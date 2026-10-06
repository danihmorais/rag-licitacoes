import ingest


def test_legacy_cache_is_invalid_after_cache_version_bump():
    entry = {
        "sha256": "abc",
        "metadata_fingerprint": "new",
        "chunks": 7,
        "_cache_version": 4,
    }
    assert not ingest.cache_entry_is_valid(entry, "abc", "new", 7)


def test_current_cache_requires_metadata_fingerprint():
    entry = {
        "sha256": "abc",
        "metadata_fingerprint": "new",
        "chunks": 7,
        "_cache_version": 6,
    }
    assert ingest.cache_entry_is_valid(entry, "abc", "new", 7)
    assert not ingest.cache_entry_is_valid(entry, "abc", "old", 7)
