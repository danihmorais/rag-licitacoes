# Roadmap de jurisprudência — 28/08/2026

A próxima etapa recomendada é separar jurisprudência de legislação e de orientação administrativa. O registro canônico deverá preservar, no mínimo:

- tribunal;
- número do processo;
- órgão julgador/colegiado;
- relator;
- data do julgamento/publicação, com distinção quando a fonte fornecer ambas;
- ementa;
- assunto/classificação;
- tese ou entendimento extraído, quando houver;
- inteiro teor, preferencialmente como texto preservado e também com URL oficial;
- número da decisão/acórdão, quando houver;
- data de coleta e hash do documento bruto.

## Ordem de implementação

### 1. TCU

É a melhor primeira fonte para automação estruturada porque o TCU disponibiliza dados abertos de jurisprudência. O coletor deve preferir o conjunto oficial estruturado em vez de scraping de páginas de resultado.

### 2. TCESP

Priorizar súmulas, boletins e decisões/acórdãos ligados a licitações e contratos. O modelo deve preservar órgão julgador, processo e data, sem converter entendimento do TCESP em norma legal.

### 3. STJ

Usar a pesquisa oficial e o inteiro teor disponibilizado pelo tribunal. O adaptador deve manter separados `ementa`, `decisao` e `inteiro_teor`, porque pesquisa de jurisprudência e consulta processual expõem informações em camadas diferentes.

### 4. STF

Usar a base oficial de pesquisa e inteiro teor. O campo `assunto` deve usar, quando disponível, vocabulário controlado do próprio tribunal para melhorar a recuperação semântica.

## Regra de indexação

Jurisprudência deve entrar em coleção ou payload logicamente separável da legislação, mantendo `source_role=jurisprudencia` ou `jurisprudencia_controle`. A recuperação pode continuar híbrida (dense + BM25 + RRF + reranker), mas a resposta deve informar explicitamente quando a conclusão decorre de precedente, súmula ou órgão de controle.

O esquema inicial está em `jurisprudencia/schema.py` e não depende de nenhum LLM. Isso permite alimentar o mesmo corpus com Qwen, Gemma, Llama ou qualquer outro gerador local sem reindexar por causa do modelo gerador.

## Inteiro teor e temporalidade

Não sobrescrever silenciosamente uma decisão já coletada. O identificador lógico deve combinar tribunal, processo, decisão e versão/hash do documento. Alterações posteriores na página devem gerar uma nova versão do registro.

## Fontes oficiais

- TCU — dados abertos de jurisprudência: https://sites.tcu.gov.br/dados-abertos/jurisprudencia/
- STJ — pesquisa de jurisprudência: https://scon.stj.jus.br/SCON/
- STF — pesquisa de jurisprudência: https://portal.stf.jus.br/jurisprudencia/
- TCESP — súmulas e boletim: https://www.tce.sp.gov.br/boletim-de-jurisprudencia/sumulas
