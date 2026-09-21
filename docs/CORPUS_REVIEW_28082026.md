# Revisão do corpus e arquitetura — 28/08/2026

## Decisão

Não versionar cópias congeladas de legislação pública. O catálogo mantém URLs oficiais, metadados jurídicos, status temporal e hierarquia de autoridade; a execução baixa HTML/PDF e transforma o conteúdo em cache local.

Os PDFs jurídicos que existiam no histórico (Constituição, Lei 14.133/2021, Decreto 12.807/2025, materiais AGU/TCU/STJ/TCESP e dossiês paulistas) foram removidos anteriormente. O novo fluxo mantém o corpus por consulta oficial automática.

## Fontes federais

Prioridades: Constituição; Lei 14.133/2021; Decreto 12.807/2025; LINDB; Decreto-Lei 200/1967; Lei 9.784/1999; improbidade; anticorrupção; LAI; LGPD; estatais; concessões; PPPs; LRF; Lei 4.320/1964; LC 123/2006; Lei 13.019/2014; Governo Digital; PCA; agentes/fiscais; SRP; credenciamento; ETP; TR; dispensa eletrônica e pesquisa de preços.

Normas históricas 8.666/1993, 10.520/2002 e RDC são marcadas `revogado` para consultas de documentos legados, sem contaminar respostas sobre a regra vigente.

A Lei 14.133/2021 é a norma central; o texto oficial está no Planalto/Câmara e os valores são atualizados pelo Decreto 12.807/2025.

## Temporalidade

A IN SEGES/MGI 512/2025 foi catalogada com `vacatio_legis` e `effective_from=2026-11-30`; a IN 129/2026 registra a postergação. Isso impede apresentar uma regra futura como vigente em 28/08/2026.

## São Paulo

Foram incluídos Constituição Estadual, Lei 10.177/1998, LC 709/1993, Lei 6.544/1989 e os decretos paulistas de transição, PCA, pesquisa de preços, bens de luxo, ETP, catálogo, TR, agentes, contratação direta, leilão e AUDESP, além de integridade, responsabilização, Marketplace.SP, Compras SP e TCESP.

A Deliberação do TCESP de 01/07/2026, publicada em 09/07/2026, sobre SRP e adesão por não participantes entrou no catálogo por sua relevância direta às contratações paulistas.

## Automação

`scripts/sync_sources.py` agora:

1. consulta a fonte oficial;
2. detecta HTML/PDF;
3. extrai texto;
4. valida conteúdo;
5. segue PDFs diretamente linkados por páginas oficiais selecionadas;
6. grava `.txt` + `.json` no cache ignorado pelo Git;
7. registra URL final, host, SHA-256, papel, autoridade e temporalidade.

## Recuperação

O parser jurídico reconhece `Art. 1º`, `Artigo 1º`, `Art. 10-A` e equivalentes. A busca continua dense + BM25 + RRF + cross-encoder. Foi acrescentado um gate de evidência antes da chamada do LLM.

## CI

O último CI vermelho tinha 5 testes aprovados e 1 falha no parser de artigos. A correção tornou o reconhecimento estrutural explícito e adicionou testes. Os workflows foram separados: CI determinístico e verificação semanal de fontes, sem commits automáticos.

## Próximos passos

1. Coletor estruturado de jurisprudência TCU/TCESP/STJ/STF com processo, órgão julgador, relator, data, assunto, ementa e inteiro teor.
2. OCR explícito para PDFs digitalizados, com `text_origin=native|ocr` e confiança por página.
3. Dataset de avaliação com recall@k, MRR/nDCG, cobertura de citação, jurisdição e temporalidade.
4. Relações entre norma alteradora e dispositivos alterados.
