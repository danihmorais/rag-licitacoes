# Expansão do corpus jurídico — 11/09/2026

## Objetivo

Ampliar o RAG para além da legislação básica e de uma única consulta jurisprudencial por tribunal, priorizando fontes oficiais e separando norma, jurisprudência, controle e orientação.

## Novas camadas

### Legislação e regulamentação

Foram acrescentados atos federais diretamente relacionados à Lei nº 14.133/2021 e à execução contratual, incluindo os Decretos nº 11.430/2023, 11.461/2023 e 11.531/2023, a Portaria SEGES/ME nº 8.678/2021, a disciplina do regime de transição e as INs SEGES/MGI nº 147/2026, 148/2026, 176/2024, 190/2024, 381/2025 e 382/2025.

A camada também incorpora a legislação de transferências voluntárias pelo Transferegov, inclusive a Portaria Conjunta MGI/MF/CGU nº 33/2023 e sua atualização de 2025.

O catálogo continua preservando a temporalidade: atos revogados ou históricos permanecem identificados separadamente para consultas retrospectivas.

### AGU

A sincronização passa a contemplar Orientações Normativas, Pareceres Referenciais e conjuntos de modelos da Lei nº 14.133/2021, com áreas específicas para contratação direta, pregão/concorrência e TIC. Esses materiais são classificados como orientação oficial e não como texto legal.

### Jurisprudência e precedentes

Além da pesquisa já existente de TCU, TCESP, STJ e STF, o catálogo passa a apontar para bases temáticas e de precedentes qualificados:

- TCU: pesquisa jurisprudencial;
- STJ: Jurisprudência em Teses, Recursos Repetitivos/IACs, Súmulas Anotadas, Legislação Aplicada e Informativos;
- STF: Repercussão Geral, Teses de Repercussão Geral e Tesauro;
- TJSP: portal de jurisprudência e consulta SAJ.

## Coleta temática

A coleta automática deixa de depender apenas de `licitação`. Foi criado um pacote de consultas cobrindo, entre outros temas, contratação direta, habilitação/qualificação técnica, ETP/TR, pesquisa de preços, SRP/adesão, sanções, reequilíbrio/reajuste/repactuação e fiscalização/execução contratual.

O pacote pode ser substituído integralmente por `RAG_JURISPRUDENCIA_QUERIES`, usando `|` como separador. `RAG_JURISPRUDENCIA_QUERY` continua disponível para forçar uma única consulta.

## Extração e indexação

Registros jurisprudenciais mantêm tribunal, processo, decisão, relator, datas, ementa, tese, decisão, partes, situação, URL oficial e hash de versão.

O chunking passa a reconhecer uma decisão jurisprudencial pela presença do cabeçalho `TRIBUNAL` + `PROCESSO` antes de aplicar a segmentação normativa. Isso impede que citações internas como `art. 62` transformem uma decisão em falsas unidades legislativas.

Também foram adicionados reconhecimentos de `Súmula Vinculante` e `Tema` como unidades jurídicas.

## Reindexação

A alteração do chunking muda a estrutura lógica do índice, portanto o `INDEX_VERSION` foi elevado de 9 para 10. O índice existente deve ser reindexado antes de usar o novo corpus.

```bash
python scripts/sync_sources.py
python -m jurisprudencia.batch --limit 12
python ingest.py
```

Para coletar somente um tribunal ou testar uma única consulta:

```bash
python -m jurisprudencia.batch --tribunais tcu --query "reequilíbrio econômico-financeiro" --limit 25
python -m jurisprudencia.collector --tribunais stj --query "contratação direta" --limit 25 --detail
```

## Fontes oficiais relevantes

A expansão foi baseada em fontes oficiais do TCU, STJ, STF, TJSP, AGU, Compras.gov.br, Transferegov e legislação federal/estadual já catalogada no projeto.
