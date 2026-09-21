# Revisão do RAG de Licitações — 26/08/2026

## Diagnóstico

O corpus existente estava concentrado em poucos documentos e alguns PDFs auxiliares continham apenas texto introdutório/metadados, em vez da íntegra normativa. Para um RAG jurídico isso é especialmente perigoso: o recuperador pode localizar uma ementa ou descrição sem ter o dispositivo legal necessário para responder.

A arquitetura atual já possui boas bases para um RAG intercambiável entre LLMs: Qdrant, busca densa + esparsa, reranking, metadados e separação do provedor de LLM. O principal ganho agora é tornar o corpus verificável e a compatibilidade do índice explícita.

## Corpus prioritário

### Federal

- Lei nº 14.133/2021, texto compilado.
- Decreto nº 12.807/2025, com os valores da Lei nº 14.133 vigentes em 2026.
- LINDB (Decreto-Lei nº 4.657/1942).
- Lei nº 9.784/1999 (processo administrativo).
- Lei nº 8.429/1992, com as alterações da Lei nº 14.230/2021 (improbidade).
- Lei nº 12.846/2013 (anticorrupção).
- Lei nº 12.527/2011 (acesso à informação).
- Lei nº 13.709/2018 (LGPD).
- Lei nº 8.987/1995 (concessões e permissões).
- Lei nº 11.079/2004 (PPPs).
- Lei nº 14.129/2021 (Governo Digital).

### Estado de São Paulo

- Lei estadual nº 10.177/1998 (processo administrativo).
- Decretos nº 67.608/2023, 67.689/2023, 67.885/2023, 67.888/2023, 67.985/2023, 68.021/2023, 68.185/2023, 68.220/2023, 68.304/2024 e 68.422/2024.
- Resolução SGGD nº 34/2026, que institui o Marketplace.SP para as hipóteses de credenciamento do art. 79 da Lei nº 14.133/2021.

## Melhorias arquiteturais

1. **Não amarrar o índice ao LLM.** LLM, embedding, reranker e banco vetorial devem ser componentes independentes. Trocar Gemma/Qwen/Llama não deve exigir reprocessar o corpus.
2. **Amarrar o índice ao embedding.** O índice vetorial deve registrar modelo, dimensão, normalização, prefixo de consulta e versão. Trocar embedding sem reindexação é incompatível.
3. **Busca híbrida + reranking.** Para texto jurídico, termos como artigo, inciso, número de decreto e expressão exata têm peso alto; dense-only tende a perder precisão lexical.
4. **Chunking estrutural.** Priorizar artigo/parágrafo/inciso/alínea, mantendo a unidade normativa completa quando couber e informando `unit_ref`, `page` e `source`.
5. **Metadados jurídicos.** Registrar, no mínimo, `jurisdiction`, `authority_level`, `document_type`, `norm_number`, `norm_year`, `status`, `effective_from`, `effective_to`, `source_url` e `retrieved_at`.
6. **Conflitos e vigência.** Uma resposta não deve simplesmente juntar trechos de normas revogadas e vigentes. O pipeline precisa permitir filtragem por vigência e priorização por hierarquia normativa.
7. **Citações verificáveis.** O gerador deve exigir referências `[F#]` para afirmações jurídicas e preservar página/dispositivo recuperado.
8. **Atualização incremental.** Hash do PDF + manifest do índice evita reprocessar tudo quando somente um documento muda.
9. **Avaliação automática.** Criar um conjunto de perguntas jurídicas com resposta esperada e medir recall@k, MRR/nDCG, precisão das citações e taxa de alucinação.
10. **OCR separado.** PDFs digitalizados devem passar por OCR antes do chunking; não misturar texto OCR com texto nativo sem marcar a origem.
11. **Temporalidade.** Guardar o documento original e alterações relevantes. O RAG deve poder responder tanto “qual é a regra vigente?” quanto “qual era a regra em determinada data?”.
12. **Modelo local.** Em uma RTX 5060 Ti 16 GB, manter o LLM desacoplado do pipeline permite testar modelos quantizados diferentes sem reconstruir o índice. Embedding/reranker podem rodar em CPU se a VRAM estiver reservada ao LLM.

## Atualização contínua

O workflow `build-legal-pdfs.yml` baixa as fontes oficiais e reconstrói os PDFs a partir delas. Isso evita manter manualmente cópias textuais desatualizadas. O sufixo `.26082026` é preservado conforme solicitado; a data efetiva de obtenção também é registrada dentro do PDF.
