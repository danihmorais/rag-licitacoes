
from pathlib import Path

import jurisprudencia.batch as batch
import jurisprudencia.collector as collector
import jurisprudencia.sumulas as sumulas
from jurisprudencia.collector import STJAdapter, _extract_process
from jurisprudencia.schema import JurisprudenciaRecord


def _record(tribunal='TCU', numero='1'):
    return JurisprudenciaRecord(
        tribunal=tribunal,
        numero_processo=f'{tribunal.lower()}-{numero}',
        ementa='Licitação administrativa.',
        url_oficial=f'https://example.test/{tribunal.lower()}/{numero}',
    )


def test_collect_isolates_invalid_record_during_persistence(monkeypatch, tmp_path: Path):
    invalid = JurisprudenciaRecord(
        tribunal='TCU',
        numero_processo='',
        ementa='Registro sem processo.',
        url_oficial='https://example.test/bad',
    )
    valid = _record('TCU', 'ok')

    class Adapter:
        def search(self, *args, **kwargs):
            return [invalid, valid]

    monkeypatch.setattr(collector, 'make_session', lambda: object())
    monkeypatch.setattr(collector, 'adapters', lambda session: {'tcu': Adapter()})

    records = collector.collect(('tcu',), 'licitação', 2, output_dir=tmp_path, persist=True, strict=False)
    assert records == [valid]
    assert len(list(tmp_path.glob('*.json'))) == 1


def test_batch_validates_before_document_key(monkeypatch, tmp_path: Path):
    invalid = JurisprudenciaRecord(
        tribunal='TCU',
        numero_processo='',
        ementa='Registro inválido.',
        url_oficial='https://example.test/bad',
    )
    valid = _record('TCU', 'ok')

    monkeypatch.setattr(batch, 'collect', lambda *args, **kwargs: [invalid, valid])
    records = batch.collect_batch(
        ('tcu',),
        ('licitação',),
        1,
        output_dir=tmp_path,
        strict=False,
        min_records_per_tribunal=1,
        include_sumulas=False,
    )
    assert records == [valid]


def test_stj_scon_search_uses_direct_http_post(monkeypatch):
    html = '''<html><body>
      <div class="row itemlistadocumentos p-2">
        <div class="col-sm-3">
          <h4>Processo</h4>
          <div><a href="/SCON/jurisprudencia/doc.jsp?ementa=LICITACAO&i=1">REsp&nbsp;1</a></div>
          <div class="small">(ACORDAO)</div>
          <div>Ministro X</div>
          <div>DJe 01/10/2026</div>
          <div>Decisao: 30/09/2026</div>
        </div>
        <div class="col-sm-8"><div class="clsEmentaCompleta">Licitação administrativa.</div></div>
      </div>
    </body></html>'''.encode("iso-8859-1")

    class Session:
        def __init__(self):
            self.calls = []

        def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            return type("Response", (), {
                "content": html,
                "url": STJAdapter.search_endpoint,
                "raise_for_status": lambda self: None,
            })()

    session = Session()
    records = STJAdapter(session).search("licitação", 1)

    assert len(records) == 1
    assert records[0].tribunal == "STJ"
    assert records[0].numero_processo == "REsp 1"
    assert session.calls[0][0] == "POST"
    assert session.calls[0][1] == STJAdapter.search_endpoint


def test_tcu_sumula_collection_forwards_custom_session():
    captured = {}

    class Response:
        content = b"KEY,NUMERO,ENUNCIADO,VIGENTE\nS1,222,Enunciado,SIM\n"

        def raise_for_status(self):
            return None

    class FakeSession:
        def get(self, url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return Response()

    records = sumulas.collect_tcu_sumulas(session=FakeSession())
    assert [record.numero_sumula for record in records] == ["222"]
    assert captured["url"] == sumulas.TCU_SUMULA_CSV_URL
    assert captured["kwargs"]["allow_redirects"] is True


def test_tcesp_strict_does_not_require_contiguous_sumula_numbers(monkeypatch):
    records = [
        JurisprudenciaRecord(
            tribunal='TCESP',
            tipo_documento='sumula',
            numero_sumula=str(number),
            tipo_decisao='Súmula',
            ementa=f'Enunciado {number}.',
        )
        for number in list(range(1, 52)) + [53]
    ]

    monkeypatch.setattr(sumulas, 'collect_tcesp_sumulas', lambda: records)
    result = sumulas.collect_sumulas(tribunals=('tcesp',), strict=True)

    assert len(result['tcesp']) == 52
    assert {int(item.numero_sumula) for item in result['tcesp']} == set(range(1, 52)) | {53}


def test_extract_process_accepts_generic_three_part_numbers():
    assert _extract_process('Processo 1000/1234/26') == '1000/1234/26'
