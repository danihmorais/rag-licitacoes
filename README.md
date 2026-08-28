# RAG de Licitações

RAG híbrido para licitações, contratos administrativos, Direito Público e regulamentação de São Paulo, com dense + BM25, RRF, reranking e LLM intercambiável.

## Arquitetura

```text
fontes oficiais HTML/PDF -> sincronização -> cache local -> metadados
                                      -> chunking jurídico -> dense + BM25
                                      -> Qdrant -> RRF -> reranker -> contexto -> LLM
```

O LLM é desacoplado do índice: Qwen, Gemma, Llama, Gemini, llama.cpp, LM Studio, vLLM, Ollama ou endpoint OpenAI-compatible podem ser trocados sem reindexação quando somente o gerador muda.

## Corpus jurídico

Legislação pública não é versionada como PDF congelado. `scripts/sources.py` mantém o catálogo oficial; `scripts/sync_sources.py` consulta as URLs, usa retry/backoff, valida o conteúdo e grava cache local em `db/source_cache/` (ignorado pelo Git).

A sincronização local também descobre PDFs diretamente linkados por páginas oficiais selecionadas. Isso substitui o antigo workflow que gerava PDFs e fazia commits automáticos.

```bash
python scripts/sync_sources.py
python ingest.py
```

Para somente verificar as fontes obrigatórias, sem gravar cache:

```bash
python scripts/sync_sources.py --check --required-only
```

Documentos recebidos manualmente (edital, TR, DFD, ETP, processo etc.) podem continuar em `pdfs/`. Para arquivos manualmente versionados, use `.DDMMAAAA.pdf`, por exemplo `.27082026.pdf`.

## Conteúdo

### Federal

Constituição; Lei 14.133/2021; Decreto 12.807/2025; LINDB; Decreto-Lei 200/1967; Lei 9.784/1999; improbidade; anticorrupção; LAI; LGPD; estatais; concessões; PPPs; LRF; Lei 4.320/1964; LC 123/2006; Lei 13.019/2014; Governo Digital; PCA; agentes/fiscais; SRP; credenciamento; ETP; TR; dispensa eletrônica; pesquisa de preços e demais atos oficiais.

Lei 8.666/1993, Lei 10.520/2002 e RDC são mantidos como corpus histórico e marcados `revogado`, para análise de documentos legados sem apresentá-los como regra atual.

### São Paulo

Constituição Estadual; Lei 10.177/1998; LC 709/1993; Lei 6.544/1989; regulamentação paulista da Lei 14.133/2021; PCA; pesquisa de preços; ETP; catálogo; TR; agentes; contratação direta; leilão; AUDESP; integridade; responsabilização; Marketplace.SP; Compras SP e TCESP.

### Controle/orientação

TCU, TCESP, AGU, PNCP, Compras.gov.br e Compras SP têm `source_role` explícito. Jurisprudência, manual e orientação nunca são tratados como texto legal. Doutrina comercial protegida não deve ser copiada integralmente sem licença.

## Recuperação jurídica

- Dense + BM25 + RRF.
- Chunking estrutural por artigo/súmula.
- `source_id`, `unit_id`, `chunk_index`, páginas e metadados temporais.
- Reranker independente do LLM.
- Relevância primária; autoridade só desempata.
- `RAG_MIN_EVIDENCE_SCORE` impede chamar o LLM quando não há evidência suficiente.
- Citações `[F#]` para afirmações jurídicas relevantes.
- Filtros: `@jurisdicao=estadual_sp @ano=2026 ...`.

## Temporalidade

O corpus carrega `status`, `effective_from`, `effective_to`, `revogado`, `data_vigencia` e `retrieved_at`. Exemplo: a IN SEGES/MGI 512/2025 está marcada como `vacatio_legis` com início em 30/11/2026, e a IN 129/2026 registra a postergação.

## RTX 5060 Ti 16 GB

Recuperação e LLM permanecem desacoplados. FastEmbed pode usar `RAG_FASTEMBED_PROVIDERS=CUDAExecutionProvider`, deixando a escolha de servidor/modelo de geração independente e permitindo reservar VRAM para o LLM.

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/sync_sources.py
python ingest.py
python query.py
```

## GitHub Actions

`ci.yml` testa e compila sem depender de sites jurídicos externos. `sync-sources.yml` apenas verifica fontes oficiais obrigatórias semanalmente/manual e não faz commits.

O último CI vermelho falhava em `test_structural_chunking_keeps_article_unit`: 5 testes passavam e o parser devolvia uma unidade genérica em vez de `Art. 1º`, `Art. 2º`, `Art. 3º`. O parser e os testes foram corrigidos, incluindo `Artigo 1º` e `Art. 10-A`.

## Verificações

```bash
python -m compileall -q .
python -m pytest -q
python scripts/sync_sources.py --check --required-only
```
