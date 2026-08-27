# RAG de Licitações

RAG híbrido para leis, regulamentos, editais, minutas e jurisprudência de licitações, com busca semântica + lexical, RRF, reranking e LLM intercambiável.

O LLM é separado do índice: trocar Qwen, Gemma, Llama, Gemini ou um endpoint OpenAI-compatible não exige reindexação. Alterar embedding, BM25, reranker, chunking ou seus parâmetros exige reindexação e é controlado por `db/index_manifest.json`.

## Pipeline

```text
PDF -> extração por página -> metadados -> chunking estrutural -> dense + BM25 -> Qdrant
                                                           -> RRF -> reranker -> deduplicação
                                                           -> orçamento de contexto -> LLM
```

Para legislação/jurisprudência, artigos, súmulas e enunciados são usados como unidades jurídicas quando essa estrutura domina o documento. Unidades longas são fragmentadas para busca, mas podem ser recompostas no contexto. Em documentos genéricos, como editais, cada fragmento é seu próprio contexto, evitando repetir o edital inteiro em cada vetor.

## Metadados

Além de `municipio`, `modalidade`, `ano`, `processo` e `tipo`, o índice suporta `jurisdicao`, `orgao` e `tipo_documento`. Para documentos importantes, use um sidecar JSON com o mesmo nome do PDF; ele tem prioridade sobre a heurística automática.

```json
{"jurisdicao":"estadual_sp","orgao":"Estado de São Paulo","tipo_documento":"decreto","ano":2026}
```

Filtros:

```text
@municipio=Urânia @ano=2026 qual o prazo de entrega?
@jurisdicao=estadual_sp @tipo_documento=decreto quais regras se aplicam ao ETP?
```

## Instalação

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python ingest.py
```

No Windows PowerShell, use `venv\Scripts\activate`.

PDFs escaneados podem produzir pouco texto com `pypdf`; o ingest avisa quando isso acontece. OCR deve ser tratado como etapa própria antes da indexação.

## LLM intercambiável

### Ollama

```text
RAG_LLM_PROVIDER=ollama
RAG_LLM_MODEL=qwen2.5:7b
```

### OpenAI-compatible / servidor local

```text
RAG_LLM_PROVIDER=openai_compatible
RAG_LLM_MODEL=SEU_MODELO
RAG_OPENAI_BASE_URL=http://localhost:8000/v1
RAG_OPENAI_API_KEY=
```

O mesmo adapter pode apontar para serviços como OpenRouter.

### Gemini

```text
RAG_LLM_PROVIDER=gemini
RAG_LLM_MODEL=gemini-2.5-flash
GEMINI_API_KEY=SUA_CHAVE
```

## Reindexação

Ao alterar qualquer componente do índice:

```bash
rm -rf db/qdrant db/index_manifest.json
python ingest.py
```

Trocar somente o LLM não exige reindexação.

## Conteúdo prioritário para São Paulo

O acervo atual contém Constituição, Lei 14.133/2021, súmulas do TCESP e material do TCU. Para tornar a base realmente especializada em contratações paulistas, adicione versões oficiais e vigentes dos regulamentos estaduais da Lei 14.133, especialmente os decretos sobre PCA, ETP, TR, padronização, valor estimado, bens de luxo, agentes/fiscais, contratação direta e leilão eletrônico, além das minutas padronizadas do Compras SP para DFD, ETP/TR, editais, atas e contratos.

Também é recomendável manter metadados de vigência: `data_publicacao`, `data_vigencia`, `revogado`, `norma_alteradora` e `fonte_oficial`. Isso evita que uma norma histórica seja tratada como regra vigente.

Jurisprudência deve ser identificada por corte, processo/acórdão, órgão julgador, data e status. Súmula ou precedente não deve ser tratado automaticamente como equivalente a norma legal vigente.
