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
INDEX_VERSION = os.getenv('RAG_INDEX_VERSION', '15')
DENSE_MODEL = os.getenv('RAG_DENSE_MODEL', 'intfloat/multilingual-e5-large')
DENSE_DIM = int(os.getenv('RAG_DENSE_DIM', '1024'))
DENSE_MAX_TOKENS = int(os.getenv('RAG_DENSE_MAX_TOKENS', '512'))
SPARSE_MODEL = os.getenv('RAG_SPARSE_MODEL', 'Qdrant/bm25')
RERANK_MODEL = os.getenv('RAG_RERANK_MODEL', 'BAAI/bge-reranker-base')
RERANK_SCORE_MODE = os.getenv('RAG_RERANK_SCORE_MODE', 'sigmoid').strip().lower()
RERANK_RELEVANCE_WEIGHT = float(os.getenv('RAG_RERANK_RELEVANCE_WEIGHT', '0.68'))
RERANK_AUTHORITY_WEIGHT = float(os.getenv('RAG_RERANK_AUTHORITY_WEIGHT', '0.20'))
RERANK_JURISDICTION_WEIGHT = float(os.getenv('RAG_RERANK_JURISDICTION_WEIGHT', '0.12'))
CHUNK_SIZE = int(os.getenv('RAG_CHUNK_SIZE', '1000'))
CHUNK_OVERLAP = int(os.getenv('RAG_CHUNK_OVERLAP', '150'))
CANDIDATES_K = int(os.getenv('RAG_CANDIDATES_K', '60'))
FINAL_K = int(os.getenv('RAG_FINAL_K', '6'))
CONTEXT_NEIGHBORS = int(os.getenv('RAG_CONTEXT_NEIGHBORS', '1'))
MAX_CONTEXT_CHARS = int(os.getenv('RAG_MAX_CONTEXT_CHARS', '16000'))
QDRANT_UPSERT_BATCH_SIZE = int(os.getenv('RAG_QDRANT_UPSERT_BATCH_SIZE', '100'))
QDRANT_PAYLOAD_INDEXES = {
    'doc_id': 'keyword', 'source_id': 'keyword', 'source': 'keyword', 'unit_id': 'keyword',
    'jurisdicao': 'keyword', 'esfera': 'keyword', 'orgao': 'keyword', 'tribunal': 'keyword',
    'tipo_documento': 'keyword', 'source_role': 'keyword', 'status': 'keyword', 'municipio': 'keyword',
    'modalidade': 'keyword', 'tipo': 'keyword', 'numero_sumula': 'keyword', 'regime_juridico': 'keyword',
    'authority_level': 'integer', 'normative_rank': 'integer', 'ano': 'integer', 'norm_ano': 'integer',
    'revogado': 'bool', 'chunking_method': 'keyword', 'semantic_topic': 'keyword', 'semantic_section': 'keyword',
}
MIN_EVIDENCE_SCORE = float(os.getenv('RAG_MIN_EVIDENCE_SCORE', '0.20'))
EVIDENCE_TOKEN_OVERLAP = float(os.getenv('RAG_EVIDENCE_TOKEN_OVERLAP', '0.25'))
FASTEMBED_PROVIDERS = tuple(x.strip() for x in os.getenv('RAG_FASTEMBED_PROVIDERS', 'CUDAExecutionProvider').split(',') if x.strip())
FASTEMBED_REQUIRE_CUDA = os.getenv('RAG_FASTEMBED_REQUIRE_CUDA', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
OCR_ENABLED = os.getenv('RAG_OCR_ENABLED', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
OCR_REQUIRED = os.getenv('RAG_OCR_REQUIRED', '0').strip().lower() not in {'0', 'false', 'no', 'off'}
OCR_MIN_NATIVE_CHARS_PER_PAGE = int(os.getenv('RAG_OCR_MIN_NATIVE_CHARS_PER_PAGE', '80'))
OCR_MIN_NATIVE_CONFIDENCE = float(os.getenv('RAG_OCR_MIN_NATIVE_CONFIDENCE', '0.60'))
OCR_DPI = int(os.getenv('RAG_OCR_DPI', '250'))
OCR_LANGUAGE = os.getenv('RAG_OCR_LANGUAGE', 'por+eng')
RAG_SYNC_SOURCES = os.getenv('RAG_SYNC_SOURCES', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
RAG_SYNC_JURISPRUDENCIA = os.getenv('RAG_SYNC_JURISPRUDENCIA', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
RAG_PRUNE_STALE = os.getenv('RAG_PRUNE_STALE', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
JURISPRUDENCIA_QUERY = os.getenv('RAG_JURISPRUDENCIA_QUERY', '').strip()
JURISPRUDENCIA_QUERIES = parse_queries(os.getenv('RAG_JURISPRUDENCIA_QUERIES'))
JURISPRUDENCIA_LIMIT = int(os.getenv('RAG_JURISPRUDENCIA_LIMIT', '200'))
JURISPRUDENCIA_MIN_RECORDS_PER_TRIBUNAL = int(os.getenv('RAG_JURISPRUDENCIA_MIN_RECORDS_PER_TRIBUNAL', '150'))
JURISPRUDENCIA_DETAIL = os.getenv('RAG_JURISPRUDENCIA_DETAIL', '0').strip().lower() not in {'0', 'false', 'no', 'off'}
JURISPRUDENCIA_WITH_CONTENT = os.getenv('RAG_JURISPRUDENCIA_WITH_CONTENT', '0').strip().lower() not in {'0', 'false', 'no', 'off'}
JURISPRUDENCIA_STRICT = os.getenv('RAG_JURISPRUDENCIA_STRICT', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
LLM_PROVIDER = os.getenv('RAG_LLM_PROVIDER', 'openai_compatible')
LLM_MODEL = os.getenv('RAG_LLM_MODEL', 'local')
LLM_TEMPERATURE = float(os.getenv('RAG_LLM_TEMPERATURE', '0.1'))
LLM_TIMEOUT = int(os.getenv('RAG_LLM_TIMEOUT', '300'))
LLM_MAX_TOKENS = int(os.getenv('RAG_LLM_MAX_TOKENS', '0'))
AI_CHUNKING_ENABLED = os.getenv('RAG_AI_CHUNKING_ENABLED', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
AI_CHUNKING_REQUIRED = os.getenv('RAG_AI_CHUNKING_REQUIRED', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
# O chunking semântico é uma otimização; por padrão, uma falha do LLM não pode bloquear a indexação.
AI_CHUNKING_FALLBACK_TO_STRUCTURAL = os.getenv('RAG_AI_CHUNKING_FALLBACK_TO_STRUCTURAL', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
AI_CHUNKING_MIN_CHARS = int(os.getenv('RAG_AI_CHUNKING_MIN_CHARS', '1800'))
AI_CHUNKING_WINDOW_CHARS = int(os.getenv('RAG_AI_CHUNKING_WINDOW_CHARS', '9000'))
AI_CHUNKING_ATTEMPTS = int(os.getenv('RAG_AI_CHUNKING_ATTEMPTS', '2'))
AI_CHUNKING_PROMPT_VERSION = os.getenv('RAG_AI_CHUNKING_PROMPT_VERSION', '1')
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
OLLAMA_NUM_CTX = int(os.getenv('RAG_OLLAMA_NUM_CTX', '16384'))
OPENAI_COMPATIBLE_BASE_URL = os.getenv('RAG_OPENAI_BASE_URL', 'http://127.0.0.1:8888/v1')
OPENAI_COMPATIBLE_API_KEY = os.getenv('RAG_OPENAI_API_KEY', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() not in {'0', 'false', 'no', 'off'}


def validate_config() -> None:
    checks = (
        (DENSE_DIM > 0, 'RAG_DENSE_DIM deve ser maior que zero.'),
        (DENSE_MAX_TOKENS > 0, 'RAG_DENSE_MAX_TOKENS deve ser maior que zero.'),
        (CHUNK_SIZE > 0, 'RAG_CHUNK_SIZE deve ser maior que zero.'),
        (0 <= CHUNK_OVERLAP < CHUNK_SIZE, 'RAG_CHUNK_OVERLAP deve estar entre zero e RAG_CHUNK_SIZE-1.'),
        (CANDIDATES_K > 0, 'RAG_CANDIDATES_K deve ser maior que zero.'),
        (0 < FINAL_K <= CANDIDATES_K, 'RAG_FINAL_K deve ser maior que zero e não exceder RAG_CANDIDATES_K.'),
        (MAX_CONTEXT_CHARS > 0, 'RAG_MAX_CONTEXT_CHARS deve ser maior que zero.'),
        (QDRANT_UPSERT_BATCH_SIZE > 0, 'RAG_QDRANT_UPSERT_BATCH_SIZE deve ser maior que zero.'),
        (0 <= MIN_EVIDENCE_SCORE <= 1, 'RAG_MIN_EVIDENCE_SCORE deve estar entre zero e um.'),
        (0 <= EVIDENCE_TOKEN_OVERLAP <= 1, 'RAG_EVIDENCE_TOKEN_OVERLAP deve estar entre zero e um.'),
        (OLLAMA_NUM_CTX >= 16384, 'RAG_OLLAMA_NUM_CTX deve ser maior ou igual a 16384.'),
        (FASTEMBED_PROVIDERS and all(provider in {'CUDAExecutionProvider', 'CPUExecutionProvider'} for provider in FASTEMBED_PROVIDERS), 'RAG_FASTEMBED_PROVIDERS deve conter somente CUDAExecutionProvider e/ou CPUExecutionProvider.'),
        (not FASTEMBED_REQUIRE_CUDA or 'CUDAExecutionProvider' in FASTEMBED_PROVIDERS, 'RAG_FASTEMBED_REQUIRE_CUDA=1 exige CUDAExecutionProvider em RAG_FASTEMBED_PROVIDERS.'),
        (OCR_MIN_NATIVE_CHARS_PER_PAGE >= 0, 'RAG_OCR_MIN_NATIVE_CHARS_PER_PAGE não pode ser negativo.'),
        (0 <= OCR_MIN_NATIVE_CONFIDENCE <= 1, 'RAG_OCR_MIN_NATIVE_CONFIDENCE deve estar entre zero e um.'),
        (OCR_DPI > 0, 'RAG_OCR_DPI deve ser maior que zero.'),
        (RERANK_SCORE_MODE in {'sigmoid', 'identity'}, "RAG_RERANK_SCORE_MODE deve ser 'sigmoid' ou 'identity'."),
        (RERANK_RELEVANCE_WEIGHT >= 0, 'RAG_RERANK_RELEVANCE_WEIGHT não pode ser negativo.'),
        (RERANK_AUTHORITY_WEIGHT >= 0, 'RAG_RERANK_AUTHORITY_WEIGHT não pode ser negativo.'),
        (RERANK_JURISDICTION_WEIGHT >= 0, 'RAG_RERANK_JURISDICTION_WEIGHT não pode ser negativo.'),
        (abs((RERANK_RELEVANCE_WEIGHT + RERANK_AUTHORITY_WEIGHT + RERANK_JURISDICTION_WEIGHT) - 1.0) < 1e-9, 'Os pesos de reranking devem somar 1.'),
        (LLM_TIMEOUT > 0, 'RAG_LLM_TIMEOUT deve ser maior que zero.'),
        (LLM_MAX_TOKENS >= 0, 'RAG_LLM_MAX_TOKENS não pode ser negativo.'),
        (AI_CHUNKING_MIN_CHARS > 0, 'RAG_AI_CHUNKING_MIN_CHARS deve ser maior que zero.'),
        (AI_CHUNKING_WINDOW_CHARS > 0, 'RAG_AI_CHUNKING_WINDOW_CHARS deve ser maior que zero.'),
        (AI_CHUNKING_WINDOW_CHARS >= AI_CHUNKING_MIN_CHARS, 'RAG_AI_CHUNKING_WINDOW_CHARS deve ser maior ou igual a RAG_AI_CHUNKING_MIN_CHARS.'),
        (AI_CHUNKING_ATTEMPTS > 0, 'RAG_AI_CHUNKING_ATTEMPTS deve ser maior que zero.'),
        (bool(str(AI_CHUNKING_PROMPT_VERSION).strip()), 'RAG_AI_CHUNKING_PROMPT_VERSION não pode ser vazio.'),
        (JURISPRUDENCIA_LIMIT > 0, 'RAG_JURISPRUDENCIA_LIMIT deve ser maior que zero.'),
        (JURISPRUDENCIA_MIN_RECORDS_PER_TRIBUNAL > 0, 'RAG_JURISPRUDENCIA_MIN_RECORDS_PER_TRIBUNAL deve ser maior que zero.'),
        (JURISPRUDENCIA_MIN_RECORDS_PER_TRIBUNAL <= JURISPRUDENCIA_LIMIT, 'RAG_JURISPRUDENCIA_MIN_RECORDS_PER_TRIBUNAL não pode exceder RAG_JURISPRUDENCIA_LIMIT.'),
    )
    errors = [message for ok, message in checks if not ok]
    if errors:
        raise ValueError('Configuração inválida: ' + ' '.join(errors))


def validate_gpu_runtime() -> None:
    if not FASTEMBED_REQUIRE_CUDA:
        return
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError('Execução GPU obrigatória: onnxruntime-gpu não está instalado.') from exc
    providers = tuple(ort.get_available_providers())
    if 'CUDAExecutionProvider' not in providers:
        raise RuntimeError(
            'Execução GPU obrigatória: CUDAExecutionProvider não está disponível no ONNX Runtime. '
            f'Provedores disponíveis: {", ".join(providers) or "nenhum"}. '
            'Para executar em CPU, defina RAG_FASTEMBED_REQUIRE_CUDA=0 e RAG_FASTEMBED_PROVIDERS=CPUExecutionProvider.'
        )


def ensure_directories():
    validate_config()
    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
