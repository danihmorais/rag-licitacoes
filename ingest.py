import hashlib
import json
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
from metadata import extract_metadata
from chunking import build_structural_chunks

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


def build_chunks(document, pages):
    full = PAGE_BREAK.join(pages)
    meta = extract_metadata(full, document)
    starts = _starts(pages)
    output = []
    for chunk in build_structural_chunks(full, config.CHUNK_SIZE, config.CHUNK_OVERLAP):
        if not chunk['text'].strip():
            continue
        start = chunk['start']
        end = start + len(chunk['text'])
        output.append({
            **chunk,
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


def delete_doc(client, name):
    client.delete(
        collection_name=config.COLLECTION_NAME,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[models.FieldCondition(key='source', match=models.MatchValue(value=name))]
            )
        ),
        wait=True,
    )


def source_point_ids(client, name):
    ids = set()
    offset = None
    source_filter = models.Filter(must=[models.FieldCondition(key='source', match=models.MatchValue(value=name))])
    while True:
        points, offset = client.scroll(
            collection_name=config.COLLECTION_NAME,
            scroll_filter=source_filter,
            limit=256,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        ids.update(point.id for point in points)
        if offset is None:
            break
    return ids


def delete_point_ids(client, point_ids):
    point_ids = list(point_ids)
    if not point_ids:
        return
    client.delete(
        collection_name=config.COLLECTION_NAME,
        points_selector=models.PointIdsList(points=point_ids),
        wait=True,
    )


def prune_stale_documents(client, active_names):
    if not config.RAG_PRUNE_STALE:
        return 0
    if not client.collection_exists(config.COLLECTION_NAME):
        return 0
    indexed_names = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=config.COLLECTION_NAME,
            limit=256,
            offset=offset,
            with_payload=['source'],
            with_vectors=False,
        )
        for point in points:
            source = point.payload.get('source') if point.payload else None
            if source:
                indexed_names.add(str(source))
        if offset is None:
            break
    stale = sorted(indexed_names - active_names)
    for name in stale:
        delete_doc(client, name)
    return len(stale)


def validate_dense_vectors(vectors, expected):
    for index, vector in enumerate(vectors):
        if len(vector) != config.DENSE_DIM:
            raise RuntimeError(
                f'embedding denso com dimensão inválida no chunk {index}: '
                f'{len(vector)} != {config.DENSE_DIM}'
            )
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

    dense = TextEmbedding(model_name=config.DENSE_MODEL, **embedding_kwargs())
    sparse = SparseTextEmbedding(model_name=config.SPARSE_MODEL, **embedding_kwargs())
    ensure_collection(client)
    active_names = {document.name for document in files}
    stale_removed = prune_stale_documents(client, active_names)
    cache, errors, skipped = read_cache(), [], 0

    for document in files:
        digest = file_hash(document)
        count_filter = models.Filter(
            must=[models.FieldCondition(key='source', match=models.MatchValue(value=document.name))]
        )
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
            continue
        try:
            pages = extract_pages(document)
            chunks = build_chunks(document, pages)
            if not chunks:
                print('Aviso: sem texto em', document.name)
                errors.append(document.name)
                continue
            old_ids = source_point_ids(client, document.name)
            dense_vectors = list(dense.embed(['passage: ' + item['text'] for item in chunks]))
            validate_dense_vectors(dense_vectors, len(chunks))
            sparse_vectors = list(sparse.embed([item['text'] for item in chunks]))
            if len(sparse_vectors) != len(chunks):
                raise RuntimeError(
                    f'quantidade de embeddings esparsas inválida: {len(sparse_vectors)} != {len(chunks)}'
                )
            points = []
            for index, item in enumerate(chunks):
                point_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{document.name}|{item['unit_id']}|{item['chunk_index']}|{item['text']}",
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
            new_ids = {point.id for point in points}
            client.upsert(collection_name=config.COLLECTION_NAME, points=points, wait=True)
            delete_point_ids(client, old_ids - new_ids)
            cache[document.name] = {'sha256': digest, 'chunks': len(points)}
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
    write_manifest()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
