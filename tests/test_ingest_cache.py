import ingest


def test_legacy_cache_remains_valid_for_non_semantic_document():
    entry = {
        "sha256": "abc",
        "metadata_fingerprint": "old",
        "chunks": 7,
        "_cache_version": 4,
    }
    assert ingest.legacy_cache_entry_is_reusable(entry, "abc", 7)
    assert ingest.cache_entry_is_valid(
        entry,
        "abc",
        "new",
        7,
        semantic_candidate=False,
    )


def test_legacy_cache_is_forced_to_reindex_for_semantic_document():
    entry = {
        "sha256": "abc",
        "metadata_fingerprint": "old",
        "chunks": 7,
        "_cache_version": 4,
    }
    assert not ingest.cache_entry_is_valid(
        entry,
        "abc",
        "new",
        7,
        semantic_candidate=True,
    )


def test_current_cache_requires_metadata_fingerprint():
    entry = {
        "sha256": "abc",
        "metadata_fingerprint": "new",
        "chunks": 7,
        "_cache_version": 5,
    }
    assert ingest.cache_entry_is_valid(
        entry,
        "abc",
        "new",
        7,
        semantic_candidate=False,
    )
    assert not ingest.cache_entry_is_valid(
        entry,
        "abc",
        "old",
        7,
        semantic_candidate=False,
    )
