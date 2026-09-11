import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

from fastembed import SparseTextEmbedding, TextEmbedding
from pypdf import PdfReader
from qdrant_client import QdrantClient, models

import config
from chunking import build_structural_chunks
from index_manifest import read_manifest, write_manifest
from metadata import extract_metadata

PAGE_BREAK = '\f'
CACHE_PATH = config.DB_DIR / 'ingest_cache.json'


def sync_sources():
    if not config.RAG_SYNC_SOURCES:
        return
    script = Path(__file__).parent / 'scripts' / 'sync_sources.py'
    result = subprocess.run([sys.executable, str(script)], check=False)
    if result.returncode != 0:
        print('Aviso: sincronização de fontes terminou com falhas; cache anterior será preservado.')


def sync_jurisprudencia():
    if not config.RAG_SYNC_JURISPRUDENCIA:
        return
    command = [sys.executable, '-m', 'jurisprudencia.collector', '--query', config.JURISPRUDENCIA_QUERY, '--limit', str(config.JURISPRUDENCIA_LIMIT)]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print('Aviso: coleta de jurisprudência terminou sem novos registros; cache anterior será preservado.')


def load_documents():
    files = sorted(config.PDFS_DIR.glob('*.pdf')) + sorted(config.SOURCE_CACHE_DIR.rglob('*.txt'))
    if not files:
        print(f'Nenhum documento em {config.PDFS_DIR} nem em {config.SOURCE_CACHE_DIR}.')
        sys.exit(1)
    return files


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read_cache():
    return json.loads(CACHE_PATH.read_text(encoding='utf-8')) if CACHE_PATH.exists() else {}


def write_cache(cache):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')


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
    for i, start in enumerate(starts, 1):
        if start <= offset:
            number = i
        else:
            break
    return number


def build_chunks(document, pages, digest):
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
            'document_hash': digest,
            'page': _page(start, starts),
            'page_end': _page(max(start, end - 1), starts),
            **meta,
        })
    return output


def embedding_kwargs():
    return {'providers': config.FASTEMBED_PROVIDERS} if config.FASTEMBED_PROVIDERS else {}


def ensure_collection(client):
    if not client.collection_exists(config.COLLECTION_NAME):
        client.create_collection(
            collection_name=config.COLLECTION_NAME,
            vectors_config={'dense': models.VectorParams(size=config.DENSE_DIM, distance=models.Distance.COSINE)},
            sparse_vectors_config={'sparse': models.SparseVectorParams()},
        )


def delete_old_versions(client, name, digest):
    """Remove versões antigas somente depois que a nova versão foi indexada."""
    client.delete(
        collection_name=config.COLLECTION_NAME,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[models.FieldCondition(key='source', match=models.MatchValue(value=name))],
                must_not=[models.FieldCondition(key='document_hash', match=models.MatchValue(value=digest))],
            )
        ),
    )


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
    elif client.collection_exists(config.COLLECTION_NAME) and client.count(config.COLLECTION_NAME).count:
        raise RuntimeError('Índice sem manifest. Remova db/qdrant e reindexe.')

    dense = TextEmbedding(model_name=config.DENSE_MODEL, **embedding_kwargs())
    sparse = SparseTextEmbedding(model_name=config.SPARSE_MODEL, **embedding_kwargs())
    ensure_collection(client)
    cache, errors, skipped = read_cache(), [], 0

    for document in files:
        digest = file_hash(document)
        count_filter = models.Filter(must=[
            models.FieldCondition(key='source', match=models.MatchValue(value=document.name)),
            models.FieldCondition(key='document_hash', match=models.MatchValue(value=digest)),
        ])
        if cache.get(document.name) == digest and client.count(config.COLLECTION_NAME, count_filter=count_filter).count:
            skipped += 1
            continue
        try:
            pages = extract_pages(document)
            chunks = build_chunks(document, pages, digest)
            if not chunks:
                print('Aviso: sem texto em', document.name)
                continue
            dense_vectors = list(dense.embed(['passage: ' + item['text'] for item in chunks]))
            sparse_vectors = list(sparse.embed([item['text'] for item in chunks]))
            points = []
            for index, item in enumerate(chunks):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document.name}|{digest}|{item['unit_id']}|{item['chunk_index']}|{item['text']}"))
                points.append(models.PointStruct(
                    id=point_id,
                    vector={
                        'dense': dense_vectors[index].tolist(),
                        'sparse': models.SparseVector(indices=sparse_vectors[index].indices.tolist(), values=sparse_vectors[index].values.tolist()),
                    },
                    payload=item,
                ))

            # Primeiro grava a nova versão. Só depois remove a anterior.
            client.upsert(collection_name=config.COLLECTION_NAME, points=points)
            delete_old_versions(client, document.name, digest)
            cache[document.name] = digest
            print(f'Indexado: {document.name} ({len(points)} chunks)')
        except Exception as exc:
            print(f'ERRO ao indexar {document.name}: {exc}. Versão anterior, se existente, foi preservada.')
            errors.append(document.name)

    write_cache(cache)
    write_manifest()
    print('Total:', client.count(config.COLLECTION_NAME).count, '| pulados (sem alteração):', skipped)
    if errors:
        print('Arquivos com erro (versão anterior preservada):', ', '.join(errors))


if __name__ == '__main__':
    main()
