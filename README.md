# RAG de Licitações

RAG híbrido para licitações, contratos administrativos, Direito Público e regulamentação de São Paulo, com busca densa + BM25, RRF, reranking e LLM intercambiável.

## Arquitetura

```text
fontes oficiais HTML/PDF -> sincronização -> cache local -> metadados
                                      -> chunking jurídico -> dense + BM25
                                      -> Qdrant -> RRF -> reranker -> contexto -> LLM
```

O LLM é desacoplado do índice: Qwen, Gemma, Llama, Gemini, llama.cpp, LM Studio, vLLM, Ollama ou qualquer endpoint OpenAI-compatible podem ser trocados sem reindexação quando somente o gerador muda.

## Corpus jurídico

Legislação pública não fica congelada em PDFs no Git. `scripts/sources.py` mantém o catálogo oficial e `scripts/sources_additional.py` complementa a cobertura com legislação recente e portais de jurisprudência. `scripts/sync_sources.py` consulta as URLs, usa retry/backoff, valida o conteúdo e grava o cache local em `db/source_cache/`, que é ignorado pelo Git.

A sincronização também descobre PDFs diretamente linkados por páginas oficiais selecionadas. PDFs manuais continuam permitidos em `pdfs/` e, quando versionados, devem terminar em `.DDMMAAAA.pdf`, por exemplo `.27082026.pdf`.

```bash
python scripts/sync_sources.py
python ingest.py
```

Para somente verificar as fontes obrigatórias, sem gravar cache:

```bash
python scripts/sync_sources.py --check --required-only
```

### Federal

Constituição; Lei 14.133/2021; Decreto 12.807/2025; LINDB; Decreto-Lei 200/1967; Lei 9.784/1999; improbidade; anticorrupção; LAI; LGPD; estatais; concessões; PPPs; LRF; Lei 4.320/1964; LC 123/2006; Lei 13.019/2014; Governo Digital; PCA; agentes e fiscais; SRP; credenciamento; ETP; TR; dispensa eletrônica; pesquisa de preços; meio ambiente; resíduos; acessibilidade; além das alterações recentes da Lei 14.133/2021 e regulamentações conexas.

Entre os acréscimos recentes estão Lei 14.770/2023, Lei 14.981/2024, Decreto 12.174/2024 e atualização pelo Decreto 12.926/2026, Decreto 12.304/2024, Decreto 12.771/2025, Lei 15.190/2025, Lei 15.210/2025, Lei 15.266/2025, Decreto 13.031/2026, Decreto 13.106/2026 e Lei 15.471/2026.

Leis 8.666/1993, 10.520/2002 e RDC permanecem como corpus histórico e são marcadas como `revogado`. A Lei paulista 6.544/1989 é preservada como `historico`, para evitar que o modelo a trate automaticamente como regime geral atual.

### São Paulo

Constituição Estadual; Lei 10.177/1998; LC 709/1993; Lei 6.544/1989; regulamentação paulista da Lei 14.133/2021; PCA; pesquisa de preços; ETP; catálogo; TR; agentes; contratação direta; leilão; AUDESP; integridade; responsabilização; Marketplace.SP; Compras SP e TCESP.

### Controle, orientação e jurisprudência

TCU, TCESP, AGU, PNCP, Compras.gov.br, Compras SP, STJ e STF têm `source_role` explícito. Jurisprudência, manual, guia e orientação nunca são tratados como texto legal pelo prompt.

Doutrina comercial protegida não deve ser copiada integralmente sem licença. Prefira materiais públicos, licenciados e referências temáticas.

## Recuperação jurídica

- Dense + BM25 + RRF.
- Chunking estrutural por artigo/súmula antes do split por tamanho.
- Cada fragmento mantém `source_id`, `unit_id`, `unit_ref`, `chunk_index` e páginas quando aplicáveis.
- Reranker independente do LLM.
- Relevância é o critério primário; autoridade só desempata.
- `RAG_MIN_EVIDENCE_SCORE` impede chamar o LLM quando não há evidência suficientemente relevante.
- Citações `[F#]` para afirmações jurídicas relevantes.
- Filtros: `@jurisdicao=estadual_sp @ano=2026 ...`.

## Temporalidade

O corpus carrega `status`, `effective_from`, `effective_to`, `revogado`, `data_vigencia` e `retrieved_at`. A resposta deve distinguir regra vigente, regra histórica e `vacatio_legis`.

A IN SEGES/MGI 512/2025 está marcada com início de vigência em 30/11/2026, em conjunto com a IN 129/2026 que posterga a entrada em vigor. O histórico de alterações entre versões ainda é uma evolução futura do coletor.

## RTX 5060 Ti 16 GB

Recuperação e LLM permanecem desacoplados. FastEmbed pode usar:

```text
RAG_FASTEMBED_PROVIDERS=CUDAExecutionProvider
```

Isso permite reservar VRAM para o modelo de geração. Trocar o gerador local não exige reindexação.

## Jurisprudência estruturada — próxima etapa

A próxima evolução recomendada é o coletor estruturado TCESP + TCU + STJ + STF, com esquema comum em `jurisprudencia/schema.py` contendo processo, órgão julgador, relator, data, ementa, assunto, tese, inteiro teor, URL oficial, tipo de decisão e hash/metadata de coleta.

O roadmap está em `docs/JURISPRUDENCIA_ROADMAP_28082026.md`. A ordem sugerida é TCU (dados abertos), TCESP, STJ e STF, sempre preservando o inteiro teor e a fonte oficial.

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

`ci.yml` testa e compila sem depender de sites jurídicos externos. `sync-sources.yml` verifica fontes oficiais obrigatórias semanalmente/manual e não faz commits automáticos.

O CI que estava vermelho por falha em `test_structural_chunking_keeps_article_unit` já foi corrigido; o último workflow na `main` terminou com sucesso. O parser agora também cobre `Artigo 1º`, `Art. 10-A` e documentos que contenham apenas um artigo.

## Verificações

```bash
python -m compileall -q .
python -m pytest -q
python scripts/sync_sources.py --check --required-only
```
