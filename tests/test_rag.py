from pathlib import Path
import importlib.util

from chunking import build_structural_chunks
from query import parse_filters

ROOT = Path(__file__).resolve().parents[1]


def source_module():
    spec = importlib.util.spec_from_file_location('sync_sources', ROOT / 'scripts' / 'sync_sources.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_core_official_sources_exist():
    ids = {item['id'] for item in source_module().SOURCES}
    assert {'lei14133', 'cf1988', 'sp-const', 'tcesp'} <= ids


def test_sources_have_urls_and_metadata():
    for item in source_module().SOURCES:
        assert item['urls'] and item['title']
        assert item.get('source_role') in {'norma', 'jurisprudencia_controle', 'orientacao_oficial'}


def test_filter_parser_converts_numeric_filters():
    query, filters = parse_filters('@jurisdicao=estadual_sp @ano=2026 qual a regra do ETP?')
    assert query == 'qual a regra do ETP?'
    assert filters == {'jurisdicao': 'estadual_sp', 'ano': 2026}


def test_structural_chunking_keeps_article_unit():
    text = 'Art. 1º Esta Lei estabelece regras.\n\nArt. 2º O processo observará os princípios.\n\nArt. 3º O contrato será fiscalizado.'
    chunks = build_structural_chunks(text, 1000, 100)
    assert len(chunks) == 3
    assert [c['unit_ref'] for c in chunks] == ['Art. 1º', 'Art. 2º', 'Art. 3º']
