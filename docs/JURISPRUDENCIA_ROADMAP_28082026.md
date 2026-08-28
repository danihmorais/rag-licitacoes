# Coletor de jurisprudência — 28/08/2026

O coletor estruturado complementa legislação e doutrina sem transformar jurisprudência em norma.

## Objetivo

Normalizar decisões oficiais em `JurisprudenciaRecord`, preservando tribunal, processo, órgão julgador, relator, datas, ementa, tese/decisão, assunto, inteiro teor quando disponível, número de decisão/acórdão, partes, situação, URL oficial, data de coleta e hash da versão.

A camada de geração continua independente. O mesmo corpus pode ser usado por Qwen, Gemma, Llama, Gemini, llama.cpp, LM Studio, vLLM, Ollama ou outro endpoint compatível.

## Fontes e adaptadores

### TCU

Preferido como fonte estruturada. O coletor usa a interface oficial de dados abertos de acórdãos e normaliza número do acórdão, colegiado, data de sessão, relator, situação, sumário, classificação e URLs oficiais. `--with-content` tenta baixar o PDF de inteiro teor quando o registro fornece URL.

### TCESP

Usa a pesquisa oficial de jurisprudência e preserva processo, documento, autuação, partes, matéria, objeto e trechos encontrados. O resultado é marcado como `source_role=jurisprudencia_controle`.

### STJ

Usa o SCON oficial e captura links dos acórdãos encontrados. Com `--detail`, tenta abrir o documento para extrair relator, data e ementa.

### STF

Parte do portal oficial de jurisprudência, localiza dinamicamente o formulário público de pesquisa e tenta preservar os links de resultados sem depender de um identificador fixo de HTML.

## Persistência e versionamento

Os registros são gravados em `db/source_cache/jurisprudencia/` como `.txt` + `.json`. O diretório é ignorado pelo Git. A versão é identificada por hash do conteúdo normalizado; alterações posteriores não substituem silenciosamente a versão anterior.

## Comandos

```bash
python -m jurisprudencia.collector --query "licitação" --limit 25
python -m jurisprudencia.collector --tribunais tcu,tcesp,stj,stf --query "contrato administrativo" --limit 50 --detail
python -m jurisprudencia.collector --tribunais tcu --query "pregão" --limit 100 --detail --with-content
```

A coleta automática do `ingest.py` pode ser controlada por `RAG_SYNC_JURISPRUDENCIA`, `RAG_JURISPRUDENCIA_QUERY` e `RAG_JURISPRUDENCIA_LIMIT`.

## Recuperação

A jurisprudência usa o mesmo pipeline híbrido: BM25 + dense -> RRF -> reranker -> contexto -> LLM. O payload mantém tribunal, processo, decisão, `source_role`, autoridade, status, URL oficial e hash. A resposta deve identificar quando a conclusão decorre de precedente, súmula ou órgão de controle e nunca apresentá-lo como texto legal.

## Fontes oficiais

- TCU — dados abertos de jurisprudência: https://sites.tcu.gov.br/dados-abertos/jurisprudencia/
- TCU — webservices: https://sites.tcu.gov.br/dados-abertos/webservices/
- STJ — pesquisa de jurisprudência: https://scon.stj.jus.br/SCON/
- STF — pesquisa de jurisprudência: https://portal.stf.jus.br/jurisprudencia/
- TCESP — pesquisa de jurisprudência: https://www.tce.sp.gov.br/jurisprudencia/pesquisar
- TCESP — súmulas: https://www.tce.sp.gov.br/boletim-de-jurisprudencia/sumulas
