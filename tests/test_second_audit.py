from pathlib import Path
from types import SimpleNamespace

import pytest

import chunking
import config
import ingest
import metadata
import query


class FakeTokenizer:
    def encode(self, text):
        return SimpleNamespace(ids=str(text).split())

    def no_truncation(self):
        return None


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def test_article_markers_without_space_are_structural_headers():
    text = (
        "LEI Nº 1, DE 2026\n"
        "Art.1º Regra principal.\n"
        "Artigo2º Segunda regra.\n"
        "Art. 3º Conforme Art.4º da Lei nº 1. Não é artigo novo.\n"
        "Art.5-A Nova regra.\n"
    )
    units = chunking._article_units(text)
    assert [unit["ref"] for unit in units] == [
        "Art.1º",
        "Artigo2º",
        "Art. 3º",
        "Art.5-A",
    ]


def test_amendment_compound_reference_does_not_create_parent_article_target():
    amendment = chunking._detect_amendment(
        "Fica alterado o § 2º do art. 75.", "Art. 2º"
    )
    assert amendment is not None
    assert amendment["target_devices"] == [
        {"kind": "paragrafo", "ref": "§ 2º do art. 75"}
    ]


def test_amendment_with_multiple_devices_keeps_distinct_targets():
    amendment = chunking._detect_amendment(
        'Ficam alteradas a alínea "a" do inciso IV do art. 75 e o § 3º do art. 76.',
        "Art. 2º",
    )
    assert amendment is not None
    assert {item["kind"] for item in amendment["target_devices"]} == {"alinea", "paragrafo"}
    assert len(amendment["target_devices"]) == 2


def test_formal_legal_ast_has_structural_parents_and_exact_source_spans():
    text = (
        "LEI Nº 1, DE 2026\n"
        "CAPÍTULO I\n"
        "Art. 1º Regra geral.\n"
        "I - primeira hipótese.\n"
        "a) detalhe.\n"
        "1. subitem.\n"
        "ANEXO I\n"
        "Art. 1º Regra do anexo.\n"
        "II - dispositivo do anexo.\n"
        "ANEXO II\n"
        "Art. 1º Regra do segundo anexo.\n"
    )
    ast = chunking.build_legal_ast(text)
    nodes = list(_walk(ast))
    assert ast.kind == "norma"
    assert all(node.source_start <= node.source_end for node in nodes)
    assert all(
        text[node.source_start:node.source_end] == node.source_text
        for node in nodes
    )

    articles = [node for node in nodes if node.kind == "artigo"]
    assert len(articles) == 3
    assert len({node.node_id for node in articles}) == 3

    body_article = next(node for node in articles if "Regra geral" in node.source_text)
    assert body_article.parent_id != ast.node_id
    assert any(child.kind == "inciso" for child in body_article.children)
    inciso = next(child for child in body_article.children if child.kind == "inciso")
    assert inciso.parent_id == body_article.node_id
    assert text[inciso.source_start:inciso.source_end] == inciso.source_text

    annex_articles = [node for node in articles if node.anexo_ref]
    assert len(annex_articles) == 2
    assert {node.anexo_ref for node in annex_articles} == {"ANEXO I", "ANEXO II"}
    assert len({node.parent_id for node in annex_articles}) == 2
    assert all(node.anexo_path for node in annex_articles)


def test_structural_chunks_preserve_source_slice_exactly():
    text = (
        "LEI Nº 1, DE 2026\n"
        "Art. 1º Caput.\n"
        "§ 1º Primeiro parágrafo.\n"
        "I - primeiro inciso.\n"
        "Art.2º Segundo artigo.\n"
    )
    chunks = chunking.build_structural_chunks(
        text, 2000, 0, tokenizer=FakeTokenizer()
    )
    assert chunks
    for chunk in chunks:
        start = chunk["source_start"]
        end = chunk["source_end"]
        assert text[start:end] == chunk["source_text"]
        assert chunk["node_id"]


def test_metadata_citations_never_change_the_document_regime():
    path = Path("lei_14133_regra.txt")
    text = (
        "LEI Nº 14.133, DE 1º DE ABRIL DE 2021\n"
        "Art. 177. Esta Lei menciona a Lei nº 8.666/1993 e a Lei nº 10.520/2002.\n"
        "O texto também explica a transição entre regimes."
    )
    result = metadata.extract_metadata(text, path)
    assert result["document_regime"] == "lei_14133"
    assert result["regime_juridico"] == "lei_14133"
    assert set(result["cited_regimes"]) == {"lei_8666", "lei_10520"}


def test_query_modes_do_not_treat_historical_regime_mentions_as_comparisons():
    specific = query.build_retrieval_plan(
        "Qual era a regra aplicável pela Lei 8.666/1993?"
    )
    historical = query.build_retrieval_plan(
        "A Lei 8.666/1993 estava vigente em dezembro de 2023?"
    )
    comparative = query.build_retrieval_plan(
        "O que mudou entre a Lei 14.133/2021 e a Lei 8.666/1993?"
    )

    assert specific["is_transition"] is False
    assert specific["regime_hint"] == "lei_8666"
    assert historical["is_transition"] is False
    assert historical["is_historical"] is True
    assert historical["regime_hint"] == "lei_8666"
    assert comparative["is_transition"] is True
    assert comparative["is_historical"] is False
    assert "Lei 14.133/2021" in comparative["retrieval_query"]
    assert "Lei 8.666/1993" in comparative["retrieval_query"]


def test_mandatory_context_is_secondary_when_context_budget_is_tight(monkeypatch):
    dense = SimpleNamespace(embed=lambda texts: iter([SimpleNamespace(tolist=lambda: [0.1, 0.2, 0.3])]))
    primary = SimpleNamespace(
        id="primary",
        payload={"source": "lei14133", "title": "Lei", "page_content": "Evidência principal."},
    )
    mandatory_a = SimpleNamespace(
        id="mandatory-a",
        payload={"source": "lei14133", "title": "Lei", "page_content": "Contexto obrigatório A."},
    )
    mandatory_b = SimpleNamespace(
        id="mandatory-b",
        payload={"source": "tcu-manual-licitacoes", "title": "Manual TCU", "page_content": "Contexto obrigatório B."},
    )

    monkeypatch.setattr(query, "hybrid", lambda *args, **kwargs: [primary])
    monkeypatch.setattr(query, "rerank", lambda *args, **kwargs: [primary])
    monkeypatch.setattr(query, "expand_context", lambda *args, **kwargs: [primary])
    monkeypatch.setattr(
        query,
        "mandatory_context_points",
        lambda *args, **kwargs: [mandatory_a, mandatory_b],
    )
    monkeypatch.setattr(config, "MAX_CONTEXT_CHARS", 620)

    _query, _context, sources = query.retrieve_context(
        dense,  # client slot is irrelevant because hybrid is mocked
        dense,
        object(),
        object(),
        "pergunta",
    )
    assert sources
    assert sources[0].id == "primary"


def test_repeated_page_edge_noise_is_removed_without_erasing_normative_heading():
    records = [
        {
            "page": 1,
            "text": "CABEÇALHO DO PORTAL\nLEI Nº 14.133, DE 2021\nArt. 1º Regra.\nRODAPE 1",
            "text_origin": "native",
            "extraction_confidence": 0.9,
        },
        {
            "page": 2,
            "text": "CABEÇALHO DO PORTAL\nArt. 2º Outra regra.\nRODAPE 1",
            "text_origin": "native",
            "extraction_confidence": 0.9,
        },
    ]
    cleaned = ingest._remove_repeated_page_noise(records)
    assert cleaned[0]["text"].startswith("LEI Nº 14.133")
    assert "CABEÇALHO DO PORTAL" not in cleaned[0]["text"]
    assert "RODAPE 1" not in cleaned[0]["text"]
    assert cleaned[1]["text"] == "Art. 2º Outra regra."


def test_multi_regime_specific_query_filters_both_regimes_without_becoming_transition():
    query_filter = query.qfilter(
        query="Quais regras constam na Lei 14.133/2021 e na Lei 8.666/1993?"
    )
    condition = next(item for item in query_filter.must if item.key == "regime_juridico")
    assert condition.match.any == ["lei_14133", "lei_8666"]


def test_manifest_declares_the_legal_ast_schema():
    import index_manifest
    manifest = index_manifest.current_manifest()
    assert manifest["manifest_schema_version"] == 2
    assert manifest["legal_ast_schema_version"] == chunking.LEGAL_AST_SCHEMA_VERSION
    assert "source_start/source_end" in manifest["schema"]
    assert "device_id" in manifest["schema"]
    assert "anexo_ref" in manifest["schema"]
