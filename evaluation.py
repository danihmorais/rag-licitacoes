from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

import config
from embedding_utils import validate_embedding_inputs
from query import embedding_kwargs, hybrid, parse_filters, qfilter, rerank
from qdrant_client import QdrantClient
from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from index_manifest import IndexCompatibilityError, validate_manifest

DEFAULT_DATASET = Path(__file__).with_name('evaluation') / 'dataset.json'


def load_cases(path: Path = DEFAULT_DATASET) -> list[dict]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    cases = payload.get('cases') if isinstance(payload, dict) else payload
    if not isinstance(cases, list) or not cases:
        raise ValueError(f'Conjunto de avaliação inválido: {path}')
    required = {'id', 'query', 'expected_source_ids', 'expected_jurisdicao'}
    for case in cases:
        if not isinstance(case, dict) or not required <= set(case):
            raise ValueError(f'Caso de avaliação inválido: {case!r}')
        if not case['expected_source_ids']:
            raise ValueError(f'Caso sem fonte esperada: {case["id"]}')
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


def reciprocal_rank(points, expected_source_ids: set[str]) -> float:
    for rank, point in enumerate(points, 1):
        if str(point.payload.get('source_id')) in expected_source_ids:
            return 1.0 / rank
    return 0.0


def recall_at_k(points, expected_source_ids: set[str], k: int) -> float:
    return 1.0 if any(str(point.payload.get('source_id')) in expected_source_ids for point in points[:k]) else 0.0


def ndcg_at_k(points, expected_source_ids: set[str], k: int) -> float:
    relevance = [
        1.0 if str(point.payload.get('source_id')) in expected_source_ids else 0.0
        for point in points[:k]
    ]
    dcg = sum(value / math.log2(rank + 1) for rank, value in enumerate(relevance, 1))
    ideal_hits = min(k, max(1, len(expected_source_ids)))
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / ideal if ideal else 0.0


def evaluate_case(points, case: dict, k_values: tuple[int, ...]) -> dict:
    expected_source_ids = {str(item) for item in case['expected_source_ids']}
    metrics = {}
    for k in k_values:
        metrics[f'recall@{k}'] = recall_at_k(points, expected_source_ids, k)
        metrics[f'ndcg@{k}'] = ndcg_at_k(points, expected_source_ids, k)
    top = points[0] if points else None
    metrics['reciprocal_rank'] = reciprocal_rank(points, expected_source_ids)
    metrics['jurisdiction_correct'] = bool(
        top and str(top.payload.get('jurisdicao')) == str(case['expected_jurisdicao'])
    )
    temporal = temporal_match(top.payload, case) if top else False
    metrics['temporal_correct'] = temporal
    return metrics


def aggregate(case_results: list[dict], cases: list[dict], k_values: tuple[int, ...]) -> dict:
    summary = {}
    for k in k_values:
        summary[f'recall@{k}'] = sum(item[f'recall@{k}'] for item in case_results) / len(case_results)
        summary[f'ndcg@{k}'] = sum(item[f'ndcg@{k}'] for item in case_results) / len(case_results)
    summary['mrr'] = sum(item['reciprocal_rank'] for item in case_results) / len(case_results)
    summary['jurisdiction_accuracy'] = sum(
        bool(item['jurisdiction_correct']) for item in case_results
    ) / len(case_results)
    temporal_cases = [
        item for item, case in zip(case_results, cases) if case.get('temporal')
    ]
    summary['temporal_accuracy'] = (
        sum(bool(item['temporal_correct']) for item in temporal_cases) / len(temporal_cases)
        if temporal_cases else None
    )
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
                **metrics,
            }
            for case, metrics in zip(cases, case_metrics)
        ],
        'summary': aggregate(case_metrics, cases, k_values),
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


def run_live_evaluation(cases: list[dict], k_values: tuple[int, ...]) -> dict:
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
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='Avalia a qualidade de recuperação do RAG.')
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--k', type=int, nargs='+', default=[1, 3, 5])
    parser.add_argument('--strict', action='store_true', help='Falha se os limiares mínimos configurados não forem atingidos.')
    parser.add_argument('--min-recall', type=float, default=0.0)
    parser.add_argument('--min-ndcg', type=float, default=0.0)
    args = parser.parse_args()
    if not args.k or any(k <= 0 for k in args.k):
        parser.error('--k deve conter inteiros positivos.')

    cases = load_cases(args.dataset)
    report = run_live_evaluation(cases, tuple(sorted(set(args.k))))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict:
        k = max(args.k)
        summary = report['summary']
        if summary[f'recall@{k}'] < args.min_recall or summary[f'ndcg@{k}'] < args.min_ndcg:
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
