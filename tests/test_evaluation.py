from __future__ import annotations

from types import SimpleNamespace

from evaluation import (
    DEFAULT_DATASET,
    evaluate_rankings,
    load_cases,
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


def test_reference_dataset_is_loadable_and_nonempty():
    cases = load_cases(DEFAULT_DATASET)
    assert len(cases) >= 10
    assert all(case['expected_source_ids'] for case in cases)


def test_recall_and_ndcg_reward_relevant_source_at_top():
    ranking = [
        point('ruim'),
        point('lei14133'),
        point('outro'),
    ]
    expected = {'lei14133'}
    assert recall_at_k(ranking, expected, 1) == 0.0
    assert recall_at_k(ranking, expected, 2) == 1.0
    assert ndcg_at_k(ranking, expected, 2) == 1.0 / __import__('math').log2(3)


def test_evaluation_report_tracks_jurisdiction_and_temporal_accuracy():
    cases = [
        {
            'id': 'case',
            'query': 'consulta',
            'expected_source_ids': ['lei8666'],
            'expected_jurisdicao': 'federal',
            'temporal': {'effective_on': '2023-12-15'},
        }
    ]
    rankings = {
        'case': [point('lei8666', effective_to='2023-12-30')]
    }
    report = evaluate_rankings(rankings, cases, (1,))
    assert report['summary']['recall@1'] == 1.0
    assert report['summary']['jurisdiction_accuracy'] == 1.0
    assert report['summary']['temporal_accuracy'] == 1.0


def test_temporal_match_rejects_historical_source_outside_validity_window():
    case = {
        'expected_source_ids': ['lei8666'],
        'temporal': {'effective_on': '2024-01-15'},
    }
    payload = point('lei8666', effective_to='2023-12-30').payload
    assert temporal_match(payload, case) is False
