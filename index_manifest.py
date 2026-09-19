import hashlib
import json
import os
import tempfile
from pathlib import Path

import config


class IndexCompatibilityError(RuntimeError):
    pass


def chunking_algorithm_sha256():
    path = Path(__file__).with_name('chunking.py')
    return hashlib.sha256(path.read_bytes()).hexdigest()


COMPATIBILITY_KEYS = (
    'index_version', 'collection_name', 'dense_model', 'dense_dim', 'dense_prefix_document',
    'dense_prefix_query', 'sparse_model', 'rerank_model', 'chunk_size', 'chunk_overlap',
    'chunking_algorithm_sha256', 'dense_max_tokens', 'payload_indexes', 'schema',
    'manifest_schema_version',
)


def current_manifest(documents=None, deletions=None, revocations=None):
    return {
        'index_version': config.INDEX_VERSION,
        'collection_name': config.COLLECTION_NAME,
        'dense_model': config.DENSE_MODEL,
        'dense_dim': config.DENSE_DIM,
        'dense_prefix_document': 'passage:',
        'dense_prefix_query': 'query:',
        'sparse_model': config.SPARSE_MODEL,
        'rerank_model': config.RERANK_MODEL,
        'chunk_size': config.CHUNK_SIZE,
        'chunk_overlap': config.CHUNK_OVERLAP,
        'context_neighbors': config.CONTEXT_NEIGHBORS,
        'max_context_chars': config.MAX_CONTEXT_CHARS,
        'chunking_algorithm_sha256': chunking_algorithm_sha256(),
        'dense_max_tokens': config.DENSE_MAX_TOKENS,
        'payload_indexes': config.QDRANT_PAYLOAD_INDEXES,
        'schema': 'doc_id/unit_id/chunk_index/page_span/page_uncertain/source_role/status/authority_level/source_id/document_hash/regime_juridico/tipo_documento/numero_sumula/text_origin/extraction_confidence/page_extraction/page_content/embedding_text',
        'manifest_schema_version': 5,
        'documents': documents or {},
        'deletions': deletions or [],
        'revocations': revocations or [],
    }


def read_manifest():
    if not config.INDEX_MANIFEST_PATH.exists():
        return None
    try:
        return json.loads(config.INDEX_MANIFEST_PATH.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IndexCompatibilityError(
            f'Manifesto do índice inválido ou corrompido: {config.INDEX_MANIFEST_PATH}. Reindexe o banco.'
        ) from exc


def _atomic_write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def write_manifest(documents=None, deletions=None, revocations=None):
    existing = read_manifest() or {}
    merged_documents = documents if documents is not None else existing.get('documents', {})
    if not isinstance(merged_documents, dict):
        merged_documents = {}
    old_deletions = existing.get('deletions') if isinstance(existing.get('deletions'), list) else []
    old_revocations = existing.get('revocations') if isinstance(existing.get('revocations'), list) else []
    merged_deletions = list(old_deletions) + list(deletions or [])
    merged_revocations = list(old_revocations) + list(revocations or [])
    _atomic_write_json(
        config.INDEX_MANIFEST_PATH,
        current_manifest(
            documents=merged_documents,
            deletions=merged_deletions[-2000:],
            revocations=merged_revocations[-2000:],
        ),
    )


def validate_manifest():
    stored = read_manifest()
    if stored is None:
        raise IndexCompatibilityError('O índice existe, mas não há index_manifest.json. Reindexe o banco.')
    expected = current_manifest()
    differences = {key: (stored.get(key), expected.get(key)) for key in COMPATIBILITY_KEYS if stored.get(key) != expected.get(key)}
    if differences:
        details = ', '.join(f'{key}: índice={old!r}, configuração={new!r}' for key, (old, new) in differences.items())
        raise IndexCompatibilityError('Configuração incompatível com o índice: ' + details + '. Reindexe o banco.')
