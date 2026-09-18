from pathlib import Path

import config
from chunking import build_structural_chunks
from jurisprudencia import batch
from jurisprudencia.queries import DEFAULT_QUERIES, parse_queries
from jurisprudencia.schema import JurisprudenciaRecord
from scripts.sources import SOURCES


def test_default_query_pack_covers_core_procurement_topics():
    assert len(DEFAULT_QUERIES) >= 8
    assert any("contratação direta" in query for query in DEFAULT_QUERIES)
    assert any("registro de preços" in query for query in DEFAULT_QUERIES)
    assert any("reequilíbrio" in query for query in DEFAULT_QUERIES)


def test_parse_queries_supports_custom_pipe_separated_pack():
    assert parse_queries("licitação|pregão|contrato") == ("licitação", "pregão", "contrato")
    assert parse_queries("") == DEFAULT_QUERIES
    assert parse_queries(None) == DEFAULT_QUERIES


def test_jurisprudence_is_one_structural_unit_even_when_it_quotes_articles():
    text = "TRIBUNAL: TCU\nPROCESSO: 123/2026\nEMENTA:\nO art. 62 da Lei 14.133/2021 deve ser interpretado com o art. 67.\n"
    chunks = build_structural_chunks(text, 1000, 100)
    assert chunks
    assert {chunk['unit_kind'] for chunk in chunks} == {'jurisprudencia'}
    assert {chunk['unit_id'] for chunk in chunks} == {'jurisprudencia:123/2026'}


def test_record_key_distinguishes_records_without_decision_number():
    first = JurisprudenciaRecord(tribunal="STJ", numero_processo="REsp 1/2026", ementa="Tese A")
    second = JurisprudenciaRecord(tribunal="STJ", numero_processo="REsp 1/2026", ementa="Tese B")
    assert first.document_key != second.document_key


def test_expanded_sources_are_present():
    ids = {item['id'] for item in SOURCES}
    required = {
        'decreto11430', 'decreto11461', 'decreto11531', 'portaria8678',
        'in147', 'in148', 'in176', 'in190', 'in381', 'in382',
        'agu-on', 'agu-pareceres-referenciais', 'agu-modelos-14133',
        'lei4717', 'lei7347', 'lc131', 'decreto7724', 'lei6019',
        'lei12016', 'lc182', 'sp-lai', 'spm-decreto62100',
        'spm-decreto62436', 'spm-decreto64863', 'sp-pge-pareceres',
    }
    assert required <= ids
    retired = {
        'tcu', 'tcesp', 'tcu-dados-jurisprudencia', 'stj-jurisprudencia',
        'stj-teses', 'stj-repetitivos-iacs', 'stf-jurisprudencia',
        'stf-teses-rg', 'tjsp-jurisprudencia',
    }
    assert retired.isdisjoint(ids)


def test_config_uses_expanded_jurisprudence_collection_defaults():
    assert config.INDEX_VERSION == '12'
    assert len(config.JURISPRUDENCIA_QUERIES) >= 8
    assert config.JURISPRUDENCIA_LIMIT >= 10


def test_batch_deduplicates_same_record_across_queries(monkeypatch, tmp_path: Path):
    records = [JurisprudenciaRecord(
        tribunal="TCU",
        numero_processo="1/2026",
        numero_decisao="10/2026",
        tipo_decisao="Acórdão",
        ementa="Licitação",
        version_sha256="abc",
    )]
    calls = []

    def fake_collect(tribunals, query, limit, **kwargs):
        calls.append((tribunals, query, limit, kwargs))
        return records

    monkeypatch.setattr(batch, 'collect', fake_collect)
    output = batch.collect_batch(('tcu',), ('licitação', 'pregão'), 2, output_dir=tmp_path)
    assert len(calls) == 2
    assert len(output) == 1
