from pathlib import Path

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
    ingest.validate_dense_vectors([[0.0] * ingest.config.DENSE_DIM], 1)


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
