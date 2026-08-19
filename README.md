# RAG de Licitações

RAG híbrido para editais e documentos de licitação em PDF, com busca semântica + lexical, RRF,
reranking e uma camada de LLM **intercambiável**.

A arquitetura separa explicitamente o **índice/RAG** do **modelo gerador**. Você pode trocar Qwen,
Gemma, Llama, Gemini ou um endpoint OpenAI-compatible sem reindexar os documentos, desde que não
mude os modelos/configurações responsáveis pela indexação.

## Arquitetura

```text
PDFs
 │
 ▼
Extração de texto + metadados
 │
 ▼
Chunking
 │
 ▼
Embedding denso + embedding esparso
 │
 ▼
Qdrant
 │
 ├── busca semântica
 └── busca lexical
       │
       ▼
      RRF
       │
       ▼
   Reranker
       │
       ▼
   Contexto final
       │
       ▼
┌───────────────────────────────┐
│      LLM PROVIDER ADAPTER     │
├──────────┬──────────┬─────────┤
│ Ollama   │ Gemini   │ OpenAI  │
│ Qwen     │          │compat.  │
│ Gemma    │          │OpenRouter│
│ Llama    │          │etc.     │
└──────────┴──────────┴─────────┘
```

### O que é intercambiável

O LLM é totalmente separado do índice. Alterar `LLM_PROVIDER` ou `LLM_MODEL` não altera Qdrant,
chunks, embeddings ou reranker.

Já mudar `DENSE_MODEL`, `DENSE_DIM`, `SPARSE_MODEL`, `RERANK_MODEL`, `CHUNK_SIZE` ou
`CHUNK_OVERLAP` muda o índice lógico. O projeto agora registra essas configurações em
`db/index_manifest.json` e bloqueia consultas/indexações incompatíveis para impedir mistura acidental
de embeddings.

## Estrutura

```text
rag-licitacoes/
├── pdfs/
├── db/
│   ├── qdrant/
│   └── index_manifest.json
├── llm/
│   ├── __init__.py
│   ├── base.py
│   ├── factory.py
│   ├── ollama.py
│   ├── openai_compatible.py
│   └── gemini.py
├── config.py
├── index_manifest.py
├── metadata.py
├── ingest.py
├── query.py
├── requirements.txt
└── README.md
```

## Instalação

```bash
python -m venv venv
```

Linux/macOS:
```bash
source venv/bin/activate
```

Windows:
```powershell
venv\Scripts\activate
```

Depois:
```bash
pip install -r requirements.txt
```

## Indexação

Coloque os PDFs em `pdfs/` e rode:

```bash
python ingest.py
```

Na primeira execução, os modelos de embedding/reranking serão baixados pelo FastEmbed.

O arquivo `db/index_manifest.json` registra exatamente quais modelos e parâmetros produziram o
índice. Isso evita que uma alteração de embedding ou chunking misture vetores incompatíveis na mesma
coleção.

## Trocar somente o LLM

### Ollama (padrão)

```text
RAG_LLM_PROVIDER=ollama
RAG_LLM_MODEL=qwen2.5:7b
```

Ou, antes de executar:

```bash
export RAG_LLM_PROVIDER=ollama
export RAG_LLM_MODEL=qwen2.5:7b
python query.py
```

No Windows PowerShell:

```powershell
$env:RAG_LLM_PROVIDER="ollama"
$env:RAG_LLM_MODEL="qwen2.5:7b"
python query.py
```

Você pode trocar, por exemplo, para o nome de outro modelo instalado no Ollama sem reindexar.

### Gemini

Configure:

```bash
export RAG_LLM_PROVIDER=gemini
export RAG_LLM_MODEL=gemini-2.5-flash
export GEMINI_API_KEY="SUA_CHAVE"
python query.py
```

A chave não fica no código nem no banco vetorial.

### OpenAI-compatible / OpenRouter

```bash
export RAG_LLM_PROVIDER=openai_compatible
export RAG_LLM_MODEL="SEU_MODELO"
export RAG_OPENAI_BASE_URL="https://openrouter.ai/api/v1"
export RAG_OPENAI_API_KEY="SUA_CHAVE"
python query.py
```

Esse mesmo adapter pode apontar para outros servidores que implementem `/v1/chat/completions`.

## Filtros por metadados

```text
@municipio=Urânia @ano=2026 qual o prazo de entrega?
```

Os campos suportados dependem dos metadados produzidos por `metadata.py` e pelos arquivos `.json`
sidecar.

## Reindexação correta

Se você mudar qualquer parâmetro de indexação, não reutilize a coleção antiga. Remova o índice e
recrie:

Linux/macOS:
```bash
rm -rf db/qdrant db/index_manifest.json
python ingest.py
```

Windows PowerShell:
```powershell
Remove-Item -Recurse -Force db\qdrant
Remove-Item -Force db\index_manifest.json -ErrorAction SilentlyContinue
python ingest.py
```

Isso **não é necessário** para trocar apenas `LLM_PROVIDER` ou `LLM_MODEL`.

## Observações

- PDFs escaneados não têm texto extraível via `pypdf`; seria necessário adicionar OCR.
- Qdrant continua armazenando somente os vetores e payloads da recuperação. O LLM não participa da
  indexação.
- O índice atual usa `multilingual-e5-large`, BM25 e `bge-reranker-base`.
- O projeto usa apenas `requests` para os adapters HTTP; não é necessário instalar SDK específico de
  cada provedor.
