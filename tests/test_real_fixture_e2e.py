from pathlib import Path

from chunking import build_structural_chunks
from query import build_retrieval_plan


def test_real_fixture_lei_14133_preserves_article_sequence_and_unit_ids():
    fixture = Path(__file__).resolve().parent / "fixtures" / "legal_act.txt"
    text = fixture.read_text(encoding="utf-8")
    chunks = build_structural_chunks(text, max_size=2000, overlap=150, tokenizer=None)
    articles = [item["unit_ref"] for item in chunks if item["unit_kind"] == "artigo"]
    unit_ids = [item["unit_id"] for item in chunks if item["unit_kind"] == "artigo"]

    assert articles[:4] == ["Art. 1º", "Art. 2º", "Art. 3º", "Art. 4º"]
    assert articles[-1] == "Art. 8º"
    assert len(articles) == 8
    assert len(set(unit_ids)) == len(unit_ids)


def test_retrieval_plan_builds_the_qdrant_contract_for_real_queries():
    plan = build_retrieval_plan("quais são as regras da Lei 14.133/2021 e da Lei 8.666/1993?")

    assert plan["is_transition"] is True
    assert plan["regime_hint"] == "lei_14133"
    assert plan["mandatory_sources"] == ["lei14133", "tcu-manual-licitacoes"]
    assert plan["qdrant_filter"] is None
    assert "Lei 14.133/2021" in plan["retrieval_query"]
    assert "Lei 8.666/1993" in plan["retrieval_query"]
    assert plan["filtered_for_current_only"] is False
