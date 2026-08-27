# Revisão do RAG de Licitações — 27/08/2026

## Mudança principal

O corpus jurídico oficial deixa de depender de PDFs versionados no Git. `scripts/sync_sources.py` consulta fontes oficiais, usa retry/backoff e URLs alternativas, valida o conteúdo e mantém cache local ignorado pelo Git.

Isso resolve a principal falha observada no GitHub Actions: o runner recebeu `RemoteDisconnected` em várias páginas do Planalto e timeout na Câmara. O workflow antigo abortava quando qualquer uma das 34 fontes falhava, embora as fontes paulistas fossem processadas corretamente.

## Corpus prioritário

### Federal — legislação primária

- Constituição Federal de 1988.
- Lei nº 14.133/2021.
- Decreto nº 12.807/2025.
- LINDB — Decreto-Lei nº 4.657/1942.
- Lei nº 9.784/1999.
- Lei nº 8.429/1992.
- Lei nº 12.846/2013 e Decreto nº 11.129/2022.
- LAI, LGPD, Lei nº 13.303/2016, Lei nº 8.987/1995, Lei nº 11.079/2004.
- LRF e Lei nº 4.320/1964.
- Meio ambiente, resíduos sólidos, acessibilidade e normas correlatas quando pertinentes à contratação.
- Normas federais de planejamento, ETP, TR e pesquisa de preços.

### São Paulo

- Constituição Estadual.
- Lei nº 10.177/1998.
- LC nº 709/1993.
- Lei nº 6.544/1989.
- Regulamentação paulista da Lei nº 14.133/2021 para PCA, pesquisa de preços, ETP, TR, agentes, contratação direta e leilão.
- Normas recentes de integridade, responsabilização e Marketplace.SP.
- TCESP, especialmente súmulas e jurisprudência de controle.

### Fontes institucionais

TCU, TCESP, AGU, PNCP, Compras.gov.br e Compras SP entram com `source_role` explícito. Orientação, manual e jurisprudência não são tratados como lei pelo prompt.

Doutrina comercial protegida por direitos autorais não deve ser copiada integralmente sem licença.

## Recuperação

- Dense + BM25 + RRF.
- Chunking estrutural por artigo/súmula antes do split por tamanho.
- `source_id`, `unit_id`, `chunk_index`, página e metadados jurídicos preservados.
- Reranker independente do LLM.
- Relevância do reranker é primária; autoridade funciona como critério secundário.
- Se nenhum trecho for recuperado, o LLM não é chamado.
- Citações `[F#]` são obrigatórias para afirmações jurídicas relevantes.

## Intercambialidade de modelos

Trocar o LLM não exige reindexação. São suportados Ollama, Gemini e endpoints OpenAI-compatible como llama.cpp, LM Studio, vLLM e OpenRouter. Mudanças no embedding, reranker, chunking, prefixos ou schema exigem reindexação e são detectadas pelo manifest.

## Temporalidade

O índice contempla `data_publicacao`, `data_vigencia`, `effective_from`, `effective_to`, `status`, `revogado`, `norma_alteradora` e `retrieved_at`. A próxima evolução é extrair relações entre norma alteradora e dispositivos alterados para responder com precisão histórica.

## Próximas prioridades

1. Coletor estruturado de acórdãos TCESP/TCU/STJ/STF com processo, órgão julgador, relator, data, assunto e ementa.
2. OCR explícito para PDFs escaneados, com `text_origin=native|ocr` e confiança por página.
3. Dataset de avaliação com recall@k, MRR/nDCG, cobertura de citação, precisão de jurisdição e temporalidade.
4. Catálogos separados para jurisprudência, orientação oficial e doutrina.
5. Melhor modelagem das relações entre normas alteradoras e dispositivos alterados.
