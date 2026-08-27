import sys
import uuid
from pypdf import PdfReader
from qdrant_client import QdrantClient, models
from fastembed import TextEmbedding, SparseTextEmbedding
import config
from chunking import build_structural_chunks
from index_manifest import read_manifest, write_manifest
from metadata import extract_metadata
PAGE_BREAK = "\f"


def load_pdfs():
    pdf_files = sorted(config.PDFS_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"Nenhum PDF encontrado em {config.PDFS_DIR}. Coloque os arquivos ali e rode de novo.")
        sys.exit(1)
    return pdf_files


def extract_pages(pdf_path):
    return [page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages]


def _page_starts(pages):
    starts, offset = [], 0
    for page_text in pages:
        starts.append(offset)
        offset += len(page_text) + len(PAGE_BREAK)
    return starts


def _page_for_offset(offset, starts):
    page_num = 1
    for i, start in enumerate(starts, start=1):
        if start <= offset:
            page_num = i
        else:
            break
    return page_num


def build_chunks(pdf_path, pages):
    full_text = PAGE_BREAK.join(pages)
    doc_metadata = extract_metadata(full_text, pdf_path)
    starts = _page_starts(pages)
    structural_chunks = build_structural_chunks(full_text, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
    chunks, search_offset = [], 0
    for piece in structural_chunks:
        if not piece["text"].strip():
            continue
        found_at = full_text.find(piece["text"], search_offset)
        start_offset = found_at if found_at >= 0 else piece["start"]
        end_offset = start_offset + len(piece["text"])
        search_offset = max(start_offset + 1, end_offset - config.CHUNK_OVERLAP)
        chunks.append({
            "text": piece["text"], "full_unit_text": piece["full_unit_text"],
            "unit_kind": piece["unit_kind"], "unit_ref": piece["unit_ref"],
            "source": pdf_path.name,
            "page": _page_for_offset(start_offset, starts),
            "page_end": _page_for_offset(max(start_offset, end_offset - 1), starts),
            **doc_metadata,
        })
    return chunks, doc_metadata


def ensure_index_compatibility(client):
    manifest = read_manifest()
    if manifest is not None:
        from index_manifest import validate_manifest
        validate_manifest()
        return
    if client.collection_exists(config.COLLECTION_NAME) and client.count(config.COLLECTION_NAME).count > 0:
        raise RuntimeError("Já existem vetores sem index_manifest.json. Remova db/qdrant e reindexe.")


def delete_existing_document(client, source_name):
    client.delete(collection_name=config.COLLECTION_NAME, points_selector=models.FilterSelector(filter=models.Filter(must=[models.FieldCondition(key="source", match=models.MatchValue(value=source_name))])))


def ensure_collection(client):
    if client.collection_exists(config.COLLECTION_NAME):
        return
    client.create_collection(collection_name=config.COLLECTION_NAME,
        vectors_config={"dense": models.VectorParams(size=config.DENSE_DIM, distance=models.Distance.COSINE)},
        sparse_vectors_config={"sparse": models.SparseVectorParams()})


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
        extracted_chars = sum(len(page.strip()) for page in pages)
        if not chunks:
            print("  Aviso: nenhum texto extraído (PDF pode ser escaneado/imagem). Pulando.")
            continue
        if extracted_chars < 500:
            print("  Aviso: pouco texto extraído; o PDF pode ser escaneado ou ter extração ruim.")
        print(f"  Metadados: {doc_metadata}")
        print(f"  {len(chunks)} chunks. Gerando embeddings...")
        dense_vectors = list(dense_model.embed(["passage: " + c["text"] for c in chunks]))
        sparse_vectors = list(sparse_model.embed([c["text"] for c in chunks]))
        delete_existing_document(client, pdf_path.name)
        points = []
        for i, chunk in enumerate(chunks):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{pdf_path.name}|{chunk['page']}|{i}|{chunk['text']}"))
            points.append(models.PointStruct(id=point_id, vector={"dense": dense_vectors[i].tolist(), "sparse": models.SparseVector(indices=sparse_vectors[i].indices.tolist(), values=sparse_vectors[i].values.tolist())}, payload=chunk))
        client.upsert(collection_name=config.COLLECTION_NAME, points=points)
        print("  Indexado.")
    write_manifest()
    print(f"\nPronto! Total de pontos: {client.count(config.COLLECTION_NAME).count}")


if __name__ == "__main__":
    main()
