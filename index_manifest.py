import json
import config

class IndexCompatibilityError(RuntimeError):
    pass


def current_manifest():
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
        'schema': 'unit_id/chunk_index/page_span/source_role/status/authority_level/source_id/document_hash',
    }


def read_manifest():
    return json.loads(config.INDEX_MANIFEST_PATH.read_text(encoding='utf-8')) if config.INDEX_MANIFEST_PATH.exists() else None


def write_manifest():
    config.INDEX_MANIFEST_PATH.write_text(json.dumps(current_manifest(), ensure_ascii=False, indent=2), encoding='utf-8')


def validate_manifest():
    stored = read_manifest()
    if stored is None:
        raise IndexCompatibilityError('O índice existe, mas não há index_manifest.json. Reindexe o banco.')
    expected = current_manifest()
    differences = {key: (stored.get(key), value) for key, value in expected.items() if stored.get(key) != value}
    if differences:
        details = ', '.join(f'{key}: índice={old!r}, configuração={new!r}' for key, (old, new) in differences.items())
        raise IndexCompatibilityError('Configuração incompatível com o índice: ' + details + '. Reindexe o banco.')
