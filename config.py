from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default

def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default

@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    pdf_dir: Path = ROOT / "pdfs"
    cache_dir: Path = ROOT / "data" / "cache"
    ingest_cache: Path = ROOT / "data" / "ingest_cache.json"
    bm25_index: Path = ROOT / "data" / "bm25.json"

    qdrant_url: str = os.getenv("RAG_QDRANT_URL", "http://127.0.0.1:6333")
    collection: str = os.getenv("RAG_QDRANT_COLLECTION", "licitacoes")
    embedding_model: str = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-m3")

    chunk_size: int = _int("RAG_CHUNK_SIZE", 1000)
    chunk_overlap: int = _int("RAG_CHUNK_OVERLAP", 120)
    dense_k: int = _int("RAG_DENSE_K", 32)
    bm25_k: int = _int("RAG_BM25_K", 32)
    rrf_k: int = _int("RAG_RRF_K", 60)
    final_k: int = _int("RAG_FINAL_K", 8)
    context_neighbors: int = _int("RAG_CONTEXT_NEIGHBORS", 1)
    max_context_chars: int = _int("RAG_MAX_CONTEXT_CHARS", 26000)
    min_evidence_score: float = _float("RAG_MIN_EVIDENCE_SCORE", 0.18)

    llm_base_url: str = os.getenv("RAG_LLM_BASE_URL", "http://127.0.0.1:8888/v1")
    llm_model: str = os.getenv("RAG_LLM_MODEL", "unsloth/gemma-4-26B-A4B-it-qat-GGUF")
    llm_api_key: str = os.getenv("RAG_LLM_API_KEY", "")

    request_timeout: float = _float("RAG_REQUEST_TIMEOUT", 45.0)

SETTINGS = Settings()
