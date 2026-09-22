from __future__ import annotations

from types import SimpleNamespace
import math

from evaluation import (
    DEFAULT_DATASET,
    evaluate_evidence_gate,
    evaluate_rankings,
    load_cases,
    load_evidence_gate_cases,
    ndcg_at_k,
    recall_at_k,
    temporal_match,
)


def point(source_id, jurisdicao='federal', effective_from=None, effective_to=None, status='vigente'):
    return SimpleNamespace(
        payload={
            'source_id': source_id,
            'jurisdicao': jurisdicao,
            'effective_from': effective_from,
            'effective_to': effective_to,
            'status': status,
        }
    )


def test_reference_dataset_matches_source_catalog():
    from scripts.sources import SOURCE_BY_ID
    cases = load_cases(DEFAULT_DATASET)
    expected = {
        source_id
        for case in cases
        for source_id in case['expected_source_ids']
    }
    assert expected <= set(SOURCE_BY_ID)


def test_reference_dataset_contains_dozen_cases_and_gate_cases():
    cases = load_cases(DEFAULT_DATASET)
    gate_cases = load_evidence_gate_cases(DEFAULT_DATASET)
    assert len(cases) >= 30
    assert len(gate_cases) >= 12
    assert any(case.get('case_type') == 'false_premise' for case in cases)
    assert any(case.get('case_type') == 'out_of_corpus' for case in cases)
    assert sum(case.get('case_type') == 'jurisdiction_conflict' for case in cases) >= 3


def test_recall_is_fractional_for_multi_source_cases():
    ranking = [
        point('lei14133'),
        point('ruim'),
        point('sp-lei10177', jurisdicao='estadual_sp'),
    ]
    expected = {'lei14133', 'sp-lei10177'}
    assert recall_at_k(ranking, expected, 1) == 0.5
    assert recall_at_k(ranking, expected, 3) == 1.0


def test_ndcg_rewards_relevant_source_at_top():
    ranking = [
        point('ruim'),
        point('lei14133'),
        point('outro'),
    ]
    expected = {'lei14133'}
    assert recall_at_k(ranking, expected, 1) == 0.0
    assert recall_at_k(ranking, expected, 2) == 1.0
    assert ndcg_at_k(ranking, expected, 2) == 1.0 / math.log2(3)


def test_evaluation_report_tracks_multi_jurisdiction_and_temporal_accuracy():
    cases = [
        {
            'id': 'case',
            'query': 'consulta',
            'expected_source_ids': ['lei14133', 'sp-lei10177'],
            'expected_jurisdicao': ['federal', 'estadual_sp'],
            'temporal': {'effective_on': '2023-12-15'},
        }
    ]
    rankings = {
        'case': [
            point('lei14133', jurisdicao='federal', effective_to='2099-12-30')
        ]
    }
    report = evaluate_rankings(rankings, cases, (1, 3))
    assert report['summary']['recall@1'] == 0.5
    assert report['summary']['jurisdiction_accuracy'] == 1.0
    assert report['summary']['temporal_accuracy'] == 1.0


def test_rejection_case_is_scored_separately_from_recall():
    cases = [
        {
            'id': 'ood',
            'query': 'fora do corpus',
            'expected_source_ids': [],
            'expected_rejection': True,
            'rejection_test': True,
            'expected_jurisdicao': None,
        }
    ]
    report = evaluate_rankings({'ood': []}, cases, (1,))
    assert report['summary']['recall@1'] is None
    assert report['summary']['retrieval_rejection_accuracy'] == 1.0


def test_temporal_match_rejects_historical_source_outside_validity_window():
    case = {
        'expected_source_ids': ['lei8666'],
        'temporal': {'effective_on': '2024-01-15'},
    }
    payload = point('lei8666', effective_to='2023-12-30').payload
    assert temporal_match(payload, case) is False


def test_evidence_gate_report_measures_correct_rejection_rate():
    cases = [
        {
            'id': 'accept',
            'answer': 'Planejamento e eficiência. [F1]',
            'expected_accept': True,
            'sources': [
                {'source': 'lei14133', 'unit_id': 'artigo:1', 'text': 'Planejamento e eficiência.'}
            ],
        },
        {
            'id': 'reject',
            'answer': 'Art. 8º da Lei 14.133/2021. [F1]',
            'expected_accept': False,
            'sources': [
                {'source': 'lei14133', 'unit_id': 'artigo:1', 'text': 'Art. 1º A licitação observará planejamento.'}
            ],
        },
    ]
    report = evaluate_evidence_gate(cases)
    assert report['summary']['correct_rejection_rate'] == 1.0
    assert report['summary']['false_accept_rate'] == 0.0
    assert report['summary']['correct_acceptance_rate'] == 1.0
    assert report['summary']['accuracy'] == 1.0
