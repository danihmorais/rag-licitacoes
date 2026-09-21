from types import SimpleNamespace

import pytest

import config
from query import EvidenceGateError, rerank, validate_generated_answer


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


def test_evidence_gate_accepts_claim_supported_by_cited_source():
    source = make_point("lei14133", "artigo:1", "Lei 14.133/2021. Art. 1º A licitação observará a legalidade e a eficiência.")
    assert validate_generated_answer(
        "O Art. 1º da Lei 14.133/2021 determina a observância da legalidade e da eficiência. [F1]",
        [source],
    )


def test_evidence_gate_rejects_unknown_citation():
    source = make_point("lei14133", "artigo:1", "A licitação observará a legalidade.")
    with pytest.raises(EvidenceGateError, match="fonte"):
        validate_generated_answer("A regra é esta. [F2]", [source])


def test_evidence_gate_rejects_unsupported_legal_identifier():
    source = make_point("lei14133", "artigo:1", "Art. 1º A licitação observará a legalidade.")
    with pytest.raises(EvidenceGateError, match="Identificador jurídico"):
        validate_generated_answer("O Art. 8º da Lei 14.133/2021 determina outra regra. [F1]", [source])



def test_evidence_gate_accepts_common_citation_brackets_and_markdown_heading():
    source = make_point(
        "lei14133", "artigo:1",
        "Lei 14.133/2021. Art. 1º A licitação observará planejamento e eficiência.",
    )
    assert validate_generated_answer(
        "## Requisitos\nO ETP deve observar planejamento e eficiência. 【F1】",
        [source],
    )


def test_evidence_gate_accepts_citation_on_following_line():
    source = make_point(
        "lei14133", "artigo:1",
        "A licitação observará planejamento e eficiência.",
    )
    assert validate_generated_answer(
        "A contratação deve observar planejamento e eficiência.\n[F1]",
        [source],
    )
