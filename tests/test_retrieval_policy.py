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


def test_query_jurisdiction_handles_tuple_and_uppercase_inputs():
    from query import _query_jurisdiction
    assert _query_jurisdiction("pergunta", {"jurisdicao": ("FEDERAL",)}) == "federal"
    assert _query_jurisdiction("pergunta", {"jurisdicao": {"estadual_sp"}}) == "estadual_sp"


def test_structured_jurisdiction_overrides_keyword_ambiguity():
    assert _query_jurisdiction("qual o prazo para impugnar edital?", {"jurisdicao": ["estadual_sp"]}) == "estadual_sp"


def test_qfilter_accepts_tuple_or_set_jurisdiction_filters():
    from query import qfilter
    filter_tuple = qfilter(filters={"jurisdicao": ("federal", "estadual_sp")}, query="licitação")
    filter_set = qfilter(filters={"jurisdicao": {"federal", "estadual_sp"}}, query="licitação")
    assert filter_tuple is not None and filter_set is not None
    assert filter_tuple.must[0].match.any == ["federal", "estadual_sp"]
    assert filter_set.must[0].match.any == ["federal", "estadual_sp"]


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


def test_base_context_is_optional_when_a_source_is_missing():
    available = {"lei14133": point("lei14133", 0.9, 1, "federal")}
    result = mandatory_context_points(FakeClient(available), FakeDense(), "pergunta")
    assert [item.payload["source"] for item in result] == ["lei14133"]
    assert result[0].payload["_context_only"] is True


def test_retrieve_context_does_not_answer_from_base_context_without_primary_evidence(monkeypatch):
    import query

    available = {
        "lei14133": point("lei14133", 0.9, 1, "federal"),
        "tcu-manual-licitacoes": point("tcu-manual-licitacoes", 0.8, 3, "federal"),
    }

    monkeypatch.setattr(query, "hybrid", lambda *args, **kwargs: [])
    monkeypatch.setattr(query, "rerank", lambda *args, **kwargs: [])
    monkeypatch.setattr(query, "expand_context", lambda *args, **kwargs: [])

    query_text, context_text, sources = query.retrieve_context(
        FakeClient(available), FakeDense(), object(), object(), "pergunta"
    )

    assert query_text == "pergunta"
    assert context_text == []
    assert sources == []


def _match_value(condition):
    return getattr(getattr(condition, "match", None), "value", None)


def test_qfilter_infers_federal_constitution_scope():
    from query import qfilter

    query_filter = qfilter(query="Segundo a Constituição, qual é o princípio aplicável à licitação?")
    values = {_match_value(condition) for condition in query_filter.must}
    keys = {condition.key for condition in query_filter.must}
    assert "source_id" in keys
    assert "cf1988" in values
    assert "authority_level" in keys
    assert "normative_rank" in keys


def test_qfilter_infers_tcu_manual_and_jurisdiction():
    from query import qfilter

    query_filter = qfilter(query="Segundo o Manual de Licitações e Contratos do TCU, como fiscalizar?")
    conditions = {condition.key: _match_value(condition) for condition in query_filter.must}
    assert conditions["source_id"] == "tcu-manual-licitacoes"
    assert conditions["tribunal"] == "tcu"
    assert conditions["jurisdicao"] == "federal"


def test_qfilter_infers_state_constitution_scope():
    from query import qfilter

    query_filter = qfilter(query="O que diz a Constituição do Estado de São Paulo sobre controle?")
    conditions = {condition.key: _match_value(condition) for condition in query_filter.must}
    assert conditions["source_id"] == "sp-const"
    assert conditions["jurisdicao"] == "estadual_sp"


def test_transition_regimes_select_current_and_historical_frameworks():
    from query import _transition_regimes

    regimes = _transition_regimes("O que mudou na nova lei de licitações em relação ao regime anterior?")
    assert regimes == ("lei_14133", "lei_8666")


def test_transition_retrieval_query_mentions_both_regimes():
    from query import _retrieval_query

    query = _retrieval_query("O que mudou na nova lei de licitações?")
    assert "Lei 14.133/2021" in query
    assert "Lei 8.666/1993" in query
