from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any
from pypdf import PdfReader
from qdrant_client import QdrantClient, models
from fastembed import TextEmbedding
from rank_bm25 import BM25Okapi
from config import SETTINGS
from chunking import build_structural_chunks
from index_manifest import write_manifest
from metadata import extract_metadata
from scripts.sync_sources import sync_sources

def _uuid(key: str) -> str:
    return hashlib.md5(key.encode("utf-8"), usedforsecurity=False).hexdigest()

def _extract_pdf(path: Path) -> tuple[str,list[str]]:
    reader=PdfReader(str(path)); pages=[p.extract_text() or "" for p in reader.pages]
    return "\n\n".join(pages), pages

def _load_cache()->dict[str,Any]:
    if not SETTINGS.ingest_cache.exists(): return {}
    try: return json.loads(SETTINGS.ingest_cache.read_text(encoding="utf-8"))
    except Exception: return {}

def _save_cache(cache:dict[str,Any])->None:
    SETTINGS.ingest_cache.parent.mkdir(parents=True,exist_ok=True)
    tmp=SETTINGS.ingest_cache.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(SETTINGS.ingest_cache)

def _ensure_collection(client:QdrantClient, dim:int)->None:
    names={c.name for c in client.get_collections().collections}
    if SETTINGS.collection not in names:
        client.create_collection(SETTINGS.collection,vectors_config=models.VectorParams(size=dim,distance=models.Distance.COSINE,name="dense"))

def _payload(source:Path, chunk, meta:dict[str,Any])->dict[str,Any]:
    d=dict(meta); d.update({"text":chunk.text,"source":source.name,"source_path":str(source.relative_to(SETTINGS.root)),
        "unit_kind":chunk.unit_kind,"unit_ref":chunk.unit_ref,"unit_id":chunk.unit_id,"chunk_index":chunk.chunk_index,
        "page":chunk.page,"page_end":chunk.page_end,"start":chunk.start,"end":chunk.end}); return d

def _rebuild_bm25(records:list[dict[str,Any]])->None:
    SETTINGS.bm25_index.parent.mkdir(parents=True,exist_ok=True)
    SETTINGS.bm25_index.write_text(json.dumps({"documents":records},ensure_ascii=False),encoding="utf-8")

def ingest(pdf_dir:Path|None=None)->int:
    pdf_dir=pdf_dir or SETTINGS.pdf_dir; pdf_dir.mkdir(parents=True,exist_ok=True)
    embedder=TextEmbedding(model_name=SETTINGS.embedding_model); client=QdrantClient(url=SETTINGS.qdrant_url)
    cache=_load_cache(); lexical=[]; total=0; dim=None
    for path in sorted(pdf_dir.rglob("*.pdf")):
        text,pages=_extract_pdf(path)
        if not text.strip(): continue
        digest=hashlib.sha256(text.encode("utf-8")).hexdigest()
        meta=extract_metadata(path,text[:30000]); chunks=build_structural_chunks(text,pages,meta)
        vectors=list(embedder.embed([c.text for c in chunks]))
        if dim is None and vectors: dim=len(vectors[0]); _ensure_collection(client,dim)
        points=[]
        for c,v in zip(chunks,vectors):
            pid=_uuid(f"{path.name}|{digest}|{c.unit_id}|{c.chunk_index}")
            payload=_payload(path,c,meta)
            points.append(models.PointStruct(id=pid,vector={"dense":v.tolist()},payload=payload))
            lexical.append({"id":pid,**payload})
        if points: client.upsert(collection_name=SETTINGS.collection,points=points,wait=True)
        cache[path.name]={"hash":digest,"chunks":len(chunks),"source_id":meta.get("source_id",path.name)}
        _save_cache(cache); total+=len(points)
    _rebuild_bm25(lexical); write_manifest(); print(f"chunks_indexados={total}"); return total

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--pdf-dir",type=Path); p.add_argument("--sync-sources",action="store_true"); args=p.parse_args()
    if args.sync_sources: sync_sources()
    ingest(args.pdf_dir); return 0
if __name__=="__main__": raise SystemExit(main())
