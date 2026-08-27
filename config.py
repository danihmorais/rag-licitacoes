from pathlib import Path
import os
try:
 from dotenv import load_dotenv
 load_dotenv(Path(__file__).parent/'.env')
except ImportError:
 pass
BASE_DIR=Path(__file__).parent
PDFS_DIR=BASE_DIR/'pdfs'; DB_DIR=BASE_DIR/'db'; QDRANT_PATH=DB_DIR/'qdrant'; INDEX_MANIFEST_PATH=DB_DIR/'index_manifest.json'; COLLECTION_NAME='licitacoes'
INDEX_VERSION=os.getenv('RAG_INDEX_VERSION','3')
DENSE_MODEL=os.getenv('RAG_DENSE_MODEL','intfloat/multilingual-e5-large'); DENSE_DIM=int(os.getenv('RAG_DENSE_DIM','1024'))
SPARSE_MODEL=os.getenv('RAG_SPARSE_MODEL','Qdrant/bm25'); RERANK_MODEL=os.getenv('RAG_RERANK_MODEL','BAAI/bge-reranker-base')
CHUNK_SIZE=int(os.getenv('RAG_CHUNK_SIZE','1000')); CHUNK_OVERLAP=int(os.getenv('RAG_CHUNK_OVERLAP','150')); CANDIDATES_K=int(os.getenv('RAG_CANDIDATES_K','60')); FINAL_K=int(os.getenv('RAG_FINAL_K','8')); MAX_CONTEXT_CHARS=int(os.getenv('RAG_MAX_CONTEXT_CHARS','26000'))
FASTEMBED_PROVIDERS=[x.strip() for x in os.getenv('RAG_FASTEMBED_PROVIDERS','').split(',') if x.strip()] or None
LLM_PROVIDER=os.getenv('RAG_LLM_PROVIDER','ollama'); LLM_MODEL=os.getenv('RAG_LLM_MODEL','qwen2.5:7b'); LLM_TEMPERATURE=float(os.getenv('RAG_LLM_TEMPERATURE','0.1')); LLM_TIMEOUT=int(os.getenv('RAG_LLM_TIMEOUT','300'))
OLLAMA_HOST=os.getenv('OLLAMA_HOST','http://localhost:11434'); OPENAI_COMPATIBLE_BASE_URL=os.getenv('RAG_OPENAI_BASE_URL','https://openrouter.ai/api/v1'); OPENAI_COMPATIBLE_API_KEY=os.getenv('RAG_OPENAI_API_KEY',''); GEMINI_API_KEY=os.getenv('GEMINI_API_KEY','')
def ensure_directories(): PDFS_DIR.mkdir(parents=True,exist_ok=True); DB_DIR.mkdir(parents=True,exist_ok=True)
