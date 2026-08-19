from pathlib import Path
import os

BASE_DIR = Path(__file__).parent
PDFS_DIR = BASE_DIR / "pdfs"
DB_DIR = BASE_DIR / "db"
QDRANT_PATH = DB_DIR / "qdrant"
INDEX_MANIFEST_PATH = DB_DIR / "index_manifest.json"

COLLECTION_NAME = "licitacoes"
INDEX_VERSION = "1"

# Retrieval / index models. These are deliberately independent from the LLM.
DENSE_MODEL = "intfloat/multilingual-e5-large"
DENSE_DIM = 1024  # must match DENSE_MODEL; changing it requires a new index/reindex
SPARSE_MODEL = "Qdrant/bm25"
RERANK_MODEL = "BAAI/bge-reranker-base"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
CANDIDATES_K = 20
FINAL_K = 5

# LLM provider. Supported: ollama, openai_compatible, gemini.
# Change these values without touching the RAG index.
LLM_PROVIDER = os.getenv("RAG_LLM_PROVIDER", "ollama")
LLM_MODEL = os.getenv("RAG_LLM_MODEL", "qwen2.5:7b")
LLM_TEMPERATURE = float(os.getenv("RAG_LLM_TEMPERATURE", "0.1"))
LLM_TIMEOUT = int(os.getenv("RAG_LLM_TIMEOUT", "300"))

# Ollama
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# OpenAI-compatible APIs (works with OpenAI-compatible local servers and
# services such as OpenRouter when the matching URL/key are configured).
OPENAI_COMPATIBLE_BASE_URL = os.getenv(
    "RAG_OPENAI_BASE_URL",
    "https://openrouter.ai/api/v1",
)
OPENAI_COMPATIBLE_API_KEY = os.getenv("RAG_OPENAI_API_KEY", "")

# Gemini REST API.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def ensure_directories() -> None:
    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)
