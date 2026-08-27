# RAG de Licitações

RAG híbrido para licitações, contratos administrativos, Direito Público e regulamentação de São Paulo, com busca densa + lexical, RRF, reranking e LLM intercambiável.

O LLM é desacoplado do índice: Qwen, Gemma, Llama, Gemini, llama.cpp, LM Studio, vLLM, Ollama ou outro endpoint OpenAI-compatible podem ser trocados sem reindexação quando somente o gerador muda.

## Pipeline

```text
fontes oficiais HTML/PDF -> sincronização -> cache local -> extração -> metadados
                                                -> chunking jurídico -> dense + BM25
                                                -> Qdrant -> RRF -> reranker -> contexto -> LLM
```

## Corpus jurídico sem PDFs versionados

O repositório não precisa armazenar cópias congeladas de legislação. `scripts/sync_sources.py` mantém um catálogo de fontes oficiais, com URLs alternativas, jurisdição, órgão, tipo documental, papel e nível de autoridade.

A sincronização baixa HTML/PDF, normaliza o texto e grava o resultado em `db/source_cache/`, que não é versionado. Há retries/backoff e fallback entre fontes oficiais. Uma indisponibilidade temporária não apaga o cache anterior.

```bash
python scripts/sync_sources.py
python ingest.py
```

Para testar somente fontes obrigatórias:

```bash
python scripts/sync_sources.py --check --required-only
```

Documentos fornecidos manualmente, como edital, TR, DFD, ETP e jurisprudência específica, continuam em `pdfs/`.

## Conteúdo prioritário

### Federal

Constituição Federal; Lei nº 14.133/2021; Decreto nº 12.807/2025; LINDB; Lei nº 9.784/1999; Lei nº 8.429/1992; Lei Anticorrupção e seu regulamento; LAI; LGPD; Lei das Estatais; concessões; PPPs; LRF; Lei nº 4.320/1964; normas federais de PCA, ETP, TR e pesquisa de preços; além de legislação ambiental, resíduos e acessibilidade pertinente a contratações.

### São Paulo

Constituição Estadual; Lei nº 10.177/1998; LC nº 709/1993; Lei nº 6.544/1989; regulamentação paulista da Lei nº 14.133/2021; Compras SP; TCESP; normas recentes de integridade, responsabilização e Marketplace.SP.

### Controle e orientação

TCU, TCESP, AGU, PNCP, Compras.gov.br e Compras SP são classificados como jurisprudência/controle ou orientação oficial conforme o caso. Não são tratados como texto legal pelo prompt.

Doutrina comercial protegida por direitos autorais não deve ser copiada integralmente para o repositório sem licença. Prefira materiais públicos, licenciados e referências temáticas.

## Recuperação jurídica

- Dense + BM25 + RRF.
- Chunking estrutural por artigo/súmula antes do split por tamanho.
- Identidade por `source_id`, `unit_id` e `chunk_index`.
- Reranker independente do LLM.
- Relevância é o critério primário; autoridade não pode transformar documento irrelevante em resposta.
- Filtros por jurisdição, ano, status e demais metadados.
- Se não houver evidência recuperada, o LLM não é chamado.
- Citações `[F#]` são exigidas para afirmações jurídicas relevantes.

O índice usa `intfloat/multilingual-e5-large`, com `passage:` em documentos e `query:` em consultas. Mudanças no embedding, chunking, reranker, prefixos ou schema exigem reindexação e são detectadas por `index_manifest.json`.

## Temporalidade

O objetivo é suportar tanto “qual é a regra vigente?” quanto “qual era a regra em determinada data?”. O modelo de metadados contempla `data_publicacao`, `data_vigencia`, `effective_from`, `effective_to`, `status`, `revogado`, `norma_alteradora` e `retrieved_at`. A extração dessas relações será ampliada progressivamente por fonte.

## RTX 5060 Ti 16 GB

Mantenha o gerador local separado do mecanismo de recuperação. FastEmbed pode usar `CUDAExecutionProvider`; Qdrant e parte da recuperação podem permanecer fora da GPU. O LLM pode ser qualquer adapter compatível.

```text
RAG_FASTEMBED_PROVIDERS=CUDAExecutionProvider
```

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python ingest.py
python query.py
```

## GitHub Actions

O antigo workflow de geração de PDFs falhava porque várias fontes externas, especialmente páginas do Planalto, retornavam `RemoteDisconnected` no runner. Como o workflow abortava quando qualquer uma das 34 fontes falhava, o CI ficava vermelho mesmo com 17 fontes de São Paulo sendo processadas corretamente.

Agora existem dois workflows independentes:

- `ci.yml`: testes e compilação, sem depender de sites jurídicos externos.
- `sync-sources.yml`: verificação semanal/manual das fontes oficiais obrigatórias, com retry e sem commits automáticos.

Isso elimina o loop de commits automáticos de PDFs e impede que uma falha de rede em uma fonte jurídica quebre o CI normal.

## Próximos passos recomendados

1. Coletor estruturado de acórdãos TCESP/TCU/STJ/STF com processo, órgão julgador, relator, data e assunto.
2. OCR explícito para PDFs escaneados, com `text_origin=native|ocr` e confiança por página.
3. Dataset de avaliação com perguntas reais e métricas recall@k, MRR/nDCG, cobertura de citação, jurisdição e temporalidade.
4. Relações entre norma alteradora e dispositivos alterados.
5. Catálogos separados para jurisprudência, orientação oficial e doutrina.
