from pathlib import Path
import importlib.util

from chunking import build_structural_chunks
from query import evidence_score, parse_filters

ROOT = Path(__file__).resolve().parents[1]


def source_module():
    spec = importlib.util.spec_from_file_location('sync_sources', ROOT / 'scripts' / 'sync_sources.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def test_core_official_sources_exist():
    ids={item['id'] for item in source_module().SOURCES}
    assert {'lei14133','cf1988','sp-const','tcesp','tcesp-srp','decreto11462','decreto11878','in65','in58','in81','sp-pca'} <= ids


def test_sources_have_urls_and_metadata():
    allowed={'norma','jurisprudencia_controle','orientacao_oficial'}
    for item in source_module().SOURCES:
        assert item['urls'] and item['title']; assert item.get('source_role') in allowed
        assert item.get('status') in {'vigente','revogado','vacatio_legis'}


def test_historical_laws_are_marked_revoked():
    sources={item['id']:item for item in source_module().SOURCES}
    assert sources['lei8666']['status']=='revogado' and sources['lei8666']['revogado'] is True
    assert sources['lei10520']['status']=='revogado'


def test_future_rule_keeps_effective_date():
    sources={item['id']:item for item in source_module().SOURCES}
    assert sources['in512']['status']=='vacatio_legis' and sources['in512']['effective_from']=='2026-11-30'
    assert sources['in129']['required'] is True


def test_filter_parser_converts_numeric_filters():
    query,filters=parse_filters('@jurisdicao=estadual_sp @ano=2026 qual a regra do ETP?')
    assert query=='qual a regra do ETP?' and filters=={'jurisdicao':'estadual_sp','ano':2026}


def test_structural_chunking_keeps_article_unit():
    text='Art. 1º Esta Lei estabelece regras.\n\nArt. 2º O processo observará os princípios.\n\nArt. 3º O contrato será fiscalizado.'
    chunks=build_structural_chunks(text,1000,100)
    assert len(chunks)==3 and [c['unit_ref'] for c in chunks]==['Art. 1º','Art. 2º','Art. 3º']


def test_structural_chunking_accepts_artigo_and_letter_suffix():
    text='Artigo 1º A regra geral.\n\nArt. 10-A O procedimento especial.\n\nArt. 11 A fiscalização.'
    chunks=build_structural_chunks(text,1000,100)
    assert [c['unit_ref'] for c in chunks]==['Artigo 1º','Art. 10-A','Art. 11']


def test_evidence_score_is_bounded():
    assert evidence_score(0.5)==0.5
    assert 0.0 < evidence_score(-5.0) < 0.5
    assert 0.5 < evidence_score(5.0) < 1.0
