# RAG de Licitações

RAG híbrido para licitações, contratos administrativos, Direito Público e regulamentação de São Paulo, com busca densa + BM25, RRF, reranking, recuperação estrutural por unidade jurídica, jurisprudência estruturada e LLM intercambiável.

## Arquitetura

```text
fontes oficiais HTML/PDF -> sincronização -> cache local -> metadados/versionamento
                                      -> jurisprudência estruturada
                                      -> chunking jurídico -> dense + BM25
                                      -> Qdrant -> RRF -> reranker
                                      -> expansão de vizinhança -> contexto -> LLM
```

O LLM é desacoplado do índice: Qwen, Gemma, Llama, Gemini, llama.cpp, LM Studio, vLLM, Ollama ou qualquer endpoint OpenAI-compatible podem ser trocados sem reindexação quando somente o gerador muda.

## Melhorias de confiabilidade

- **Ingestão versionada e segura:** uma nova versão do documento é inserida primeiro; a versão anterior só é removida depois do `upsert` bem-sucedido. Uma falha de embedding/indexação não destrói a evidência que já funcionava.
- **Hash do documento no payload:** cada chunk recebe `document_hash`, permitindo coexistência transitória de versões e limpeza seletiva de versões antigas.
- **Chunking jurídico estrutural:** artigos e súmulas são identificados antes do split por tamanho.
- **Expansão de vizinhança pós-reranking:** depois de selecionar as melhores evidências, o sistema recupera chunks adjacentes da mesma unidade jurídica. Isso ajuda quando incisos, parágrafos ou alíneas ficaram separados pelo limite de tamanho sem permitir que o vizinho altere o ranking de relevância.
- **Filtros controlados:** filtros desconhecidos são rejeitados em vez de serem enviados silenciosamente ao Qdrant.
- **Manifesto de compatibilidade:** mudanças de modelo, chunking ou estratégia de contexto invalidam explicitamente um índice antigo e exigem reindexação.
- **Citações rastreáveis:** o contexto informa fonte, página, unidade, papel da fonte, autoridade, jurisdição, status e vigência.

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

Leis 8.666/1993, 10.520/2002 e RDC permanecem como corpus histórico e são marcadas como `revogado`. A Lei paulista 6.544/1989 é preservada como `historico`, para evitar que o modelo a trate automaticamente como regime geral atual.

### São Paulo

Constituição Estadual; Lei 10.177/1998; LC 709/1993; Lei 6.544/1989; regulamentação paulista da Lei 14.133/2021; PCA; pesquisa de preços; ETP; catálogo; TR; agentes; contratação direta; leilão; AUDESP; integridade; responsabilização; Marketplace.SP; Compras SP e TCESP.

### Controle, orientação e jurisprudência

TCU, TCESP, AGU, PNCP, Compras.gov.br, Compras SP, STJ e STF têm `source_role` explícito. Jurisprudência, manual, guia e orientação nunca são tratados como texto legal pelo prompt.

Doutrina comercial protegida não deve ser copiada integralmente sem licença. Prefira materiais públicos, licenciados e referências temáticas.

## Coletor estruturado de jurisprudência

A jurisprudência possui um esquema independente do LLM em `jurisprudencia/schema.py` e adaptadores em `jurisprudencia/collector.py`. O objetivo é transformar resultados de pesquisa em registros com processo, órgão/tribunal, relator, data, ementa, tese/decisão, assunto, URL oficial, situação e hash de versão.

O TCU é coletado pela interface oficial de dados abertos de acórdãos, o TCESP pela pesquisa oficial, o STJ pelo SCON e o STF pelo portal oficial de jurisprudência. Quando a fonte oferece PDF de inteiro teor, o coletor pode preservá-lo como texto com `--with-content`.

```bash
python -m jurisprudencia.collector --query "licitação" --limit 25
python -m jurisprudencia.collector --tribunais tcu,tcesp,stj,stf --query "contrato administrativo" --limit 50 --detail
```

Na execução normal de `ingest.py`, a coleta pode ocorrer automaticamente. Configure:

```text
RAG_SYNC_JURISPRUDENCIA=1
RAG_JURISPRUDENCIA_QUERY=licitação
RAG_JURISPRUDENCIA_LIMIT=25
```

Cada registro recebe `version_sha256`, de modo que uma alteração do conteúdo não apaga silenciosamente a versão anterior.

## Recuperação jurídica

- Dense + BM25 + RRF.
- Chunking estrutural por artigo/súmula antes do split por tamanho.
- Cada fragmento mantém `source_id`, `unit_id`, `unit_ref`, `chunk_index`, `document_hash` e páginas quando aplicáveis.
- Reranker independente do LLM.
- Relevância é o critério primário; autoridade só desempata.
- Após o reranking, chunks vizinhos da mesma `unit_id` podem completar o contexto sem influenciar a relevância inicial.
- `RAG_MIN_EVIDENCE_SCORE` impede chamar o LLM quando não há evidência suficientemente relevante.
- Citações `[F#]` para afirmações jurídicas relevantes.
- Filtros: `@jurisdicao=estadual_sp @ano=2026 @status=vigente` e demais campos suportados pelo payload.

## Temporalidade

O corpus carrega `status`, `effective_from`, `effective_to`, `revogado`, `data_vigencia` e `retrieved_at`. A resposta deve distinguir regra vigente, regra histórica e `vacatio_legis`.

O histórico de alterações é controlado por hash dos documentos. A ingestão não substitui uma versão antiga antes de concluir a indexação da nova.

## RTX 5060 Ti 16 GB

Recuperação e LLM permanecem desacoplados. FastEmbed pode usar `RAG_FASTEMBED_PROVIDERS=CUDAExecutionProvider`, reservando VRAM para o modelo de geração. Trocar o gerador local não exige reindexação, salvo quando mudar o modelo de embedding ou sua dimensão.

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

`ci.yml` compila e testa a lógica determinística sem depender de sites jurídicos externos. O health-check de fontes é separado e não bloqueante.

## Verificações

```bash
python -m compileall -q .
python -m pytest -q
python scripts/sync_sources.py --check --required-only
```
