
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


def test_stj_caches_resources_and_payloads_across_variants():
    adapter = STJAdapter(object())
    adapter.orgao_datasets = {'FIRST': 'dataset-first', 'SECOND': 'dataset-second'}
    resource_calls = []
    json_calls = []
    resources = {
        'dataset-first': [{'url': 'https://example.test/first.json', 'name': '20260901'}],
        'dataset-second': [{'url': 'https://example.test/second.json', 'name': '20260901'}],
    }
    payloads = {
        'https://example.test/first.json': [{'id': 'first', 'numeroProcesso': 'first/1', 'ementa': 'licitação'}],
        'https://example.test/second.json': [{'id': 'second', 'numeroProcesso': 'second/1', 'ementa': 'contrato'}],
    }

    def fake_resources(dataset):
        resource_calls.append(dataset)
        return resources[dataset]

    def fake_json(url, **params):
        json_calls.append(url)
        return payloads[url]

    adapter._resources = fake_resources
    adapter._json = fake_json
    records = adapter.search('licitação contrato', 3, detail=True)

    assert len(records) == 2
    assert resource_calls == ['dataset-first', 'dataset-second']
    assert sorted(json_calls) == ['https://example.test/first.json', 'https://example.test/second.json']
    assert all(record.inteiro_teor for record in records)


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
