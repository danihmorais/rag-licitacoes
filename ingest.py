import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from fastembed import SparseTextEmbedding, TextEmbedding
from pypdf import PdfReader
from qdrant_client import QdrantClient, models

import config
from index_manifest import read_manifest, write_manifest
from metadata import embedding_metadata_prefix, extract_metadata
from chunking import build_structural_chunks
from embedding_utils import validate_embedding_inputs

PAYLOAD_INDEXES = {
    'doc_id': models.PayloadSchemaType.KEYWORD,
    'source_id': models.PayloadSchemaType.KEYWORD,
    'source': models.PayloadSchemaType.KEYWORD,
    'unit_id': models.PayloadSchemaType.KEYWORD,
    'jurisdicao': models.PayloadSchemaType.KEYWORD,
    'esfera': models.PayloadSchemaType.KEYWORD,
    'orgao': models.PayloadSchemaType.KEYWORD,
    'tribunal': models.PayloadSchemaType.KEYWORD,
    'tipo_documento': models.PayloadSchemaType.KEYWORD,
    'source_role': models.PayloadSchemaType.KEYWORD,
    'status': models.PayloadSchemaType.KEYWORD,
    'municipio': models.PayloadSchemaType.KEYWORD,
    'modalidade': models.PayloadSchemaType.KEYWORD,
    'tipo': models.PayloadSchemaType.KEYWORD,
    'regime_juridico': models.PayloadSchemaType.KEYWORD,
    'authority_level': models.PayloadSchemaType.INTEGER,
    'normative_rank': models.PayloadSchemaType.INTEGER,
    'ano': models.PayloadSchemaType.INTEGER,
    'norm_ano': models.PayloadSchemaType.INTEGER,
    'revogado': models.PayloadSchemaType.BOOL,
}

PAGE_BREAK = '\f'
CACHE_PATH = config.DB_DIR / 'ingest_cache.json'
CACHE_VERSION = 2


def sync_sources():
    if not config.RAG_SYNC_SOURCES:
        return
    script = Path(__file__).parent / 'scripts' / 'sync_sources.py'
    result = subprocess.run(
        [sys.executable, str(script), '--strict'],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            'Sincronização de fontes jurídicas incompleta. Corrija as fontes rejeitadas antes de indexar; '
            'o cache anterior foi preservado onde aplicável.'
        )


def sync_jurisprudencia():
    if not config.RAG_SYNC_JURISPRUDENCIA:
        return
    if config.JURISPRUDENCIA_QUERY:
        command = [
            sys.executable,
            '-m',
            'jurisprudencia.collector',
            '--query',
            config.JURISPRUDENCIA_QUERY,
            '--limit',
            str(config.JURISPRUDENCIA_LIMIT),
        ]
    else:
        command = [
            sys.executable,
            '-m',
            'jurisprudencia.batch',
            '--limit',
            str(config.JURISPRUDENCIA_LIMIT),
        ]
        for query in config.JURISPRUDENCIA_QUERIES:
            command.extend(['--query', query])
    if config.JURISPRUDENCIA_STRICT:
        command.append('--strict')
    if config.JURISPRUDENCIA_DETAIL:
        command.append('--detail')
    if config.JURISPRUDENCIA_WITH_CONTENT:
        command.append('--with-content')
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        if config.JURISPRUDENCIA_STRICT:
            raise RuntimeError(
                'Sincronização de jurisprudência incompleta. Corrija as fontes jurisprudenciais antes de indexar; '
                'o cache anterior foi preservado onde aplicável.'
            )
        print('Aviso: coleta de jurisprudência terminou sem novos registros; cache anterior será preservado.')


def load_documents():
    files = sorted(config.PDFS_DIR.glob('*.pdf')) + sorted(config.SOURCE_CACHE_DIR.rglob('*.txt'))
    if not files:
        print(f'Nenhum documento em {config.PDFS_DIR} nem em {config.SOURCE_CACHE_DIR}.')
        sys.exit(1)
    return files


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_cache():
    if not CACHE_PATH.exists():
        return {}
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f'Aviso: cache de ingestão inválido; reindexação será feita: {exc}')
        return {}
    if payload.get('version') != CACHE_VERSION or not isinstance(payload.get('documents'), dict):
        return {}
    return payload['documents']


def write_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f'.{CACHE_PATH.name}.', suffix='.tmp', dir=CACHE_PATH.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump({'version': CACHE_VERSION, 'documents': cache}, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, CACHE_PATH)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def extract_pages(path):
    if path.suffix.lower() == '.pdf':
        return [page.extract_text() or '' for page in PdfReader(str(path)).pages]
    return path.read_text(encoding='utf-8').split(PAGE_BREAK)


def _starts(pages):
    out, offset = [], 0
    for text in pages:
        out.append(offset)
        offset += len(text) + 1
    return out


def _page(offset, starts):
    number = 1
    for index, start in enumerate(starts, 1):
        if start <= offset:
            number = index
        else:
            break
    return number


def document_id_for(document, metadata=None):
    metadata = metadata or extract_metadata('', document)
    explicit = metadata.get('document_id')
    if explicit:
        return str(explicit)
    source_id = str(metadata.get('source_id') or 'local')
    return f'{source_id}::{document.stem}'


def build_chunks(document, pages):
    full = PAGE_BREAK.join(pages)
    meta = extract_metadata(full, document)
    doc_id = document_id_for(document, meta)
    starts = _starts(pages)
    prefix = embedding_metadata_prefix(meta)
    output = []
    for chunk in build_structural_chunks(full, config.CHUNK_SIZE, config.CHUNK_OVERLAP):
        if not chunk['text'].strip():
            continue
        start = chunk['start']
        end = start + len(chunk['text'])
        hierarchy = chunk.get('hierarchy_path') or []
        hierarchy_label = ' > '.join(str(item) for item in hierarchy)
        page_content = prefix
        if hierarchy_label:
            page_content += f' [HIERARQUIA: {hierarchy_label}]'
        page_content += '\n' + chunk.get('page_content', chunk['text'])
        embedding_text = 'passage: ' + page_content
        output.append({
            **chunk,
            'text': chunk['text'],
            'page_content': page_content,
            'embedding_text': embedding_text,
            'doc_id': doc_id,
            'source': document.name,
            'source_id': meta.get('source_id') or document.stem,
            'page': _page(start, starts),
            'page_end': _page(max(start, end - 1), starts),
            **meta,
        })
    return output


def embedding_kwargs():
    config.validate_gpu_runtime()
    return {'providers': list(config.FASTEMBED_PROVIDERS)}


def ensure_collection(client):
    if not client.collection_exists(config.COLLECTION_NAME):
        client.create_collection(
            collection_name=config.COLLECTION_NAME,
            vectors_config={
                'dense': models.VectorParams(size=config.DENSE_DIM, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={'sparse': models.SparseVectorParams()},
        )
    for field_name, field_schema in PAYLOAD_INDEXES.items():
        client.create_payload_index(
            collection_name=config.COLLECTION_NAME,
            field_name=field_name,
            field_schema=field_schema,
            wait=True,
        )


def _filter_for_doc_id(doc_id):
    return models.Filter(
        must=[models.FieldCondition(key='doc_id', match=models.MatchValue(value=doc_id))]
    )


def _point_ids_for_filter(client, filters):
    ids = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=config.COLLECTION_NAME,
            scroll_filter=filters,
            limit=256,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        for point in points:
            ids.update(
                value for value in (
                    getattr(point, 'id', None),
                    (point.payload or {}).get('source') if getattr(point, 'payload', None) else None,
                )
                if value is not None
            )
        if offset is None:
            break
    return ids


def source_point_ids(client, doc_id, legacy_source=None):
    ids = _point_ids_for_filter(client, _filter_for_doc_id(doc_id))
    if legacy_source and str(legacy_source) != str(doc_id):
        ids.update(
            _point_ids_for_filter(
                client,
                models.Filter(
                    must=[models.FieldCondition(
                        key='source',
                        match=models.MatchValue(value=str(legacy_source)),
                    )]
                ),
            )
        )
    return ids


def delete_point_ids(client, point_ids):
    point_ids = list(point_ids)
    if not point_ids:
        return
    for start in range(0, len(point_ids), config.QDRANT_UPSERT_BATCH_SIZE):
        batch = point_ids[start:start + config.QDRANT_UPSERT_BATCH_SIZE]
        client.delete(
            collection_name=config.COLLECTION_NAME,
            points_selector=models.PointIdsList(points=batch),
            wait=True,
        )


def upsert_points(client, points):
    points = list(points)
    for start in range(0, len(points), config.QDRANT_UPSERT_BATCH_SIZE):
        client.upsert(
            collection_name=config.COLLECTION_NAME,
            points=points[start:start + config.QDRANT_UPSERT_BATCH_SIZE],
            wait=True,
        )


def delete_doc(client, doc_id, legacy_source=None):
    delete_point_ids(client, source_point_ids(client, doc_id, legacy_source=legacy_source))


def _restore_points(client, points):
    if not points:
        return
    restored = [
        models.PointStruct(id=point.id, vector=point.vector, payload=point.payload or {})
        for point in points
    ]
    upsert_points(client, restored)


def replace_document_points(client, doc_id, new_points, legacy_source=None):
    if not new_points:
        raise ValueError(f'Nenhum chunk produzido para {doc_id}.')
    old_points = []
    seen_ids = set()
    filters = [_filter_for_doc_id(doc_id)]
    if legacy_source and str(legacy_source) != str(doc_id):
        filters.append(models.Filter(
            must=[models.FieldCondition(key='source', match=models.MatchValue(value=str(legacy_source)))]
        ))
    for point_filter in filters:
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=config.COLLECTION_NAME,
                scroll_filter=point_filter,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            for point in points:
                if point.id not in seen_ids:
                    seen_ids.add(point.id)
                    old_points.append(point)
            if offset is None:
                break
    old_ids = {point.id for point in old_points}
    try:
        delete_point_ids(client, old_ids)
        upsert_points(client, new_points)
    except Exception as exc:
        try:
            delete_point_ids(client, {point.id for point in new_points})
            _restore_points(client, old_points)
        except Exception as rollback_exc:
            raise RuntimeError(
                f'Falha na substituição de {doc_id} e rollback também falhou: {rollback_exc}'
            ) from exc
        raise RuntimeError(f'Falha na substituição de {doc_id}; versão anterior restaurada.') from exc
    return old_ids


def prune_stale_documents(client, active_names, *, delete=True, return_ids=False):
    if not config.RAG_PRUNE_STALE:
        return [] if return_ids else 0
    if not client.collection_exists(config.COLLECTION_NAME):
        return [] if return_ids else 0
    indexed_ids = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=config.COLLECTION_NAME,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            doc_id = payload.get('doc_id') or payload.get('source')
            if doc_id:
                indexed_ids.add(str(doc_id))
        if offset is None:
            break
    stale = sorted(indexed_ids - {str(item) for item in active_names})
    if delete:
        for doc_id in stale:
            delete_doc(client, doc_id)
    return stale if return_ids else len(stale)


def validate_dense_vectors(vectors, expected):
    for index, vector in enumerate(vectors):
        if len(vector) != config.DENSE_DIM:
            raise RuntimeError(
                f'embedding denso com dimensão inválida no chunk {index}: '
                f'{len(vector)} != {config.DENSE_DIM}'
            )
        norm_sq = 0.0
        for value in vector:
            numeric = float(value)
            if not math.isfinite(numeric):
                raise RuntimeError(f'embedding denso contém valor não finito no chunk {index}.')
            norm_sq += numeric * numeric
        if norm_sq <= 0.0:
            raise RuntimeError(f'embedding denso nulo no chunk {index}.')
    if len(vectors) != expected:
        raise RuntimeError(f'quantidade de embeddings densa inválida: {len(vectors)} != {expected}')


def main():
    config.ensure_directories()
    sync_sources()
    sync_jurisprudencia()
    files = load_documents()
    client = QdrantClient(path=str(config.QDRANT_PATH))
    manifest = read_manifest()
    if manifest is not None:
        from index_manifest import validate_manifest
        validate_manifest()
    elif client.collection_exists(config.COLLECTION_NAME) and client.count(config.COLLECTION_NAME, exact=True).count:
        raise RuntimeError('Índice sem manifest. Remova db/qdrant e reindexe.')

    dense = TextEmbedding(model_name=config.DENSE_MODEL, max_length=config.DENSE_MAX_TOKENS, **embedding_kwargs())
    sparse = SparseTextEmbedding(model_name=config.SPARSE_MODEL, **embedding_kwargs())
    ensure_collection(client)
    active_names = {document_id_for(document) for document in files}
    stale_removed = prune_stale_documents(client, active_names, delete=False, return_ids=True)
    deleted_manifest = []
    cache, errors, skipped = read_cache(), [], 0
    document_manifest = {}
    revocations = []

    for document in files:
        digest = file_hash(document)
        document_meta = extract_metadata('', document)
        doc_id = document_id_for(document, document_meta)
        count_filter = _filter_for_doc_id(doc_id)
        entry = cache.get(document.name)
        indexed_count = client.count(
            config.COLLECTION_NAME,
            count_filter=count_filter,
            exact=True,
        ).count
        if (
            isinstance(entry, dict)
            and entry.get('sha256') == digest
            and int(entry.get('chunks') or 0) == indexed_count
            and indexed_count > 0
        ):
            skipped += 1
            document_manifest[doc_id] = {
                'sha256': digest,
                'chunks': indexed_count,
                'source': document.name,
                'source_id': document_meta.get('source_id'),
                'regime_juridico': document_meta.get('regime_juridico'),
                'status': document_meta.get('status'),
            }
            if document_meta.get('revogado') or document_meta.get('status') == 'revogado':
                revocations.append({'doc_id': doc_id, 'source': document.name, 'status': document_meta.get('status'), 'effective_to': document_meta.get('effective_to')})
            continue
        try:
            pages = extract_pages(document)
            chunks = build_chunks(document, pages)
            if not chunks:
                print('Aviso: sem texto em', document.name)
                errors.append(document.name)
                continue
            embedding_inputs = [item['embedding_text'] for item in chunks]
            validate_embedding_inputs(dense, embedding_inputs, label=document.name)
            dense_vectors = list(dense.embed(embedding_inputs))
            validate_dense_vectors(dense_vectors, len(chunks))
            sparse_vectors = list(sparse.embed([item['page_content'] for item in chunks]))
            if len(sparse_vectors) != len(chunks):
                raise RuntimeError(
                    f'quantidade de embeddings esparsas inválida: {len(sparse_vectors)} != {len(chunks)}'
                )
            points = []
            for index, item in enumerate(chunks):
                point_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{doc_id}|{item['unit_id']}|{item['chunk_index']}|{item['page_content']}",
                    )
                )
                points.append(
                    models.PointStruct(
                        id=point_id,
                        vector={
                            'dense': dense_vectors[index].tolist(),
                            'sparse': models.SparseVector(
                                indices=sparse_vectors[index].indices.tolist(),
                                values=sparse_vectors[index].values.tolist(),
                            ),
                        },
                        payload=item,
                    )
                )
            replace_document_points(client, doc_id, points, legacy_source=document.name)
            cache[document.name] = {'sha256': digest, 'chunks': len(points), 'doc_id': doc_id, 'source_id': document_meta.get('source_id')}
            document_manifest[doc_id] = {
                'sha256': digest,
                'chunks': len(points),
                'source': document.name,
                'source_id': document_meta.get('source_id'),
                'regime_juridico': document_meta.get('regime_juridico'),
                'status': document_meta.get('status'),
            }
            if document_meta.get('revogado') or document_meta.get('status') == 'revogado':
                revocations.append({'doc_id': doc_id, 'source': document.name, 'status': document_meta.get('status'), 'effective_to': document_meta.get('effective_to')})
            write_cache(cache)
            print(f'Indexado: {document.name} ({len(points)} chunks)')
        except Exception as exc:
            print(f'ERRO ao indexar {document.name}: {exc}. A versão anterior permanece disponível quando o upsert falhar.')
            errors.append(document.name)

    write_cache(cache)
    total = client.count(config.COLLECTION_NAME, exact=True).count
    print('Total:', total, '| pulados (sem alteração):', skipped, '| fontes obsoletas removidas:', stale_removed)
    if errors:
        print('Arquivos com erro (não indexados):', ', '.join(errors))
        print('Manifesto não atualizado porque a indexação terminou parcialmente; execute novamente após corrigir as fontes.')
        return 1
    for name, entry in cache.items():
        if isinstance(entry, dict) and entry.get('doc_id') and name in {document.name for document in files}:
            document_manifest.setdefault(str(entry['doc_id']), {**entry, 'source': name})
    for doc_id in stale_removed:
        delete_doc(client, doc_id)
        deleted_manifest.append({
            'doc_id': doc_id,
            'reason': 'stale',
            'timestamp': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        })
    write_manifest(
        documents=document_manifest,
        deletions=deleted_manifest,
        revocations=revocations,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
