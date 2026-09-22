from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import config
from embedding_utils import validate_embedding_inputs
from query import (
    EvidenceGateError,
    embedding_kwargs,
    hybrid,
    parse_filters,
    qfilter,
    rerank,
    validate_generated_answer,
)
from qdrant_client import QdrantClient
from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from index_manifest import IndexCompatibilityError, validate_manifest

DEFAULT_DATASET = Path(__file__).with_name('evaluation') / 'dataset.json'


def load_dataset(path: Path = DEFAULT_DATASET) -> dict:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'Conjunto de avaliação inválido: {path}')
    return payload


def load_cases(path: Path = DEFAULT_DATASET) -> list[dict]:
    payload = load_dataset(path)
    cases = payload.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError(f'Conjunto de avaliação inválido: {path}')
    seen = set()
    required = {'id', 'query', 'expected_source_ids'}
    for case in cases:
        if not isinstance(case, dict) or not required <= set(case):
            raise ValueError(f'Caso de avaliação inválido: {case!r}')
        case_id = str(case['id'])
        if case_id in seen:
            raise ValueError(f'ID de caso duplicado: {case_id}')
        seen.add(case_id)
        expected = case['expected_source_ids']
        if not isinstance(expected, list):
            raise ValueError(f'expected_source_ids inválido no caso {case_id}.')
        if not expected and not case.get('rejection_test'):
            raise ValueError(
                f'Caso sem fonte esperada deve marcar rejection_test: {case_id}'
            )
        jurisdiction = case.get('expected_jurisdicao')
        if jurisdiction is not None and not isinstance(jurisdiction, (str, list)):
            raise ValueError(f'expected_jurisdicao inválido no caso {case_id}.')
        if isinstance(jurisdiction, list) and not all(
            isinstance(item, str) for item in jurisdiction
        ):
            raise ValueError(f'expected_jurisdicao inválido no caso {case_id}.')
    return cases


def load_evidence_gate_cases(path: Path = DEFAULT_DATASET) -> list[dict]:
    payload = load_dataset(path)
    cases = payload.get('evidence_gate_cases', [])
    if not isinstance(cases, list) or not cases:
        raise ValueError(f'Conjunto de evidence gate inválido: {path}')
    seen = set()
    required = {'id', 'answer', 'expected_accept', 'sources'}
    for case in cases:
        if not isinstance(case, dict) or not required <= set(case):
            raise ValueError(f'Caso do evidence gate inválido: {case!r}')
        case_id = str(case['id'])
        if case_id in seen:
            raise ValueError(f'ID de evidence gate duplicado: {case_id}')
        seen.add(case_id)
        if not isinstance(case['expected_accept'], bool):
            raise ValueError(f'expected_accept inválido no caso {case_id}.')
        sources = case['sources']
        if not isinstance(sources, list) or not sources:
            raise ValueError(f'Caso do evidence gate sem fontes: {case_id}.')
        for source in sources:
            if not isinstance(source, dict) or not (
                source.get('text') or source.get('page_content')
            ):
                raise ValueError(f'Fonte inválida no caso do evidence gate {case_id}.')
    return cases


def _parse_iso_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f'Data inválida no conjunto de avaliação: {value!r}') from exc


def temporal_match(payload: dict, case: dict) -> bool | None:
    temporal = case.get('temporal')
    if not temporal:
        return None
    expected_ids = set(case['expected_source_ids'])
    if str(payload.get('source_id')) not in expected_ids:
        return False
    target = _parse_iso_date(temporal.get('effective_on'))
    if target is None:
        return None
    effective_from = _parse_iso_date(payload.get('effective_from'))
    effective_to = _parse_iso_date(payload.get('effective_to'))
    if effective_from and target < effective_from:
        return False
    if effective_to and target > effective_to:
        return False
    if str(payload.get('status') or '').casefold() == 'vacatio_legis' and effective_from and target < effective_from:
        return False
    return True


def reciprocal_rank(points, expected_source_ids: set[str]) -> float | None:
    if not expected_source_ids:
        return None
    for rank, point in enumerate(points, 1):
        if str(point.payload.get('source_id')) in expected_source_ids:
            return 1.0 / rank
    return 0.0


def recall_at_k(points, expected_source_ids: set[str], k: int) -> float | None:
    if not expected_source_ids:
        return None
    expected = {str(item) for item in expected_source_ids}
    found = {
        str(point.payload.get('source_id'))
        for point in points[:k]
        if str(point.payload.get('source_id'))
    }
    return len(found & expected) / len(expected)


def ndcg_at_k(points, expected_source_ids: set[str], k: int) -> float | None:
    if not expected_source_ids:
        return None
    expected = {str(item) for item in expected_source_ids}
    relevance = [
        1.0 if str(point.payload.get('source_id')) in expected else 0.0
        for point in points[:k]
    ]
    dcg = sum(value / math.log2(rank + 1) for rank, value in enumerate(relevance, 1))
    ideal_hits = min(k, len(expected))
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / ideal if ideal else 0.0


def _expected_jurisdictions(case: dict) -> set[str]:
    value = case.get('expected_jurisdicao')
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item) for item in value}
    return {str(value)}


def evaluate_case(points, case: dict, k_values: tuple[int, ...]) -> dict:
    expected_source_ids = {str(item) for item in case['expected_source_ids']}
    metrics = {}
    for k in k_values:
        metrics[f'recall@{k}'] = recall_at_k(points, expected_source_ids, k)
        metrics[f'ndcg@{k}'] = ndcg_at_k(points, expected_source_ids, k)
    top = points[0] if points else None
    metrics['reciprocal_rank'] = reciprocal_rank(points, expected_source_ids)
    expected_jurisdictions = _expected_jurisdictions(case)
    metrics['jurisdiction_correct'] = (
        None
        if not expected_jurisdictions
        else bool(top and str(top.payload.get('jurisdicao')) in expected_jurisdictions)
    )
    temporal = temporal_match(top.payload, case) if top and case.get('temporal') else None
    metrics['temporal_correct'] = temporal
    metrics['retrieval_rejected'] = not bool(points)
    metrics['rejection_correct'] = (
        bool(case.get('expected_rejection')) == metrics['retrieval_rejected']
        if case.get('rejection_test')
        else None
    )
    return metrics


def _mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def aggregate(case_results: list[dict], cases: list[dict], k_values: tuple[int, ...]) -> dict:
    summary = {}
    for k in k_values:
        summary[f'recall@{k}'] = _mean(item[f'recall@{k}'] for item in case_results)
        summary[f'ndcg@{k}'] = _mean(item[f'ndcg@{k}'] for item in case_results)
    summary['mrr'] = _mean(item['reciprocal_rank'] for item in case_results)
    jurisdiction_values = [
        item['jurisdiction_correct']
        for item in case_results
        if item['jurisdiction_correct'] is not None
    ]
    summary['jurisdiction_accuracy'] = _mean(jurisdiction_values)
    temporal_values = [
        item['temporal_correct']
        for item in case_results
        if item['temporal_correct'] is not None
    ]
    summary['temporal_accuracy'] = _mean(temporal_values)
    rejection_values = [
        item['rejection_correct']
        for item, case in zip(case_results, cases)
        if case.get('rejection_test') and item['rejection_correct'] is not None
    ]
    summary['retrieval_rejection_accuracy'] = _mean(rejection_values)
    summary['retrieval_rejection_cases'] = len(rejection_values)
    return summary


def evaluate_rankings(rankings: dict[str, list], cases: list[dict], k_values: tuple[int, ...]) -> dict:
    case_metrics = []
    for case in cases:
        if case['id'] not in rankings:
            raise ValueError(f'Resultado ausente para o caso {case["id"]}')
        case_metrics.append(evaluate_case(rankings[case['id']], case, k_values))
    return {
        'cases': [
            {
                'id': case['id'],
                'case_type': case.get('case_type', 'supported'),
                **metrics,
            }
            for case, metrics in zip(cases, case_metrics)
        ],
        'summary': aggregate(case_metrics, cases, k_values),
    }


def _gate_sources(case: dict):
    return [
        SimpleNamespace(
            id=f'{item.get("source", "source")}:{index}',
            payload={
                'source': item.get('source'),
                'unit_id': item.get('unit_id'),
                'text': item.get('text') or item.get('page_content') or '',
                'page_content': item.get('page_content'),
            },
        )
        for index, item in enumerate(case['sources'], 1)
    ]


def evaluate_evidence_gate(cases: list[dict]) -> dict:
    rows = []
    for case in cases:
        accepted = True
        error = None
        try:
            validate_generated_answer(case['answer'], _gate_sources(case))
        except EvidenceGateError as exc:
            accepted = False
            error = str(exc)
        rows.append({
            'id': case['id'],
            'category': case.get('category', 'unspecified'),
            'expected_accept': bool(case['expected_accept']),
            'actual_accept': accepted,
            'correct': accepted == bool(case['expected_accept']),
            'error': error,
        })

    negatives = [row for row in rows if not row['expected_accept']]
    positives = [row for row in rows if row['expected_accept']]
    correct_rejections = sum(1 for row in negatives if not row['actual_accept'])
    false_accepts = sum(1 for row in negatives if row['actual_accept'])
    correct_accepts = sum(1 for row in positives if row['actual_accept'])
    return {
        'cases': rows,
        'summary': {
            'total': len(rows),
            'accepted_expected': len(positives),
            'rejected_expected': len(negatives),
            'correct': sum(1 for row in rows if row['correct']),
            'accuracy': sum(1 for row in rows if row['correct']) / len(rows),
            'correct_rejection_rate': (
                correct_rejections / len(negatives) if negatives else None
            ),
            'false_accept_rate': false_accepts / len(negatives) if negatives else None,
            'correct_acceptance_rate': (
                correct_accepts / len(positives) if positives else None
            ),
            'observed_rejection_rate': sum(
                1 for row in rows if not row['actual_accept']
            ) / len(rows),
        },
    }


def build_retriever():
    config.ensure_directories()
    config.validate_config()
    if not config.QDRANT_PATH.exists():
        raise RuntimeError('Índice não encontrado. Rode python ingest.py antes da avaliação.')
    try:
        validate_manifest()
    except (IndexCompatibilityError, FileNotFoundError, ValueError) as error:
        raise RuntimeError(f'ERRO DE COMPATIBILIDADE: {error}') from error
    client = QdrantClient(path=str(config.QDRANT_PATH))
    if not client.collection_exists(config.COLLECTION_NAME):
        raise RuntimeError(f'Coleção Qdrant não encontrada: {config.COLLECTION_NAME}.')
    dense = TextEmbedding(
        model_name=config.DENSE_MODEL,
        max_length=config.DENSE_MAX_TOKENS,
        **embedding_kwargs(),
    )
    sparse = SparseTextEmbedding(model_name=config.SPARSE_MODEL, **embedding_kwargs())
    reranker = TextCrossEncoder(model_name=config.RERANK_MODEL, **embedding_kwargs())
    return client, dense, sparse, reranker


def retrieve_case(client, dense, sparse, reranker, raw_query: str, limit: int):
    query, filters = parse_filters(raw_query)
    if not query:
        return []
    embedding_text = 'query: ' + query
    validate_embedding_inputs(dense, [embedding_text], label='avaliação')
    dense_vector = list(dense.embed([embedding_text]))[0]
    candidates = hybrid(
        client,
        dense,
        sparse,
        query,
        qfilter(filters, query=query),
        dense_vector=dense_vector,
    )
    return rerank(reranker, query, candidates, filters, limit=limit)


def run_live_evaluation(cases: list[dict], gate_cases: list[dict], k_values: tuple[int, ...]) -> dict:
    client, dense, sparse, reranker = build_retriever()
    limit = max(k_values)
    rankings = {
        case['id']: retrieve_case(client, dense, sparse, reranker, case['query'], limit)
        for case in cases
    }
    report = evaluate_rankings(rankings, cases, k_values)
    for case in report['cases']:
        case['retrieved_source_ids'] = [
            str(point.payload.get('source_id') or '')
            for point in rankings[case['id']]
        ]
    report['evidence_gate'] = evaluate_evidence_gate(gate_cases)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='Avalia recuperação e evidence gate do RAG.')
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--k', type=int, nargs='+', default=[1, 3, 5, 10])
    parser.add_argument('--strict', action='store_true', help='Falha se os limiares mínimos configurados não forem atingidos.')
    parser.add_argument('--min-recall', type=float, default=0.0)
    parser.add_argument('--min-ndcg', type=float, default=0.0)
    parser.add_argument('--min-gate-rejection', type=float, default=0.0, help='Taxa mínima de rejeição correta para os casos negativos do evidence gate.')
    args = parser.parse_args()
    if not args.k or any(k <= 0 for k in args.k):
        parser.error('--k deve conter inteiros positivos.')

    cases = load_cases(args.dataset)
    gate_cases = load_evidence_gate_cases(args.dataset)
    report = run_live_evaluation(cases, gate_cases, tuple(sorted(set(args.k))))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict:
        k = max(args.k)
        summary = report['summary']
        gate_summary = report['evidence_gate']['summary']
        if (
            (summary[f'recall@{k}'] is not None and summary[f'recall@{k}'] < args.min_recall)
            or (summary[f'ndcg@{k}'] is not None and summary[f'ndcg@{k}'] < args.min_ndcg)
            or (
                gate_summary['correct_rejection_rate'] is not None
                and gate_summary['correct_rejection_rate'] < args.min_gate_rejection
            )
        ):
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
