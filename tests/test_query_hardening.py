import pytest

import config
from query import _query_jurisdiction, parse_filters


def test_municipal_jurisdiction_filter_is_rejected():
    with pytest.raises(ValueError, match='somente federal ou estadual_sp'):
        parse_filters('@jurisdicao=municipal_sp licitação')


def test_state_and_federal_jurisdiction_detection():
    assert _query_jurisdiction('regra estadual do Estado de São Paulo') == 'estadual_sp'
    assert _query_jurisdiction('regra federal da União') == 'federal'


def test_expand_context_always_includes_article_caput(monkeypatch):
    from types import SimpleNamespace
    from query import expand_context

    monkeypatch.setattr(config, 'CONTEXT_NEIGHBORS', 1)

    selected = SimpleNamespace(
        id='selected',
        payload={
            'source': 'lei',
            'unit_id': 'artigo:Art. 99.',
            'unit_kind': 'artigo',
            'chunk_index': 5,
            '_evidence_score': 0.91,
        },
    )
    neighbors = [
        SimpleNamespace(id=f'chunk-{index}', payload={
            'source': 'lei',
            'unit_id': 'artigo:Art. 99.',
            'unit_kind': 'artigo',
            'chunk_index': index,
            'page_content': f'chunk {index}',
        })
        for index in range(7)
    ]

    class FakeClient:
        def scroll(self, **kwargs):
            return neighbors, None

    expanded = expand_context(FakeClient(), [selected])
    expanded_ids = {point.id for point in expanded}
    assert 'selected' in expanded_ids
    assert 'chunk-0' in expanded_ids
    assert 'chunk-4' in expanded_ids
    assert 'chunk-6' in expanded_ids
    assert 'chunk-2' not in expanded_ids


def test_expand_context_includes_caput_even_when_neighbor_distance_is_zero(monkeypatch):
    from types import SimpleNamespace
    from query import expand_context

    monkeypatch.setattr(config, 'CONTEXT_NEIGHBORS', 0)

    selected = SimpleNamespace(
        id='selected',
        payload={
            'source': 'lei',
            'unit_id': 'artigo:Art. 100.',
            'unit_kind': 'artigo',
            'chunk_index': 4,
            '_evidence_score': 0.87,
        },
    )
    neighbors = [
        SimpleNamespace(id='caput', payload={
            'source': 'lei',
            'unit_id': 'artigo:Art. 100.',
            'unit_kind': 'artigo',
            'chunk_index': 0,
        }),
        SimpleNamespace(id='far', payload={
            'source': 'lei',
            'unit_id': 'artigo:Art. 100.',
            'unit_kind': 'artigo',
            'chunk_index': 2,
        }),
    ]

    class FakeClient:
        def scroll(self, **kwargs):
            return neighbors, None

    expanded = expand_context(FakeClient(), [selected])
    expanded_ids = {point.id for point in expanded}
    assert expanded_ids == {'selected', 'caput'}
