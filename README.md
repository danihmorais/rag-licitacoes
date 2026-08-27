# RAG de Licitações

RAG híbrido para leis, regulamentos, editais, minutas e jurisprudência de licitações, com busca semântica + lexical, RRF, reranking e LLM intercambiável.

O LLM é desacoplado do índice: trocar Qwen, Gemma, Llama, Gemini ou qualquer endpoint OpenAI-compatible não exige reindexação. Mudanças em embedding, BM25, reranker, chunking, prefixos de embedding ou esquema do payload exigem reindexação e são detectadas por `db/index_manifest.json`.

## Pipeline

```text
PDF -> extração por página -> metadados -> chunking estrutural -> dense + BM25 -> Qdrant
                                                           -> RRF -> reranker -> diversidade
                                                           -> orçamento de contexto -> LLM
```

### Estrutura jurídica do chunk

Legislação, súmulas e documentos estruturados são divididos preferencialmente por unidade jurídica (`artigo`, `sumula`, etc.) antes do split por tamanho. Cada fragmento mantém `unit_id`, `unit_ref`, `chunk_index`, `page` e `page_end`.

Unidades longas não repetem o texto integral em todos os vetores. Isso reduz o payload e evita que a mesma unidade consuma várias vezes o orçamento de contexto.

## Fontes e hierarquia

1. **Norma vigente**: Constituição, lei, decreto, resolução, portaria e atos normativos aplicáveis.
2. **Jurisprudência/controle**: STF, STJ, TCESP, TCU etc., sempre identificados como decisões/entendimentos.
3. **Orientação oficial**: AGU, Compras.gov, Compras SP, manuais e guias.
4. **Doutrina**: fonte secundária.

O prompt exige marcadores `[F#]` para afirmações jurídicas e o contexto preserva fonte, página, unidade, jurisdição, papel, autoridade e vigência.

## Metadados

Além de `municipio`, `modalidade`, `ano`, `processo` e `tipo`, o índice suporta:

- `jurisdicao`, `esfera`, `orgao`, `tribunal`
- `tipo_documento`, `source_role`, `authority_level`, `status`
- `data_versao`, `data_publicacao`, `data_vigencia`
- `effective_from`, `effective_to`, `revogado`, `norma_alteradora`
- `fonte_oficial`, `fonte_host`, `retrieved_at`

Documentos importantes devem ter sidecar JSON com o mesmo nome do PDF. O sidecar prevalece sobre a heurística automática.

Filtros continuam no formato:

```text
@municipio=Urânia @ano=2026 qual o prazo de entrega?
@jurisdicao=estadual_sp @tipo_documento=decreto quais regras se aplicam ao ETP?
@status=vigente @source_role=norma qual é a regra aplicável?
```

## Conteúdo prioritário para São Paulo

O corpus prioriza a Lei nº 14.133/2021 e a regulamentação estadual paulista, incluindo os Decretos nº 67.608/2023, 67.689/2023, 67.885/2023, 67.888/2023, 67.985/2023, 68.017/2023, 68.021/2023, 68.185/2023, 68.220/2023, 68.304/2024 e 68.422/2024, além das normas estaduais transversais e atos recentes de integridade/anticorrupção.

Itens em elaboração não devem entrar no acervo como norma vigente.

## Conteúdo federal complementar

O corpus também contempla legislação integral/compilada relevante para Direito Administrativo e Direito Público, incluindo LINDB, processo administrativo, improbidade, anticorrupção, LAI, LGPD, Governo Digital, estatais, concessões, PPPs, responsabilidade fiscal e direito financeiro.

A regra é: **legislação primária completa primeiro; materiais explicativos depois**.

## Hardware e modelos locais

Em uma RTX 5060 Ti 16 GB, mantenha o índice e os modelos de recuperação separados do gerador. O LLM pode rodar via Ollama, llama.cpp/vLLM através de endpoint OpenAI-compatible ou outro adapter.

Para usar CUDA no FastEmbed, configure:

```text
RAG_FASTEMBED_PROVIDERS=CUDAExecutionProvider
```

O embedding atual é `intfloat/multilingual-e5-large`; consultas usam `query:` e documentos `passage:`. O manifest registra esses prefixos para impedir incompatibilidade silenciosa.

## Instalação

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python ingest.py
```

No Windows PowerShell, use `venv\\Scripts\\activate`.

PDFs escaneados podem produzir pouco texto com `pypdf`; o ingest avisa quando isso acontece. OCR deve ser tratado como etapa própria e marcado como tal.

## Configuração via .env

Copie `.env.example` para `.env` e ajuste `RAG_LLM_PROVIDER`/`RAG_LLM_MODEL`. O `.env` não deve ser commitado.

## Ingestão incremental

`ingest.py` guarda hash SHA-256 de cada PDF em `db/ingest_cache.json`. PDFs inalterados são pulados. Um PDF corrompido ou ilegível gera aviso sem interromper os demais.

## Reindexação

Ao alterar embedding, chunking, reranker, prefixos ou esquema do índice:

```bash
rm -rf db/qdrant db/index_manifest.json db/ingest_cache.json
python ingest.py
```

Trocar somente o LLM não exige reindexação.

## Corpus jurídico — 27/08/2026

A revisão atual ampliou e fortaleceu o gerador de PDFs oficiais. Os nomes recebem o sufixo `.27082026` nesta execução. O workflow valida o tamanho e a aparência normativa das fontes antes de gerar o PDF, evitando incorporar páginas de navegação como legislação.

Consulte `docs/CORPUS_REVIEW_27082026.md` para a auditoria e o roadmap de jurisprudência, OCR, avaliação e temporalidade.
