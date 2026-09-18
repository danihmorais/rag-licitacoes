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

Legislação pública não fica congelada em PDFs no Git. `scripts/sources.py` mantém o catálogo jurídico unificado, com metadados de jurisdição, esfera, órgão, papel da fonte, autoridade, status e ramo do Direito. `scripts/sync_sources.py` consulta as URLs, usa retry/backoff, valida o conteúdo e grava o cache local em `db/source_cache/`, que é ignorado pelo Git. Páginas de índice/discovery podem ser usadas para localizar atos novos, mas não entram no corpus como evidência jurídica (`index_only=True`).

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

O núcleo cobre Constituição e controle de constitucionalidade; Administração Pública, processo administrativo e LINDB; servidores e responsabilização; licitações e contratos; controle e precedentes; Direito Financeiro e Orçamentário; Direito Tributário; concessões, PPPs, regulação e serviços públicos; consórcios e federalismo cooperativo; transparência, proteção de dados e governo digital; urbanismo e patrimônio; meio ambiente; saúde, educação e assistência social; direitos de grupos protegidos; defesa civil; ciência, tecnologia e inovação; e legislação eleitoral. A Lei 14.133/2021 permanece como núcleo de contratações públicas, mas deixa de ser o limite temático do RAG.

Leis 8.666/1993, 10.520/2002 e RDC permanecem como corpus histórico e são marcadas como `revogado`. A Lei paulista 6.544/1989 é preservada como `historico`, para evitar que o modelo a trate automaticamente como regime geral atual.

### São Paulo

Constituição Estadual; Lei 10.177/1998; LC 709/1993; Lei 6.544/1989; regulamentação paulista da Lei 14.133/2021; PCA; pesquisa de preços; ETP; catálogo; TR; agentes; contratação direta; leilão; AUDESP; integridade; responsabilização; Marketplace.SP; Compras SP e TCESP.

### Controle, orientação e jurisprudência

TCU, TCESP, STJ, STF, TCM-SP e TJSP são tratados pelo coletor estruturado de jurisprudência. As pesquisas usam as bases oficiais de cada órgão e salvam registros individuais como documentos indexáveis; páginas genéricas de pesquisa não entram no índice como evidência. O inteiro teor é opcional: com `--with-content`, o coletor tenta recuperar o documento integral quando a própria fonte oferece PDF ou página de detalhe. Jurisprudência, parecer, manual, guia e orientação nunca são tratados como texto legal.

| Fonte | Coletor | Indexação | Inteiro teor |
|---|---|---|---|
| TCU | Sim | Sim | Opcional |
| TCESP | Sim | Sim | Opcional |
| STJ | Sim | Sim | Opcional |
| STF | Sim | Sim | Opcional |
| TCM-SP | Sim | Sim | Opcional |
| TJSP | Sim | Sim | Opcional |

O TCU possui webservice oficial de acórdãos com URL de texto, DOC e PDF. O TCESP mantém pesquisa de jurisprudência com resultados de decisões, súmulas e boletins. O STJ disponibiliza o SCON para pesquisa de jurisprudência. O TCM-SP mantém consulta oficial de julgados e jurisprudência. O TJSP disponibiliza a Consulta Completa do segundo grau, incluindo Pesquisa Livre no inteiro teor dos acórdãos.

Doutrina comercial protegida não deve ser copiada integralmente sem licença. Prefira materiais públicos, licenciados e referências temáticas.

## Política de autoridade e jurisdição

A recuperação usa uma escala única: authority_level=1 para norma, 2 para jurisprudência/controle, 3 para orientação oficial e 4 para doutrina. Dentro das normas, normative_rank distingue Constituição, lei, decreto e ato infralegal. O score final é ponderado por relevância (0.68), autoridade (0.20) e jurisdição (0.12) antes do limite de FINAL_K. A ponderação jurisdicional só atua quando a jurisdição pode ser determinada pelos filtros estruturados ou por indicadores explícitos da consulta; sem essa evidência, o componente permanece neutro. TCM-SP usa jurisdicao=municipal_sp e não é misturado com TCESP.

## Cobertura jurídica ampliada

O catálogo inclui as bases adicionais de controle e responsabilização (Lei nº 4.717/1965, Lei nº 7.347/1985 e LC nº 131/2009), transparência e LAI (Decreto nº 7.724/2012 e Decreto SP nº 68.155/2023), terceirização (Lei nº 6.019/1974), controle judicial (Lei nº 12.016/2009), inovação (LC nº 182/2021), além da regulamentação municipal de contratações de São Paulo e pareceres/orientações da PGE-SP. As leis 14.230/2021, LC 173/2020, Lei 12.232/2010 e Leis 10.973/2004 e 13.243/2016 já pertenciam ao catálogo e permanecem nele.

## Coletor estruturado de jurisprudência

A jurisprudência possui um esquema independente do LLM em `jurisprudencia/schema.py` e adaptadores dedicados em `jurisprudencia/collector.py`. Portais de pesquisa jurisprudencial não são indexados pelo sincronizador genérico de fontes. O objetivo é transformar resultados de pesquisa em registros com processo, órgão/tribunal, relator, data, ementa, tese/decisão, assunto, URL oficial, situação e hash de versão.

O TCU é coletado pela interface oficial de dados abertos de acórdãos, o TCESP pela pesquisa oficial, o STJ pelo SCON, o STF pelo portal oficial e o TCM-SP pelo portal oficial de jurisprudência municipal. Quando a fonte oferece PDF de inteiro teor, o coletor pode preservá-lo como texto com `--with-content`.

```bash
python -m jurisprudencia.collector --query "licitação" --limit 25
python -m jurisprudencia.collector --tribunais tcu,tcesp,stj,stf,tcm-sp,tjsp --query "contrato administrativo" --limit 50 --detail --with-content --strict
```

Na execução normal de `ingest.py`, a coleta pode ocorrer automaticamente. Com `RAG_JURISPRUDENCIA_STRICT=1`, a ingestão falha se algum dos tribunais solicitados não produzir nenhum registro na coleta temática.

```text
RAG_SYNC_JURISPRUDENCIA=1
RAG_JURISPRUDENCIA_QUERY=licitação
RAG_JURISPRUDENCIA_LIMIT=25
RAG_JURISPRUDENCIA_STRICT=1
```

Cada registro recebe `version_sha256`, de modo que uma alteração do conteúdo não apaga silenciosamente a versão anterior.

## Recuperação jurídica

- Dense + BM25 + RRF.
- Chunking estrutural por artigo/súmula antes do split por tamanho.
- Cada fragmento mantém `source_id`, `unit_id`, `unit_ref`, `chunk_index`, `document_hash` e páginas quando aplicáveis.
- Reranker independente do LLM.
- O reranking combina relevância, autoridade e jurisdição antes do corte de FINAL_K; autoridade não é apenas um critério de desempate.
- Após o reranking, chunks vizinhos da mesma `unit_id` podem completar o contexto sem influenciar a relevância inicial.
- `RAG_MIN_EVIDENCE_SCORE` impede chamar o LLM quando não há evidência suficientemente relevante.
- Citações `[F#]` para afirmações jurídicas relevantes.
- Filtros: `@jurisdicao=estadual_sp @ano=2026 ...`.
- `RAG_RERANK_SCORE_MODE=sigmoid` interpreta o score padrão do cross-encoder como logit; `identity` fica disponível para rerankers que já devolvem score normalizado entre 0 e 1.
- Documentos recuperados são tratados como dados, não como instruções; ordens inseridas no texto do documento não devem alterar o comportamento do modelo.

## Integridade do índice

O manifesto registra modelo, dimensão, parâmetros de chunking, reranker e esquema. Alterações incompatíveis interrompem a consulta e exigem reindexação. Manifesto e cache de ingestão são gravados atomicamente.

O cache de ingestão usa versão própria e guarda `sha256` e quantidade de chunks. Um documento é reindexado quando mudou ou quando sua quantidade indexada não confere com o cache. Por padrão, `RAG_PRUNE_STALE=1` remove do Qdrant fontes que já não pertencem ao corpus atual, evitando documentos órfãos.

O ingest também valida a dimensão dos embeddings densos antes de substituir os pontos existentes. Assim, falhas de modelo/embedding não destroem o índice válido anterior.

## Consulta não interativa

Para integração com scripts e serviços, a consulta pode ser executada sem modo interativo:

```bash
python query.py --query "Quais são os requisitos do ETP?"
python query.py --query "@jurisdicao=estadual_sp @ano=2026 regra do ETP" --json
```

`--json` retorna apenas o objeto da consulta, com resposta e fontes recuperadas. O uso normal continua disponível com `python query.py`.

## Temporalidade

O corpus carrega `status`, `effective_from`, `effective_to`, `revogado`, `data_vigencia` e `retrieved_at`. A resposta deve distinguir regra vigente, regra histórica e `vacatio_legis`.

O histórico de alterações é controlado por hash dos documentos. A ingestão não substitui uma versão antiga antes de concluir a indexação da nova.

## RTX 5060 Ti 16 GB

Recuperação e LLM permanecem desacoplados. Para gerar embeddings na GPU, use o perfil `requirements-gpu.txt` em um ambiente novo. O FastEmbed oficial exige `fastembed-gpu` para execução em GPU; `fastembed` e `fastembed-gpu` não devem coexistir no mesmo ambiente.

```bash
python -m venv .venv-gpu
source .venv-gpu/bin/activate
pip install -r requirements-gpu.txt
cp .env.example .env
```

No `.env`, habilite:

```text
RAG_FASTEMBED_PROVIDERS=CUDAExecutionProvider
```

A implementação usa a mesma coleção Qdrant para CPU e GPU; mudar apenas o provedor de execução não altera os vetores. Trocar o modelo de embedding, porém, exige reindexação e atualização do manifesto.

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

O projeto é validado em Python 3.12 no CI. Essa escolha é intencional para o `fastembed 0.8.0`; há relatos de falha no `SparseTextEmbedding` com Python 3.14.2 em Linux.

## GitHub Actions

`ci.yml` compila e testa apenas lógica determinística; não depende de sites jurídicos externos.

`sync-sources.yml` é um health-check separado e não bloqueante: indisponibilidade temporária de Planalto, TCESP, TCU ou outro site não deixa o branch vermelho. A lógica de parsing das fontes continua coberta pelo CI offline, com fixtures que rejeitam casca de SPA, exigem identidade normativa e validam documentos de orientação oficial.

O CI cobre chunking estrutural, filtros, política de autoridade/jurisdição, catálogo de fontes, regressão de conteúdo jurídico, parsing dos adaptadores de jurisprudência (incluindo TCM-SP), compatibilidade de configuração, cache de ingestão, limpeza de fontes obsoletas e respostas OpenAI-compatible.

Foi corrigido o caso de regex de PDF com escape duplicado que fazia `discover_links()` ignorar PDFs oficiais. O normalizador aceita regex normal e duplamente escapado.

## Verificações

```bash
python -m compileall -q .
python -m pytest -q
python scripts/sync_sources.py --check --required-only
```
