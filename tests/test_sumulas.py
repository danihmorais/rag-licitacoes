from pathlib import Path

from jurisprudencia.collector import save_record
import jurisprudencia.sumulas as sumulas

from jurisprudencia.sumulas import (
    TCU_SUMULA_DOCUMENT_URL,
    TCU_SUMULA_MIN_RECORDS,
    TCU_SUMULA_MAX_NUMBER,
    TCU_SUMULA_REQUIRED_NUMBERS,
    TCESP_SUMULA_MIN_RECORDS,
    TCESP_SUMULA_URL,
    _parse_tcu_sumula_document,
    _parse_tcesp_sumulas_text,
    collect_tcesp_sumulas,
)


def test_tcu_document_parser_extracts_enunciado_from_official_layout():
    raw = """
    <html><body>
      <div>Enunciado</div>
      <div>SÚMULA TCU 222: As decisões do Tribunal de Contas da União, relativas à aplicação de normas gerais de licitação, devem ser acatadas.</div>
      <div>Excerto</div>
      <div>Fundamento legal</div>
      <div>Lei nº 8.666/1993.</div>
    </body></html>
    """.encode("utf-8")

    record = _parse_tcu_sumula_document(
        raw,
        222,
        TCU_SUMULA_DOCUMENT_URL.format(numero=222),
    )

    assert record is not None
    assert record.tribunal == "TCU"
    assert record.tipo_documento == "sumula"
    assert record.numero_sumula == "222"
    assert record.tipo_decisao == "Súmula"
    assert "normas gerais de licitação" in record.ementa


def test_tcu_document_parser_accepts_numero_marker_and_status():
    raw = """
    <html><body>
      <div>Enunciado</div>
      <div>SÚMULA TCU Nº 247: É obrigatória a admissão da adjudicação por item.</div>
      <div>Excerto</div>
    </body></html>
    """.encode("utf-8")

    record = _parse_tcu_sumula_document(
        raw,
        247,
        TCU_SUMULA_DOCUMENT_URL.format(numero=247),
    )

    assert record is not None
    assert record.numero_sumula == "247"
    assert record.ementa == "É obrigatória a admissão da adjudicação por item."


def test_tcu_collection_contract_contains_key_summulas():
    assert "{numero}" in TCU_SUMULA_DOCUMENT_URL
    assert TCU_SUMULA_DOCUMENT_URL.startswith("https://pesquisa.apps.tcu.gov.br/documento/sumula/")
    assert TCU_SUMULA_MAX_NUMBER == 292
    assert TCU_SUMULA_MIN_RECORDS == 292
    assert TCU_SUMULA_REQUIRED_NUMBERS == (222, 247, 259, 263, 292)




def test_tcu_strict_catalog_expected_numbers_are_contiguous():
    assert set(range(1, TCU_SUMULA_MAX_NUMBER + 1)) == set(range(1, 293))


def test_tcesp_parser_extracts_current_catalog_and_preserves_cancelled_status():
    parts = []
    for number in range(1, TCESP_SUMULA_MIN_RECORDS + 1):
        suffix = " (CANCELADA)" if number == 5 else ""
        parts.append(
            f"SÚMULA Nº {number} - Texto da súmula {number}.{suffix}\n"
            "HISTÓRICO | Aprovação e fundamentos."
        )
    html = "<html><body>" + "\n".join(parts) + "</body></html>"

    records = _parse_tcesp_sumulas_text(html)

    assert len(records) == TCESP_SUMULA_MIN_RECORDS
    assert {int(item.numero_sumula) for item in records} == set(range(1, TCESP_SUMULA_MIN_RECORDS + 1))
    cancelled = next(item for item in records if item.numero_sumula == "5")
    assert cancelled.situacao == "CANCELADA"
    assert "(CANCELADA)" not in cancelled.ementa
    assert next(item for item in records if item.numero_sumula == str(TCESP_SUMULA_MIN_RECORDS)).orgao_julgador == "Tribunal Pleno"


def test_tcesp_collection_uses_current_official_catalog():
    class Response:
        content = (
            "<html><body>"
            "SÚMULA Nº 1 - Primeiro enunciado.\n"
            "SÚMULA Nº 2 - Segundo enunciado.\n"
            "</body></html>"
        ).encode("utf-8")

        def raise_for_status(self):
            return None

    class Session:
        def get(self, url, **kwargs):
            assert url == TCESP_SUMULA_URL
            return Response()

    records = collect_tcesp_sumulas(Session())
    assert [record.numero_sumula for record in records] == ["1", "2"]


def test_tcesp_parser_accepts_heading_without_ordinal():
    records = _parse_tcesp_sumulas_text("SÚMULA 53 – Enunciado da Súmula 53.")
    assert len(records) == 1
    assert records[0].numero_sumula == "53"


def test_sumula_save_record_has_dedicated_type(tmp_path: Path):
    from jurisprudencia.schema import JurisprudenciaRecord

    record = JurisprudenciaRecord(
        tribunal="TCU",
        tipo_documento="sumula",
        numero_processo="Súmula TCU 247",
        numero_sumula="247",
        numero_decisao="247",
        tipo_decisao="Súmula",
        ementa="É obrigatória a admissão da adjudicação por item.",
        url_oficial=TCU_SUMULA_DOCUMENT_URL.format(numero=247),
    )

    path = save_record(record, tmp_path)
    data = path.with_suffix(".json").read_text(encoding="utf-8")

    assert '"source_id": "tcu-sumulas"' in data
    assert '"tipo_documento": "sumula"' in data
    assert '"status": "vigente"' in data


def test_sumula_schema_does_not_require_process_number():
    from jurisprudencia.schema import JurisprudenciaRecord

    record = JurisprudenciaRecord(
        tribunal="TCESP",
        tipo_documento="sumula",
        numero_sumula="53",
        tipo_decisao="Súmula",
        ementa="Enunciado da Súmula 53.",
    )

    record.validate()
    assert "SÚMULA: 53" in record.to_index_text()


def test_batch_can_disable_sumulas_for_targeted_health_checks(monkeypatch, tmp_path: Path):
    import jurisprudencia.batch as batch

    monkeypatch.setattr(batch, "collect", lambda *args, **kwargs: [])

    def fail_sumulas(**kwargs):
        raise AssertionError("súmulas não deveriam ser coletadas")

    monkeypatch.setattr(batch, "collect_sumulas", fail_sumulas)

    result = batch.collect_batch(
        ("tcu",),
        ("licitação",),
        1,
        output_dir=tmp_path,
        include_sumulas=False,
    )

    assert result == []


def test_tcu_collection_uses_browser_fallback_for_unparsed_portal(monkeypatch):
    record = sumulas._make_tcu_record(
        222,
        "Enunciado da Súmula 222.",
        source_url=TCU_SUMULA_DOCUMENT_URL.format(numero=222),
    )

    monkeypatch.setattr(sumulas, "_fetch_tcu_sumula", lambda number: None)

    async def fake_browser(numbers):
        assert numbers == [222]
        return [record]

    monkeypatch.setattr(sumulas, "_collect_tcu_sumulas_browser", fake_browser)

    records = sumulas._collect_tcu_sumulas([222])

    assert [item.numero_sumula for item in records] == ["222"]


def test_collect_sumulas_strict_only_validates_requested_tribunals(monkeypatch):
    monkeypatch.setattr(
        sumulas,
        "collect_tcu_sumulas",
        lambda: [sumulas._make_tcu_record(
            222,
            "Enunciado da Súmula 222.",
            source_url=TCU_SUMULA_DOCUMENT_URL.format(numero=222),
        )] * 295,
    )

    def fail_tcesp():
        raise AssertionError("TCESP não deveria ser consultado")

    monkeypatch.setattr(sumulas, "collect_tcesp_sumulas", fail_tcesp)

    result = sumulas.collect_sumulas(tribunals=("tcu",), strict=False)

    assert len(result["tcu"]) == 295
    assert result["tcesp"] == []


def test_tcesp_strict_validation_accepts_current_catalog_size(monkeypatch):
    records = [
        sumulas.JurisprudenciaRecord(
            tribunal="TCESP",
            tipo_documento="sumula",
            numero_sumula=str(number),
            tipo_decisao="Súmula",
            ementa=f"Enunciado {number}.",
        )
        for number in range(1, TCESP_SUMULA_MIN_RECORDS + 1)
    ]
    monkeypatch.setattr(sumulas, "collect_tcesp_sumulas", lambda: records)
    monkeypatch.setattr(sumulas, "collect_tcu_sumulas", lambda: [])
    result = sumulas.collect_sumulas(tribunals=("tcesp",), strict=True)
    assert len(result["tcesp"]) == TCESP_SUMULA_MIN_RECORDS
