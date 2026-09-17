from types import SimpleNamespace

from query import authority_score, jurisdiction_score, rerank


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
