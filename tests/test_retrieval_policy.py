from types import SimpleNamespace

from query import _query_jurisdiction, authority_score, jurisdiction_score, mandatory_context_points, rerank


class FakeReranker:
    def __init__(self, scores):
        self.scores = scores

    def rerank(self, query, texts):
        return self.scores


def point(name, score, level, jurisdiction, normative_rank=None, unit=None):
    payload = {
        "source": name,
        "unit_id": unit or name,
        "authority_level": level,
        "jurisdicao": jurisdiction,
    }
    if normative_rank is not None:
        payload["normative_rank"] = normative_rank
    return SimpleNamespace(id=name, payload=payload)


def test_authority_score_distinguishes_normative_sublevels():
    assert authority_score({"authority_level": 1, "normative_rank": 1}) > authority_score({"authority_level": 1, "normative_rank": 4})
    assert authority_score({"authority_level": 1, "normative_rank": 4}) > authority_score({"authority_level": 2})


def test_rerank_authority_changes_top_k_selection(monkeypatch):
    monkeypatch.setattr("config.FINAL_K", 2)
    points = [
        point("guidance", 0.97, 3, "federal"),
        point("law", 0.78, 1, "federal", normative_rank=2),
    ]
    ranked = rerank(FakeReranker([5.0, 3.0]), "qualificação técnica", points)
    assert ranked[0].payload["source"] == "law"
    assert ranked[0].payload["_authority_score"] > ranked[1].payload["_authority_score"]
    assert ranked[0].payload["_retrieval_score"] > ranked[1].payload["_retrieval_score"]


def test_jurisdiction_changes_rank_for_state_control():
    points = [
        point("stj", 0.90, 2, "federal"),
        point("tcesp", 0.86, 2, "estadual_sp"),
    ]
    ranked = rerank(FakeReranker([3.0, 2.5]), "fiscalização de contrato", points, {"jurisdicao": ["estadual_sp"]})
    assert ranked[0].payload["source"] == "tcesp"
    assert ranked[0].payload["_jurisdiction_score"] == 1.0
    assert ranked[0].payload["_authority_score"] == ranked[1].payload["_authority_score"]


def test_ambiguous_query_keeps_jurisdiction_neutral():
    assert _query_jurisdiction("qual o prazo para impugnar edital?") is None


def test_structured_jurisdiction_overrides_keyword_ambiguity():
    assert _query_jurisdiction("qual o prazo para impugnar edital?", {"jurisdicao": ["estadual_sp"]}) == "estadual_sp"


class FakeDenseVector:
    def tolist(self):
        return [0.1, 0.2, 0.3]


class FakeDense:
    def embed(self, texts):
        return iter([FakeDenseVector()])


class FakeClient:
    def __init__(self, available):
        self.available = available

    def query_points(self, **kwargs):
        source_id = kwargs["query_filter"].must[0].match.value
        point = self.available.get(source_id)
        return SimpleNamespace(points=[point] if point is not None else [])


def test_mandatory_context_requires_law_and_tcu_manual():
    available = {
        "lei14133": point("lei14133", 0.9, 1, "federal"),
        "tcu-manual-licitacoes": point("tcu-manual-licitacoes", 0.8, 3, "federal"),
    }
    result = mandatory_context_points(FakeClient(available), FakeDense(), "pergunta")
    assert [item.payload["source"] for item in result] == ["lei14133", "tcu-manual-licitacoes"]
    assert all(item.payload["_mandatory_context"] is True for item in result)


def test_mandatory_context_fails_closed_when_a_required_source_is_missing():
    available = {"lei14133": point("lei14133", 0.9, 1, "federal")}
    import pytest
    with pytest.raises(RuntimeError, match="Manual de Licitações e Contratos do TCU"):
        mandatory_context_points(FakeClient(available), FakeDense(), "pergunta")
