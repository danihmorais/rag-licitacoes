# Revisão do RAG de Licitações — 27/08/2026

## Diagnóstico e mudanças

A arquitetura já estava corretamente orientada para desacoplar o LLM do mecanismo de recuperação: Qdrant, busca densa + BM25, RRF, reranking, metadados e adapters de LLM. Isso permite trocar Qwen, Gemma, Llama, Gemini ou outro endpoint OpenAI-compatible sem reindexar quando somente o gerador muda. O código agora explicita ainda mais essa fronteira e incrementa a versão do índice quando a representação recuperável muda.

### Melhorias implementadas

- `INDEX_VERSION` elevado para 5 porque chunking/metadados/prefixos do embedding fazem parte da compatibilidade do índice.
- Manifest passou a registrar os prefixos `passage:` e `query:` do multilingual-e5-large.
- Chunking estrutural preserva unidades normativas e melhora separadores para textos jurídicos sem fragmentar artificialmente artigo, parágrafo e inciso.
- Metadados passaram a reconhecer melhor a jurisdição estadual paulista e fontes normativas estaduais.
- Prompt jurídico passou a tratar explicitamente temporalidade, jurisdição, hierarquia de autoridade e distinção entre norma, jurisprudência, orientação oficial e doutrina.
- Reranking mantém diversidade por unidade jurídica e aplica autoridade somente como critério posterior, evitando que o RAG substitua relevância semântica por uma ordenação cega.
- Gerador de PDFs passou a falhar quando uma fonte normativa retorna conteúdo pequeno ou que não aparenta ser texto legislativo; isso evita incorporar páginas de pesquisa/menus como se fossem legislação.
- O corpus jurídico foi ampliado com normas federais transversais e normas paulistas relevantes à contratação pública, anticorrupção e integridade.

## Corpus prioritário

### Federal — legislação primária

- Lei nº 14.133/2021 — Licitações e Contratos Administrativos.
- Decreto nº 12.807/2025 — atualização anual dos valores da Lei nº 14.133/2021.
- LINDB — Decreto-Lei nº 4.657/1942.
- Decreto-Lei nº 200/1967 — organização administrativa federal.
- Lei nº 9.784/1999 — processo administrativo federal.
- Lei nº 8.429/1992 — improbidade administrativa, considerada sua redação vigente.
- Lei nº 12.846/2013 e Decreto nº 11.129/2022 — responsabilização anticorrupção.
- Lei nº 12.527/2011 — acesso à informação.
- Lei nº 13.709/2018 — LGPD.
- Lei nº 13.460/2017 — usuários de serviços públicos.
- Lei nº 14.129/2021 — Governo Digital.
- Lei nº 13.303/2016 — empresas estatais.
- Lei nº 8.987/1995 — concessões e permissões.
- Lei nº 11.079/2004 — PPPs.
- LC nº 101/2000 — responsabilidade fiscal.
- Lei nº 4.320/1964 — direito financeiro.

### Estado de São Paulo

- Constituição do Estado de São Paulo.
- Lei nº 10.177/1998 — processo administrativo estadual.
- LC nº 709/1993 — Lei Orgânica do TCESP.
- Regulamentação paulista da Lei nº 14.133/2021: Decretos nº 67.608/2023, 67.689/2023, 67.885/2023, 67.888/2023, 67.985/2023, 68.017/2023, 68.021/2023, 68.185/2023, 68.220/2023, 68.304/2024 e 68.422/2024.
- Decreto nº 69.588/2025 — responsabilização administrativa de pessoas jurídicas.
- Decreto nº 69.861/2025 — programas de integridade.
- Resolução SGGD nº 34/2026 — Marketplace.SP/credenciamento.

## O que ainda deve entrar no corpus

A prioridade seguinte é ampliar a jurisprudência estruturada, não simplesmente despejar PDFs grandes no índice:

1. TCESP: súmulas, comunicados, decisões e julgados diretamente relacionados à Lei nº 14.133/2021, com número do processo, órgão julgador, data e assunto.
2. TCU: acórdãos de referência em planejamento, ETP, pesquisa de preços, contratação direta, habilitação, sanções, gestão/fiscalização e obras.
3. STJ/STF: precedentes com pertinência direta a contratos administrativos, licitações, sanções, improbidade, responsabilidade civil e processo administrativo.
4. AGU/Compras.gov/Compras SP: modelos oficiais e orientações, classificados como `orientacao_oficial`, nunca como norma.
5. Obras e engenharia: orçamento, BDI, SINAPI/SICRO, matriz de riscos, fiscalização, medição e recebimento.
6. TIC: contratação de soluções de tecnologia, segurança, dados e serviços continuados.
7. Terceiro setor e instrumentos correlatos somente quando o caso de uso exigir, mantendo-os separados do regime geral da Lei nº 14.133.

## RAG jurídico: recomendações estruturais

### 1. Temporalidade de primeira classe

Cada norma deve ter `data_publicacao`, `data_vigencia`, `effective_from`, `effective_to`, `status`, `norma_alteradora` e, quando possível, a relação de dispositivos alterados. O sistema precisa responder tanto “qual é a regra vigente?” quanto “qual era a regra em 2024?”.

### 2. Unidade jurídica como identidade

O identificador ideal é algo como `Lei 14133/2021::art. 75::§ 1º`, e não apenas um chunk arbitrário. Isso permite deduplicação, agrupamento, citação precisa e recuperação de toda a unidade quando um fragmento for selecionado.

### 3. Recuperação híbrida

Manter dense + BM25 + RRF. Números de artigos, decretos, processos, súmulas e expressões exatas têm forte valor lexical. Embedding não deve ser tratado como substituto de BM25.

### 4. Reranker independente do LLM

O reranker continua separado do gerador. Isso é especialmente importante na RTX 5060 Ti 16 GB: é possível manter o gerador quantizado na GPU e executar parte da recuperação em CPU, ou alternar modelos sem reconstruir o corpus.

### 5. Avaliação

Criar `eval/` com perguntas reais de licitações paulistas e respostas esperadas. Medir pelo menos recall@k, MRR/nDCG, cobertura de citação, precisão de jurisdição, precisão temporal e taxa de resposta sem suporte.

### 6. OCR

PDF escaneado deve passar por OCR antes da indexação. O resultado deve carregar `text_origin=native|ocr` e, idealmente, confiança por página. Não tratar OCR ruim como texto legislativo confiável.

### 7. Fontes oficiais como requisito

Para legislação, preferir Planalto, ALESP/Diário Oficial, TCESP, TCU, STF, STJ, AGU, Compras.gov.br e Compras SP conforme a competência da fonte. Doutrina comercial não deve ser copiada integralmente no corpus sem licença.

## Atualização do corpus

Os PDFs jurídicos gerados pelo workflow recebem o sufixo `.27082026` quando esta revisão é executada. A data de coleta também é gravada no PDF e no sidecar JSON. O workflow falha se uma fonte normativa retornar conteúdo insuficiente, reduzindo o risco de indexar uma página de navegação como legislação.
