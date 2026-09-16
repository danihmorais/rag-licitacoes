from pathlib import Path
import json

import pytest

from metadata import extract_metadata
from query import parse_filters, qfilter
from jurisprudencia.schema import JurisprudenciaRecord
from scripts.sources import SOURCES


def test_filters_support_or_values():
    query, filters = parse_filters('@jurisdicao=estadual_sp,federal pergunta')
    assert query == 'pergunta'
    assert filters == {'jurisdicao': ['estadual_sp', 'federal']}


def test_filters_support_ranges():
    query, filters = parse_filters('@ano>=2020 @ano<=2025 regra')
    assert query == 'regra'
    assert filters == {'ano': {'gte': 2020, 'lte': 2025}}
    compiled = qfilter(filters)
    assert compiled.must[0].key == 'ano'
    assert compiled.must[0].range.gte == 2020
    assert compiled.must[0].range.lte == 2025


def test_filter_rejects_range_for_non_numeric_field():
    with pytest.raises(ValueError, match='não aceita'):
        parse_filters('@jurisdicao>=federal pergunta')


def test_ambiguous_filename_is_not_guessed_without_sidecar(tmp_path: Path):
    path = tmp_path / 'lei_14133_sp.pdf'
    path.write_text('', encoding='utf-8')
    metadata = extract_metadata('Lei 14.133 de 1º de abril de 2021', path)
    assert metadata['metadata_ambiguous'] is True
    assert metadata['jurisdicao'] is None


def test_sidecar_is_authoritative_for_ambiguous_filename(tmp_path: Path):
    path = tmp_path / 'lei_14133_sp.pdf'
    path.write_text('', encoding='utf-8')
    path.with_suffix('.json').write_text(
        json.dumps({'jurisdicao': 'estadual_sp', 'esfera': 'estadual', 'orgao': 'Estado de São Paulo'}),
        encoding='utf-8',
    )
    metadata = extract_metadata('Lei 14.133 de 1º de abril de 2021', path)
    assert metadata['jurisdicao'] == 'estadual_sp'
    assert metadata['esfera'] == 'estadual'


def test_jurisprudence_sidecar_authority_is_normalized_from_tribunal(tmp_path: Path):
    path = tmp_path / 'julgado.json.pdf'
    path.write_text('', encoding='utf-8')
    path.with_suffix('.json').write_text(
        json.dumps({'tribunal': 'TCU', 'jurisdicao': 'federal', 'esfera': 'federal', 'authority_level': 2}),
        encoding='utf-8',
    )
    metadata = extract_metadata('TRIBUNAL: TCU\nPROCESSO: 1/2026', path)
    assert metadata['authority_level'] == 3


def test_catalog_jurisprudence_sources_have_tribunal_and_valid_authority():
    expected = {'STF': 2, 'STJ': 3, 'TCU': 3, 'TCESP': 4, 'TJSP': 4}
    roles = {'jurisprudencia', 'jurisprudencia_controle'}
    for source in SOURCES:
        if source.get('source_role') not in roles:
            continue
        tribunal = source.get('tribunal')
        assert tribunal in expected, f"fonte sem tribunal válido: {source.get('id')}"
        assert source.get('authority_level') == expected[tribunal], f"autoridade inconsistente: {source.get('id')}"


def test_orientation_filename_with_sp_is_not_promoted_to_norma(tmp_path: Path):
    path = tmp_path / 'guia_sustentabilidade_sp.pdf'
    path.write_text('', encoding='utf-8')
    metadata = extract_metadata('Guia de sustentabilidade', path)
    assert metadata['source_role'] == 'orientacao_oficial'
    assert metadata['authority_level'] == 3


def test_jurisprudence_schema_rejects_invalid_records():
    record = JurisprudenciaRecord(tribunal='XYZ', numero_processo='1/2026')
    with pytest.raises(ValueError, match='tribunal inválido'):
        record.validate()


def test_jurisprudence_schema_accepts_supported_record():
    record = JurisprudenciaRecord(tribunal='TCESP', numero_processo='1/2026', url_oficial='https://example.com')
    record.validate()
    assert record.to_index_text().startswith('TRIBUNAL: TCESP')
