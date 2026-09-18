import pytest

from jurisprudencia.schema import JurisprudenciaRecord


def test_tjsp_is_valid_jurisprudence_source():
    record = JurisprudenciaRecord(tribunal='TJSP', numero_processo='1/2026')
    record.validate()


def test_unknown_tribunal_is_rejected():
    record = JurisprudenciaRecord(tribunal='XYZ', numero_processo='1/2026')
    with pytest.raises(ValueError, match='tribunal inválido'):
        record.validate()


def test_schema_normalizes_tcu_variants_before_validation():
    record = JurisprudenciaRecord(
        tribunal="Tribunal de Contas da União",
        numeroProcesso="TC 000.123/2026-1",
        numeroAcordao="1234/2026",
        assunto="licitação; contrato",
    )
    record.validate()
    assert record.tribunal == "TCU"
    assert record.numero_processo == "TC 000.123/2026-1"
    assert record.numero_decisao == "1234/2026"
    assert record.assunto == ["licitação", "contrato"]


def test_schema_normalizes_tcesp_and_tcm_aliases():
    tcesp = JurisprudenciaRecord(siglaTribunal="TCE-SP", processo_numero="1/2026")
    tcesp.validate()
    assert tcesp.tribunal == "TCESP"
    tcm = JurisprudenciaRecord(tribunal="TCM SP", processo="2/2026")
    tcm.validate()
    assert tcm.tribunal == "TCM-SP"
