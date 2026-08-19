import sys
import uuid

from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient, models
from fastembed import TextEmbedding, SparseTextEmbedding

import config
from index_manifest import read_manifest, write_manifest
from metadata import extract_metadata


def load_pdfs():
    pdf_files = sorted(config.PDFS_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"Nenhum PDF encontrado em {config.PDFS_DIR}. Coloque os arquivos ali e rode de novo.")
        sys.exit(1)
    return pdf_files


def extract_pages(pdf_path):
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def build_chunks(pdf_path, pages):
    full_text = "\n".join(pages)
    doc_metadata = extract_metadata(full_text, pdf_path)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )

    chunks = []
    for page_num, page_text in enumerate(pages, start=1):
        if not page_text.strip():
            continue
        for piece in splitter.split_text(page_text):
            chunks.append({
                "text": piece,
                "source": pdf_path.name,
                "page": page_num,
                **doc_metadata,
            })
    return chunks, doc_metadata


def ensure_index_compatibility(client):
    manifest = read_manifest()
    if manifest is not None:
        # Any existing manifest is authoritative; a changed retrieval/index config
        # must not silently mix incompatible vectors in one collection.
        from index_manifest import validate_manifest
        validate_manifest()
        return

    if client.collection_exists(config.COLLECTION_NAME) and client.count(config.COLLECTION_NAME).count > 0:
        raise RuntimeError(
            "Já existem vetores na coleção, mas não há index_manifest.json. "
            "Para evitar misturar embeddings incompatíveis, remova db/qdrant e reindexe."
        )


def delete_existing_document(client, source_name: str) -> None:
    """Remove os chunks anteriores de um PDF antes de reindexá-lo."""
    client.delete(
        collection_name=config.COLLECTION_NAME,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source",
                        match=models.MatchValue(value=source_name),
                    )
                ]
            )
        ),
    )


def ensure_collection(client):
    if client.collection_exists(config.COLLECTION_NAME):
        return
    client.create_collection(
        collection_name=config.COLLECTION_NAME,
        vectors_config={
            "dense": models.VectorParams(size=config.DENSE_DIM, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams(),
        },
    )


def main():
    config.ensure_directories()
    pdf_files = load_pdfs()
    client = QdrantClient(path=str(config.QDRANT_PATH))

    try:
        ensure_index_compatibility(client)
    except Exception as exc:
        print(f"ERRO: {exc}")
        sys.exit(1)

    print("Carregando modelos de indexação (primeira vez pode demorar)...")
    dense_model = TextEmbedding(model_name=config.DENSE_MODEL)
    sparse_model = SparseTextEmbedding(model_name=config.SPARSE_MODEL)

    ensure_collection(client)

    for pdf_path in pdf_files:
        print(f"\nLendo {pdf_path.name}...")
        pages = extract_pages(pdf_path)
        chunks, doc_metadata = build_chunks(pdf_path, pages)

        if not chunks:
            print("  Aviso: nenhum texto extraído (PDF pode ser escaneado/imagem). Pulando.")
            continue

        print(f"  Metadados detectados: {doc_metadata}")
        print(f"  {len(chunks)} chunks. Gerando embeddings...")

        texts_for_dense = ["passage: " + c["text"] for c in chunks]
        dense_vectors = list(dense_model.embed(texts_for_dense))
        sparse_vectors = list(sparse_model.embed([c["text"] for c in chunks]))

        # Only replace the old document after the new vectors were generated successfully.
        delete_existing_document(client, pdf_path.name)

        points = []
        for i, chunk in enumerate(chunks):
            point_key = f"{pdf_path.name}|{chunk['page']}|{i}|{chunk['text']}"
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, point_key))
            points.append(models.PointStruct(
                id=point_id,
                vector={
                    "dense": dense_vectors[i].tolist(),
                    "sparse": models.SparseVector(
                        indices=sparse_vectors[i].indices.tolist(),
                        values=sparse_vectors[i].values.tolist(),
                    ),
                },
                payload=chunk,
            ))
        client.upsert(collection_name=config.COLLECTION_NAME, points=points)
        print("  Indexado.")

    write_manifest()
    print(f"\nPronto! Total de pontos na coleção: {client.count(config.COLLECTION_NAME).count}")
    print(f"Manifesto de compatibilidade: {config.INDEX_MANIFEST_PATH}")


if __name__ == "__main__":
    main()
