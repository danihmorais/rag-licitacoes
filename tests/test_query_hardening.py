import pytest

from query import _query_jurisdiction, parse_filters


def test_municipal_jurisdiction_filter_is_rejected():
    with pytest.raises(ValueError, match='somente federal ou estadual_sp'):
        parse_filters('@jurisdicao=municipal_sp licitação')


def test_state_and_federal_jurisdiction_detection():
    assert _query_jurisdiction('regra estadual do Estado de São Paulo') == 'estadual_sp'
    assert _query_jurisdiction('regra federal da União') == 'federal'
