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
