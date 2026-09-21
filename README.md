# RAG Licitações

RAG jurídico para licitações e contratos administrativos brasileiros, com foco em Lei 14.133/2021, regulamentação federal e paulista, jurisprudência e orientação oficial.

## Arquitetura

- ingestão de PDFs e fontes web com cache e hash;
- chunking jurídico estrutural (Art., Súmula, Tema e registros de jurisprudência);
- metadados explícitos por sidecar JSON, com jurisdição, esfera, vigência, tribunal e autoridade;
- recuperação híbrida dense + BM25 + RRF;
- reranking com score de evidência e autoridade;
- contexto com vizinhança estrutural e citações rastreáveis [F#];
- cliente LLM compatível com OpenAI, incluindo endpoints locais como Unsloth;
- coletores estruturados para TCU, TCESP, STJ e STF;
- sincronização separada do corpus e da indexação.

## Consultas

A sintaxe de filtro aceita `@campo=valor`, por exemplo:

```text
@jurisdicao=federal @ano=2026 dispensa eletrônica
@tribunal=TCU registro de preços
```

## Variáveis principais

```bash
RAG_QDRANT_URL=http://127.0.0.1:6333
RAG_QDRANT_COLLECTION=licitacoes
RAG_EMBEDDING_MODEL=BAAI/bge-m3
RAG_CHUNK_SIZE=1000
RAG_CHUNK_OVERLAP=120
RAG_DENSE_K=32
RAG_BM25_K=32
RAG_FINAL_K=8
RAG_CONTEXT_NEIGHBORS=1
RAG_MAX_CONTEXT_CHARS=26000
RAG_MIN_EVIDENCE_SCORE=0.18

RAG_LLM_BASE_URL=http://127.0.0.1:8888/v1
RAG_LLM_MODEL=unsloth/gemma-4-26B-A4B-it-qat-GGUF
RAG_LLM_API_KEY=
```

## Diretórios

```text
pdfs/                  corpus manual
data/cache/            cache das fontes
data/ingest_cache.json estado da ingestão
data/bm25.json         índice lexical auxiliar
jurisprudencia/        coletores e schema
scripts/               catálogo e sincronização de fontes
llm/                   clientes LLM
tests/                 testes de regressão
docs/                   auditorias e notas técnicas
```

## Execução

```bash
python -m pip install -r requirements.txt
python ingest.py --sync-sources
python query.py "dispensa por valor na Lei 14.133"
```

O corpus jurídico deve ser alimentado prioritariamente por fontes oficiais. Arquivos manuais podem receber um sidecar `arquivo.pdf.json` para declarar metadados de forma determinística.
