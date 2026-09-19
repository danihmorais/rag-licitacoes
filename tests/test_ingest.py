from pathlib import Path

import pytest

import ingest


class FakeClient:
    def __init__(self):
        self.deleted = []

    def collection_exists(self, name):
        return True

    def scroll(self, **kwargs):
        return [type('Point', (), {'payload': {'source': 'old.txt'}})()], None

    def delete(self, **kwargs):
        self.deleted.append(kwargs)


def test_cache_round_trip_and_legacy_invalidation(tmp_path: Path, monkeypatch):
    path = tmp_path / 'ingest_cache.json'
    monkeypatch.setattr(ingest, 'CACHE_PATH', path)
    value = {'doc.txt': {'sha256': 'abc', 'chunks': 3}}
    ingest.write_cache(value)
    assert ingest.read_cache() == value
    path.write_text('{"doc.txt": "legacy-digest"}', encoding='utf-8')
    assert ingest.read_cache() == {}


def test_validate_dense_vectors_accepts_expected_shape():
    ingest.validate_dense_vectors([[1.0] + [0.0] * (ingest.config.DENSE_DIM - 1)], 1)


def test_validate_dense_vectors_rejects_wrong_dimension():
    wrong = [[0.0] * (ingest.config.DENSE_DIM - 1)]
    try:
        ingest.validate_dense_vectors(wrong, 1)
    except RuntimeError as exc:
        assert 'dimensão inválida' in str(exc)
    else:
        raise AssertionError('dimensão inválida não foi rejeitada')


def test_prune_stale_documents_removes_sources_missing_from_corpus():
    client = FakeClient()
    removed = ingest.prune_stale_documents(client, {'active.txt'})
    assert removed == 1
    assert len(client.deleted) == 1


def test_sync_jurisprudencia_strict_failure_is_fatal(monkeypatch):
    monkeypatch.setattr(ingest.config, 'RAG_SYNC_JURISPRUDENCIA', True)
    monkeypatch.setattr(ingest.config, 'JURISPRUDENCIA_STRICT', True)
    monkeypatch.setattr(ingest.subprocess, 'run', lambda *args, **kwargs: type('Result', (), {'returncode': 1})())
    with pytest.raises(RuntimeError, match='jurisprudência'):
        ingest.sync_jurisprudencia()



class UpsertClient:
    def __init__(self):
        self.calls = []
        self.indexes = []

    def upsert(self, **kwargs):
        self.calls.append(kwargs['points'])

    def create_payload_index(self, **kwargs):
        self.indexes.append(kwargs)


def test_upsert_points_uses_bounded_batches(monkeypatch):
    monkeypatch.setattr(ingest.config, 'QDRANT_UPSERT_BATCH_SIZE', 2)
    client = UpsertClient()
    ingest.upsert_points(client, [1, 2, 3, 4, 5])
    assert [len(batch) for batch in client.calls] == [2, 2, 1]


def test_ensure_collection_creates_payload_indexes(monkeypatch):
    class CollectionClient(UpsertClient):
        def collection_exists(self, name):
            return False

        def create_collection(self, **kwargs):
            self.collection = kwargs

    client = CollectionClient()
    ingest.ensure_collection(client)
    fields = {item['field_name']: item['field_schema'] for item in client.indexes}
    assert fields['doc_id'] == ingest.models.PayloadSchemaType.KEYWORD
    assert fields['ano'] == ingest.models.PayloadSchemaType.INTEGER
    assert fields['revogado'] == ingest.models.PayloadSchemaType.BOOL


def test_metadata_fingerprint_changes_when_metadata_source_or_sidecar_changes(tmp_path: Path):
    document = tmp_path / 'documento.txt'
    document.write_text('texto', encoding='utf-8')
    metadata_path = Path(ingest.__file__).with_name('metadata.py')
    original_metadata = metadata_path.read_bytes()
    try:
        first = ingest.metadata_fingerprint(document)
        document.with_suffix('.json').write_text('{"status":"vigente"}', encoding='utf-8')
        second = ingest.metadata_fingerprint(document)
        assert first != second
        metadata_path.write_bytes(original_metadata + b'\n')
        third = ingest.metadata_fingerprint(document)
        assert second != third
    finally:
        metadata_path.write_bytes(original_metadata)


def test_build_chunks_preserves_page_extraction_quality(tmp_path: Path):
    document = tmp_path / 'documento.txt'
    document.write_text('Art. 1º Texto nativo.\\fTexto obtido por OCR.', encoding='utf-8')
    page_records = [
        {'page': 1, 'text': 'Art. 1º Texto nativo.', 'text_origin': 'native', 'extraction_confidence': 1.0},
        {'page': 2, 'text': 'Texto obtido por OCR.', 'text_origin': 'ocr', 'extraction_confidence': 0.42},
    ]
    chunks = ingest.build_chunks(document, [item['text'] for item in page_records], page_records=page_records)
    assert chunks
    assert {chunk['text_origin'] for chunk in chunks} <= {'native', 'ocr', 'mixed'}
    assert all('page_extraction' in chunk for chunk in chunks)


def test_native_extraction_confidence_penalizes_empty_and_malformed_text():
    assert ingest._native_extraction_confidence('texto jurídico consistente ' * 20) > 0.8
    assert ingest._native_extraction_confidence('') == 0.0


def test_build_chunks_uses_e5_passage_prefix_and_real_newline(tmp_path: Path):
    document = tmp_path / 'documento.txt'
    document.write_text('Art. 1º Regra de licitação.', encoding='utf-8')
    chunks = ingest.build_chunks(document, ['Art. 1º Regra de licitação.'])
    assert chunks
    assert '\\n' not in chunks[0]['page_content']
    assert chunks[0]['embedding_text'].startswith('passage: ')
