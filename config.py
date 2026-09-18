from pathlib import Path
import os

from jurisprudencia.queries import parse_queries

BASE_DIR = Path(__file__).parent
PDFS_DIR = BASE_DIR / 'pdfs'
DB_DIR = BASE_DIR / 'db'
SOURCE_CACHE_DIR = DB_DIR / 'source_cache'
QDRANT_PATH = DB_DIR / 'qdrant'
INDEX_MANIFEST_PATH = DB_DIR / 'index_manifest.json'
COLLECTION_NAME = 'licitacoes'
INDEX_VERSION = os.getenv('RAG_INDEX_VERSION', '11')
DENSE_MODEL = os.getenv('RAG_DENSE_MODEL', 'intfloat/multilingual-e5-large')
DENSE_DIM = int(os.getenv('RAG_DENSE_DIM', '1024'))
SPARSE_MODEL = os.getenv('RAG_SPARSE_MODEL', 'Qdrant/bm25')
RERANK_MODEL = os.getenv('RAG_RERANK_MODEL', 'BAAI/bge-reranker-base')
RERANK_SCORE_MODE = os.getenv('RAG_RERANK_SCORE_MODE', 'sigmoid').strip().lower()
RERANK_RELEVANCE_WEIGHT = float(os.getenv('RAG_RERANK_RELEVANCE_WEIGHT', '0.68'))
RERANK_AUTHORITY_WEIGHT = float(os.getenv('RAG_RERANK_AUTHORITY_WEIGHT', '0.20'))
RERANK_JURISDICTION_WEIGHT = float(os.getenv('RAG_RERANK_JURISDICTION_WEIGHT', '0.12'))
CHUNK_SIZE = int(os.getenv('RAG_CHUNK_SIZE', '1000'))
CHUNK_OVERLAP = int(os.getenv('RAG_CHUNK_OVERLAP', '150'))
CANDIDATES_K = int(os.getenv('RAG_CANDIDATES_K', '60'))
FINAL_K = int(os.getenv('RAG_FINAL_K', '8'))
CONTEXT_NEIGHBORS = int(os.getenv('RAG_CONTEXT_NEIGHBORS', '1'))
MAX_CONTEXT_CHARS = int(os.getenv('RAG_MAX_CONTEXT_CHARS', '26000'))
MIN_EVIDENCE_SCORE = float(os.getenv('RAG_MIN_EVIDENCE_SCORE', '0.20'))
FASTEMBED_PROVIDERS = [x.strip() for x in os.getenv('RAG_FASTEMBED_PROVIDERS', '').split(',') if x.strip()] or None
RAG_SYNC_SOURCES = os.getenv('RAG_SYNC_SOURCES', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
RAG_SYNC_JURISPRUDENCIA = os.getenv('RAG_SYNC_JURISPRUDENCIA', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
RAG_PRUNE_STALE = os.getenv('RAG_PRUNE_STALE', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
JURISPRUDENCIA_QUERY = os.getenv('RAG_JURISPRUDENCIA_QUERY', '').strip()
JURISPRUDENCIA_QUERIES = parse_queries(os.getenv('RAG_JURISPRUDENCIA_QUERIES'))
JURISPRUDENCIA_LIMIT = int(os.getenv('RAG_JURISPRUDENCIA_LIMIT', '12'))
JURISPRUDENCIA_DETAIL = os.getenv('RAG_JURISPRUDENCIA_DETAIL', '0').strip().lower() not in {'0', 'false', 'no', 'off'}
JURISPRUDENCIA_WITH_CONTENT = os.getenv('RAG_JURISPRUDENCIA_WITH_CONTENT', '0').strip().lower() not in {'0', 'false', 'no', 'off'}
JURISPRUDENCIA_STRICT = os.getenv('RAG_JURISPRUDENCIA_STRICT', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
LLM_PROVIDER = os.getenv('RAG_LLM_PROVIDER', 'openai_compatible')
LLM_MODEL = os.getenv('RAG_LLM_MODEL', 'local')
LLM_TEMPERATURE = float(os.getenv('RAG_LLM_TEMPERATURE', '0.1'))
LLM_TIMEOUT = int(os.getenv('RAG_LLM_TIMEOUT', '300'))
LLM_MAX_TOKENS = int(os.getenv('RAG_LLM_MAX_TOKENS', '0'))
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
OPENAI_COMPATIBLE_BASE_URL = os.getenv('RAG_OPENAI_BASE_URL', 'http://127.0.0.1:8080/v1')
OPENAI_COMPATIBLE_API_KEY = os.getenv('RAG_OPENAI_API_KEY', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() not in {'0', 'false', 'no', 'off'}


def validate_config() -> None:
    checks = (
        (DENSE_DIM > 0, 'RAG_DENSE_DIM deve ser maior que zero.'),
        (CHUNK_SIZE > 0, 'RAG_CHUNK_SIZE deve ser maior que zero.'),
        (0 <= CHUNK_OVERLAP < CHUNK_SIZE, 'RAG_CHUNK_OVERLAP deve estar entre zero e RAG_CHUNK_SIZE-1.'),
        (CANDIDATES_K > 0, 'RAG_CANDIDATES_K deve ser maior que zero.'),
        (0 < FINAL_K <= CANDIDATES_K, 'RAG_FINAL_K deve ser maior que zero e não exceder RAG_CANDIDATES_K.'),
        (MAX_CONTEXT_CHARS > 0, 'RAG_MAX_CONTEXT_CHARS deve ser maior que zero.'),
        (0 <= MIN_EVIDENCE_SCORE <= 1, 'RAG_MIN_EVIDENCE_SCORE deve estar entre zero e um.'),
        (RERANK_SCORE_MODE in {'sigmoid', 'identity'}, "RAG_RERANK_SCORE_MODE deve ser 'sigmoid' ou 'identity'."),
        (RERANK_RELEVANCE_WEIGHT >= 0, 'RAG_RERANK_RELEVANCE_WEIGHT não pode ser negativo.'),
        (RERANK_AUTHORITY_WEIGHT >= 0, 'RAG_RERANK_AUTHORITY_WEIGHT não pode ser negativo.'),
        (RERANK_JURISDICTION_WEIGHT >= 0, 'RAG_RERANK_JURISDICTION_WEIGHT não pode ser negativo.'),
        (abs((RERANK_RELEVANCE_WEIGHT + RERANK_AUTHORITY_WEIGHT + RERANK_JURISDICTION_WEIGHT) - 1.0) < 1e-9, 'Os pesos de reranking devem somar 1.'),
        (LLM_TIMEOUT > 0, 'RAG_LLM_TIMEOUT deve ser maior que zero.'),
        (LLM_MAX_TOKENS >= 0, 'RAG_LLM_MAX_TOKENS não pode ser negativo.'),
        (JURISPRUDENCIA_LIMIT > 0, 'RAG_JURISPRUDENCIA_LIMIT deve ser maior que zero.'),
    )
    errors = [message for ok, message in checks if not ok]
    if errors:
        raise ValueError('Configuração inválida: ' + ' '.join(errors))


def ensure_directories():
    validate_config()
    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
