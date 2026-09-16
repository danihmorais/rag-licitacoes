from types import SimpleNamespace

import config
from query import rerank


def make_point(source, unit_id, text):
    return SimpleNamespace(
        id=f'{source}:{unit_id}',
        payload={'source': source, 'unit_id': unit_id, 'text': text},
    )


class FakeReranker:
    def __init__(self, scores):
        self.scores = scores

    def rerank(self, query, texts):
        assert query == 'consulta'
        assert len(texts) == len(self.scores)
        return self.scores


def test_min_evidence_score_filters_each_candidate(monkeypatch):
    monkeypatch.setattr(config, 'FINAL_K', 3)
    monkeypatch.setattr(config, 'MIN_EVIDENCE_SCORE', 0.8)
    monkeypatch.setattr(config, 'RERANK_SCORE_MODE', 'identity')

    points = [
        make_point('fonte-a', 'u1', 'forte'),
        make_point('fonte-b', 'u1', 'fraca'),
        make_point('fonte-c', 'u1', 'forte-2'),
    ]
    result = rerank(FakeReranker([0.95, 0.20, 0.85]), 'consulta', points)

    assert [point.payload['_evidence_score'] for point in result] == [0.95, 0.85]
    assert all(point.payload['_evidence_score'] >= config.MIN_EVIDENCE_SCORE for point in result)
