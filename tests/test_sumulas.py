from pathlib import Path

from jurisprudencia.collector import save_record
from jurisprudencia.sumulas import _tcu_record, collect_tcesp_sumulas


def test_tcu_sumula_parser_extracts_enunciado_and_status():
    raw = """
    <html><body>
    <h1>Resultados da pesquisa</h1>
    <div>SÚMULA TCU 247: É obrigatória a admissão da adjudicação por item e não por preço global.</div>
    <div>Acórdão 1782/2004-Plenário | RELATOR Marcos Vinicios Vilaça</div>
    </body></html>
    """.encode("utf-8")
    record = _tcu_record(247, raw)
    assert record is not None
    assert record.tribunal == "TCU"
    assert record.numero_decisao == "247"
    assert record.numero_sumula == "247"
    assert record.tipo_documento == "sumula"
    assert record.tipo_decisao == "Súmula"
    assert "adjudicação por item" in record.ementa


def test_tcesp_sumula_parser_extracts_all_53_and_cancelled_status():
    parts = []
    for number in range(1, 54):
        suffix = " (CANCELADA)" if number == 5 else ""
        parts.append(f"SÚMULA Nº {number} - Texto da súmula {number}.{suffix}")
    html = "<html><body>" + "\n".join(parts) + "</body></html>"
    class Response:
        content = html.encode("utf-8")
        def raise_for_status(self): return None
    class Session:
        def get(self, *args, **kwargs): return Response()
    records = collect_tcesp_sumulas(Session())
    assert len(records) == 53
    assert {int(item.numero_decisao) for item in records} == set(range(1, 54))
    assert next(item for item in records if item.numero_decisao == "5").situacao == "CANCELADA"


def test_sumula_save_record_has_dedicated_type(tmp_path: Path):
    from jurisprudencia.schema import JurisprudenciaRecord
    record = JurisprudenciaRecord(
        tribunal="TCU",
        numero_processo="Súmula TCU 247",
        numero_decisao="247",
        tipo_decisao="Súmula",
        ementa="É obrigatória a admissão da adjudicação por item.",
        url_oficial="https://pesquisa.apps.tcu.gov.br/resultado/sumula/247",
    )
    path = save_record(record, tmp_path)
    data = path.with_suffix(".json").read_text(encoding="utf-8")
    assert '"source_id": "tcu-sumulas"' in data
    assert '"tipo_documento": "sumula"' in data
    assert '"status": "vigente"' in data


def test_batch_can_disable_sumulas_for_targeted_health_checks(monkeypatch, tmp_path: Path):
    import jurisprudencia.batch as batch
    monkeypatch.setattr(batch, "collect", lambda *args, **kwargs: [])
    monkeypatch.setattr(batch, "collect_sumulas", lambda **kwargs: (_ for _ in ()).throw(AssertionError("sumulas não deveriam ser coletadas")))
    result = batch.collect_batch(
        ("tcu",),
        ("licitação",),
        1,
        output_dir=tmp_path,
        include_sumulas=False,
    )
    assert result == []


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



def test_tcu_catalog_parser_extracts_multiple_sumulas_and_pagination():
    from jurisprudencia.sumulas import _pagination_links, _parse_tcu_sumulas_page
    html = """<html><body>
    <div>SÚMULA TCU 222: Enunciado sobre normas gerais.</div>
    <div>Decisão 759/1994-Plenário</div>
    <div>SÚMULA TCU 247: Enunciado sobre parcelamento.</div>
    <div>Acórdão 1782/2004-Plenário</div>
    <a href="/resultado/todas-bases/*?pb=sumula&pagina=2">2</a>
    <a href="/resultado/todas-bases/*?pb=sumula&pagina=3">Próxima</a>
    </body></html>"""
    records = _parse_tcu_sumulas_page(html.encode("utf-8"))
    assert [item.numero_sumula for item in records] == ["222", "247"]
    links = _pagination_links(html.encode("utf-8"), "https://pesquisa.apps.tcu.gov.br/resultado/todas-bases/%2A?pb=sumula")
    assert len(links) == 2


def test_tcu_catalog_is_canonical_source_url():
    from jurisprudencia.sumulas import TCU_SUMULA_CATALOG_URL
    assert TCU_SUMULA_CATALOG_URL == "https://pesquisa.apps.tcu.gov.br/resultado/todas-bases/%2A?pb=sumula"


def test_tcu_sumula_parser_accepts_numero_marker_and_metadata_block():
    raw = """
    <html><body>
    <div>SÚMULA TCU Nº 222: As decisões do Tribunal de Contas da União devem ser acatadas.</div>
    <div>Decisão 759/1994-Plenário | RELATOR IRAM SARAIVA</div>
    <div>Área: Competência do TCU</div>
    </body></html>
    """.encode("utf-8")
    record = _parse_tcu_record_for_test(raw)
    assert record.numero_sumula == "222"
    assert record.ementa.startswith("As decisões do Tribunal de Contas da União")


def _parse_tcu_record_for_test(raw):
    from jurisprudencia.sumulas import _parse_tcu_sumulas_page
    records = _parse_tcu_sumulas_page(raw)
    assert records
    return records[0]
