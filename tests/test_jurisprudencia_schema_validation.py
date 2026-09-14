import pytest

from jurisprudencia.schema import JurisprudenciaRecord


def test_tjsp_is_valid_jurisprudence_source():
    record = JurisprudenciaRecord(tribunal='TJSP', numero_processo='1/2026')
    record.validate()


def test_unknown_tribunal_is_rejected():
    record = JurisprudenciaRecord(tribunal='XYZ', numero_processo='1/2026')
    with pytest.raises(ValueError, match='tribunal inválido'):
        record.validate()
