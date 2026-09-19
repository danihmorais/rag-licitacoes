# RAG de Licitações

RAG especializado em **licitações, contratos administrativos e Direito Público brasileiro**, com atenção especial ao **Estado de São Paulo**.

O projeto separa as evidências em três grupos:

- **normas**: Constituição, leis, decretos e atos normativos;
- **jurisprudência e controle**: registros estruturados de tribunais;
- **doutrina/conteúdo secundário**: matérias públicas de sites jurídicos selecionados.

A recuperação combina busca semântica e lexical, reranking, filtros jurídicos e expansão estrutural do contexto antes de chamar o LLM.

> Jurisprudência, doutrina, pareceres e orientações não são tratados como texto legal. A resposta deve permanecer vinculada às evidências recuperadas e aos metadados de jurisdição, autoridade e temporalidade.

## Arquitetura

~~~text
Fontes HTML / PDF / APIs / web
            │
            ▼
Sincronização e coleta
retry + validação + hash
            │
            ▼
Cache local estruturado
texto + metadados + versões
            │
            ├──────────────► jurisprudência estruturada
            │
            ▼
Chunking jurídico estrutural
artigo / súmula / blocos
            │
        ┌───┴───┐
        ▼       ▼
     Dense    BM25
        └───┬───┘
            ▼
           RRF
            │
            ▼
         Reranker
relevância + autoridade + jurisdição
            │
            ▼
Expansão de vizinhança estrutural
            │
            ▼
     Evidências + [F#]
            │
            ▼
           LLM
~~~

O índice é local e usa **Qdrant**. Embeddings, recuperação sparse e reranking usam o stack **FastEmbed**. Por padrão, o projeto exige `CUDAExecutionProvider`; execução em CPU é suportada de forma explícita por configuração, sem alterar o código.

O LLM é desacoplado do índice. Trocar somente o gerador não exige reindexação.

## O que o projeto faz

### Recuperação híbrida

A consulta combina:

1. embedding denso com **intfloat/multilingual-e5-large**, usando `query:` para perguntas e `passage:` para documentos;
2. BM25 com **Qdrant/bm25**;
3. fusão **RRF**;
4. reranking com **BAAI/bge-reranker-base**;
5. ponderação explícita de relevância, autoridade e jurisdição;
6. expansão de chunks vizinhos da mesma unidade jurídica.

Padrões atuais:

~~~text
RAG_CANDIDATES_K=60
RAG_FINAL_K=6
RAG_CHUNK_SIZE=1000
RAG_CHUNK_OVERLAP=150
RAG_CONTEXT_NEIGHBORS=1
RAG_MAX_CONTEXT_CHARS=16000

RAG_RERANK_RELEVANCE_WEIGHT=0.68
RAG_RERANK_AUTHORITY_WEIGHT=0.20
RAG_RERANK_JURISDICTION_WEIGHT=0.12
~~~

### Integridade da evidência

Cada fragmento pode carregar, entre outros:

~~~text
source_id
unit_id
unit_ref
chunk_index
document_hash
página
jurisdição
esfera
órgão
papel da fonte
nível de autoridade
status
vigência
text_origin
extraction_confidence
page_extraction
~~~

O sistema também:

- rejeita filtros desconhecidos;
- mantém versões por hash;
- invalida o cache por documento quando `metadata.py`, o sidecar ou a configuração de extração/OCR muda;
- evita remover a versão anterior antes de a nova ser indexada com sucesso;
- valida a compatibilidade do índice por manifesto;
- pode bloquear o LLM quando a evidência não atinge o mínimo configurado;
- exige citações [F#] para afirmações jurídicas relevantes;
- trata o conteúdo recuperado como **dados**, não como instruções para o modelo.

## Corpus jurídico

O catálogo principal fica em **scripts/sources.py**.

Cada fonte possui metadados de jurisdição, esfera, órgão, tipo documental, papel, autoridade, status, vigência e ramo do Direito.

A escala de autoridade é:

| Nível | Papel |
|---|---|
| 1 | Norma |
| 2 | Jurisprudência / controle |
| 3 | Orientação oficial |
| 4 | Doutrina / conteúdo secundário |

Dentro das normas, **normative_rank** diferencia Constituição, lei, decreto e atos infralegais.

### Cobertura federal

O corpus federal inclui, entre outros:

- Constituição Federal;
- Lei nº 14.133/2021;
- LINDB e processo administrativo;
- improbidade e responsabilização;
- licitações, contratos, contratação direta e registro de preços;
- pesquisa de preços, ETP e Termo de Referência;
- concessões e PPP;
- Direito Financeiro e responsabilidade fiscal;
- assinaturas eletrônicas;
- anticorrupção e integridade;
- contratação de serviços sob execução indireta, pesquisa de preços, ETP, Termo de Referência e técnica e preço;
- atualização anual dos valores da Lei nº 14.133/2021;
- transparência, LAI e LGPD;
- governo digital;
- servidores públicos;
- controle e responsabilização;
- urbanismo e patrimônio;
- meio ambiente;
- saúde, educação e assistência social;
- ciência, tecnologia e inovação.

Leis e regimes históricos de contratação, como as Leis nº 8.666/1993, 10.520/2002 e o RDC, permanecem disponíveis com metadados próprios para não serem apresentados automaticamente como regime vigente.

### Estado de São Paulo

O catálogo estadual inclui, entre outros:

- Constituição do Estado;
- Lei nº 10.177/1998;
- regulamentação paulista da Lei nº 14.133/2021;
- PCA, pesquisa de preços e ETP;
- catálogo e Termo de Referência;
- agentes, gestores e fiscais;
- contratação direta;
- leilão eletrônico;
- AUDESP;
- integridade e responsabilização;
- Compras SP;
- Marketplace.SP;
- orientações e pareceres da PGE-SP;
- CADIN Estadual e sua regulamentação.

## Jurisprudência e controle

A jurisprudência possui pipeline próprio em **jurisprudencia/**.

Além dos resultados temáticos, o batch coleta separadamente as **Súmulas do TCU e do TCESP**, cada enunciado como registro estruturado individual a partir dos catálogos oficiais consolidados (o catálogo do TCU atualmente informa 295 registros), com normalização das variações de cabeçalho dos enunciados. O catálogo do TCU usa Chromium como fallback quando a aplicação renderizada não entrega o enunciado no HTML inicial. Súmulas não são contabilizadas no alvo de acórdãos por tribunal.

O conjunto padrão utiliza:

| Tribunal | Coleta | Registro estruturado | Inteiro teor |
|---|---:|---:|---:|
| TCU | Sim | Sim | Opcional |
| TCESP | Sim | Sim | Opcional |
| STJ | Sim | Sim | Opcional |
| STF | Sim | Sim | Opcional |
| TJSP | Sim | Sim | Opcional |

Os resultados são convertidos em registros individuais com informações como processo, tribunal, órgão julgador, relator, data, ementa, tese/decisão, assunto, URL oficial, situação e hash de versão.

Páginas genéricas de pesquisa não são usadas como evidência jurídica. Quando a fonte oferece o documento integral, ele pode ser recuperado com **--with-content**.

### Coleta temática

As consultas padrão abrangem temas como:

- Lei nº 14.133/2021;
- contratação direta;
- edital e habilitação;
- ETP e Termo de Referência;
- registro de preços;
- sanções;
- equilíbrio econômico-financeiro;
- fiscalização contratual;
- ato e processo administrativo;
- controle de constitucionalidade;
- servidores públicos;
- improbidade;
- responsabilidade do Estado;
- transparência e LGPD;
- concessões e PPP;
- temas específicos do Estado de São Paulo.

O limite é um **alvo total por tribunal**. As consultas são percorridas em lotes de até 25 resultados por tribunal e duplicidades são eliminadas por **document_key**.

Configuração padrão:

~~~text
RAG_JURISPRUDENCIA_LIMIT=200
RAG_JURISPRUDENCIA_MIN_RECORDS_PER_TRIBUNAL=150
RAG_JURISPRUDENCIA_STRICT=1
~~~

Consulta única:

~~~bash
python -m jurisprudencia.collector --query "licitação contrato administrativo" --limit 50
~~~

Coleta temática completa:

~~~bash
python -m jurisprudencia.batch --strict --limit 200 --min-records-per-tribunal 150
~~~

Com **--detail** e **--with-content**, o coletor tenta obter informações adicionais e o inteiro teor quando disponibilizados pelo tribunal.

## Matérias jurídicas e de licitação

O sincronizador também coleta conteúdo público secundário de seis fontes:

### Fontes dedicadas a licitações

- **Nova Lei de Licitação**
- **Licitações Públicas**
- **ConLicitação**
- **Zênite**

### Direito Administrativo e Direito Público

- **Migalhas**
- **ConJur**

As quatro primeiras são consideradas fontes dedicadas a licitações e contratos.

Migalhas e ConJur passam por filtro temático para restringir o corpus a Direito Administrativo e Direito Público, além dos assuntos diretamente relacionados a licitações e contratos.

Política atual:

~~~text
publicações a partir de 01/01/2021

Nova Lei de Licitação: até 250 matérias
Licitações Públicas: até 250 matérias
ConLicitação: até 250 matérias
Zênite: até 250 matérias
Migalhas: até 300 matérias
ConJur: até 300 matérias
~~~

A coleta registra título, data, autor, seção, palavras-chave, URL e texto substantivo.

Páginas de arquivo, categorias, paginação, navegação e assets estáticos não entram como matérias.

**PDFs públicos podem ser candidatos válidos.** Quando um link web aponta para PDF, o sistema pode baixar o arquivo, extrair texto e metadados e armazená-lo como documento de origem web. Imagens, JavaScript, CSS e outros recursos estáticos continuam fora do corpus.

As matérias web recebem:

~~~text
source_role=doutrina
authority_level=4
is_official=false
status=orientativo
~~~

O projeto utiliza apenas conteúdo publicamente acessível e não tenta contornar login, paywall ou controles de acesso.

Para validar somente as fontes web:

~~~bash
python scripts/sync_sources.py --web-only --strict
~~~

## Sincronização

A sincronização baixa, descobre, valida e versiona o conteúdo jurídico.

~~~bash
python scripts/sync_sources.py
~~~

Modo estrito:

~~~bash
python scripts/sync_sources.py --strict
~~~

Verificação apenas das fontes obrigatórias:

~~~bash
python scripts/sync_sources.py --check --required-only
~~~

O sincronizador usa retry/backoff, validação de conteúdo e gravação atômica.

O cache de fontes fica em:

~~~text
db/source_cache/
~~~

O catálogo versionado continua sendo **scripts/sources.py**; o cache é somente dado de execução.

## PDFs locais

PDFs fornecidos manualmente podem ser colocados em:

~~~text
pdfs/
~~~

Quando versionados no repositório, a identificação de versão utiliza o sufixo:

~~~text
.DDMMAAAA.pdf
~~~

Exemplo:

~~~text
.27082026.pdf
~~~

## Indexação

Depois da sincronização:

~~~bash
python ingest.py
~~~

O pipeline de ingestão:

1. sincroniza fontes configuradas;
2. coleta jurisprudência quando habilitada;
3. lê textos e PDFs;
4. extrai e normaliza metadados;
5. cria chunks estruturais;
6. gera embeddings dense e sparse;
7. indexa no Qdrant;
8. atualiza o manifesto e o cache de ingestão;
9. remove fontes obsoletas quando **RAG_PRUNE_STALE=1**.

O índice local fica em:

~~~text
db/qdrant/
~~~

Não é necessário executar um servidor Qdrant separado no uso local padrão.

## Consulta

Consulta interativa:

~~~bash
python query.py
~~~

Consulta direta:

~~~bash
python query.py --query "Quais são os requisitos do ETP?"
~~~

### Contexto jurídico-base obrigatório

Toda consulta recupera, além das evidências relevantes para a pergunta, pelo menos um trecho da **Lei nº 14.133/2021** e um trecho do **Manual de Licitações e Contratos do TCU**. Essas fontes são âncoras de contexto e não devem ser tratadas automaticamente como aplicáveis à pergunta. A Lei é fonte normativa; o Manual é orientação oficial do TCU e mantém nível de autoridade distinto.

Caso uma dessas duas fontes ainda não esteja indexada, a consulta falha explicitamente e orienta sincronizar as fontes e executar o ingest. Isso evita uma resposta que aparente ter sido fundamentada com uma fonte obrigatória que não está realmente presente no contexto.

Saída JSON:

~~~bash
python query.py --query "@jurisdicao=estadual_sp @ano=2026 regra do ETP" --json
~~~

### Filtros

São aceitos filtros como:

~~~text
@jurisdicao=estadual_sp
@esfera=federal
@orgao=TCESP
@tribunal=tjsp
@tipo_documento=decreto
@source_role=norma
@authority_level=1
@status=vigente
@revogado=false
@ano=2026
@norm_ano=2026
@municipio=...
@modalidade=...
@tipo=...
@source_id=...
@regime_juridico=lei_14133
~~~

Filtros numéricos também aceitam intervalos:

~~~text
@ano>=2025
@ano<=2026
@authority_level<3
~~~

Consultas que mencionam regimes históricos, como Lei nº 8.666/1993 ou Lei nº 10.520/2002, recebem tratamento específico para evitar mistura silenciosa entre regimes jurídicos.

## Integração prevista com o LICITA.AI

A integração futura deve ocorrer **no backend**, e não diretamente do navegador para o Qdrant ou para o servidor do LLM.

Fluxo previsto:

~~~text
LICITA.AI (frontend)
        │
        ▼
Backend do LICITA.AI
        │
        ├──► RAG: recuperação de evidências
        │       ├── filtros jurídicos
        │       ├── Lei 14.133/2021 + Manual TCU
        │       ├── jurisprudência
        │       └── contexto + fontes [F#]
        │
        ▼
Prompt específico de DFD / ETP / TR
        │
        ▼
Servidor LLM OpenAI-compatible
        │
        ▼
Documento gerado
~~~

O contrato recomendado para o RAG é de **retrieval-first**: o serviço deve conseguir devolver o pacote de evidências sem chamar o LLM. Isso permite ao LICITA.AI reutilizar o mesmo contexto em DFD, ETP e TR, mantendo um único ponto de recuperação e evitando chamadas duplicadas ao modelo.

Contrato HTTP previsto:

~~~text
POST /v1/retrieve

{
  "query": "...",
  "filters": {
    "jurisdicao": "estadual_sp"
  },
  "max_context_chars": 16000
}

→

{
  "query": "...",
  "context": "...",
  "sources": [
    {
      "citation": "[F1]",
      "source": "...",
      "title": "...",
      "page": 1,
      "authority_level": 1,
      "mandatory_context": true
    }
  ]
}
~~~

O endpoint de geração de resposta pode permanecer separado. O LICITA.AI deve enviar ao RAG apenas os dados necessários à recuperação e receber evidências estruturadas; o navegador nunca deve receber credenciais do Qdrant ou do servidor LLM.

O código atual mantém a separação lógica entre recuperação e geração em `query.py`, permitindo transformar essa camada em serviço HTTP sem acoplar o índice ao pipeline de documentos do LICITA.AI. O RAG também não deve assumir que o backend se chama Unsloth: o contrato externo continua sendo OpenAI-compatible, permitindo trocar o servidor local sem modificar a camada de recuperação.

## Qualidade de extração e OCR

PDFs são primeiro processados por extração nativa. Páginas com pouco texto ou baixa confiança heurística podem ser reprocessadas por OCR. Cada página recebe `text_origin` (`native` ou `ocr`) e `extraction_confidence`; chunks que atravessam mais de uma página registram ainda `page_extraction` e podem ser classificados como `mixed`.

A confiança do reranking incorpora essa qualidade de extração: uma evidência OCR de baixa confiança não recebe o mesmo peso de relevância de um trecho nativo de alta confiança. O valor é exposto também no contexto e na saída JSON.

Configuração:

~~~text
RAG_OCR_ENABLED=1
RAG_OCR_REQUIRED=0
RAG_OCR_MIN_NATIVE_CHARS_PER_PAGE=80
RAG_OCR_MIN_NATIVE_CONFIDENCE=0.60
RAG_OCR_DPI=250
RAG_OCR_LANGUAGE=por+eng
~~~

`RAG_OCR_REQUIRED=1` transforma uma falha do OCR necessário em erro de ingestão, em vez de preservar silenciosamente a extração nativa degradada. Para uso local, o Tesseract deve estar instalado com o pacote de idioma correspondente, além das dependências Python do projeto.

## Avaliação da recuperação

O repositório agora inclui um harness de avaliação em `evaluation.py` e um conjunto versionado de perguntas em `evaluation/dataset.json`. O dataset registra, para cada caso, as fontes esperadas, a jurisdição esperada e, quando pertinente, a data em que a regra deve ser avaliada.

As métricas calculadas são `recall@k`, `nDCG@k`, MRR, acerto de jurisdição e acerto temporal. A avaliação reutiliza o pipeline real de dense + BM25 + RRF + reranker, sem chamar o LLM.

Com um índice já construído:

~~~bash
python evaluation.py
python evaluation.py --k 1 3 5 --strict --min-recall 0.80 --min-ndcg 0.60
~~~

Os limiares do modo `--strict` são fornecidos pelo chamador e não são codificados como uma suposta nota universal do corpus. A finalidade é permitir comparar sistematicamente alterações de embedding, reranker e pesos contra o mesmo conjunto de referência.

## Temporalidade e vigência

O corpus preserva metadados como:

~~~text
status
revogado
effective_from
effective_to
data_publicacao
data_vigencia
retrieved_at
~~~

Isso permite distinguir norma vigente, norma histórica, vacatio legis e versões anteriores do mesmo documento.

O histórico é protegido por hash e a ingestão preserva a versão anterior até que a nova versão seja indexada com sucesso.

## LLM

O gerador é independente da recuperação.

Configuração padrão:

~~~text
RAG_LLM_PROVIDER=openai_compatible
RAG_OPENAI_BASE_URL=http://127.0.0.1:8888/v1
RAG_LLM_MODEL=local
~~~

O adaptador OpenAI-compatible usa **/v1/chat/completions**, permitindo conectar qualquer servidor compatível com essa interface.

O projeto também possui adapters adicionais de provedor. A troca do LLM não altera o índice vetorial.

Configuração inicial:

~~~bash
cp .env.example .env
~~~

Nunca versione chaves de API.

## Runtime de embeddings

O pacote padrão usa `fastembed-gpu` e mantém CUDA como caminho recomendado. Para manter esse comportamento previsível, o padrão é:

~~~text
RAG_FASTEMBED_PROVIDERS=CUDAExecutionProvider
RAG_FASTEMBED_REQUIRE_CUDA=1
~~~

O runtime verifica a presença de `CUDAExecutionProvider` quando `RAG_FASTEMBED_REQUIRE_CUDA=1`.

Execução somente em CPU é suportada para CI, notebooks e máquinas sem GPU:

~~~text
RAG_FASTEMBED_REQUIRE_CUDA=0
RAG_FASTEMBED_PROVIDERS=CPUExecutionProvider
~~~

Não use `CPUExecutionProvider` com `RAG_FASTEMBED_REQUIRE_CUDA=1`: nesse modo a configuração é rejeitada de propósito.

## Instalação

O CI utiliza **Python 3.12**.

~~~bash
git clone https://github.com/danihmorais/rag-licitacoes.git
cd rag-licitacoes

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

python -m playwright install chromium

# Linux: requerido para OCR de PDFs escaneados
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-por

cp .env.example .env
~~~

Execução inicial:

~~~bash
python scripts/sync_sources.py --strict
python ingest.py
python query.py
~~~

Os coletores que dependem de automação de navegador precisam do Chromium instalado pelo Playwright.

## Configuração

As variáveis disponíveis estão em **.env.example**.

### Modelos

~~~text
RAG_DENSE_MODEL=intfloat/multilingual-e5-large
RAG_DENSE_DIM=1024
RAG_SPARSE_MODEL=Qdrant/bm25
RAG_RERANK_MODEL=BAAI/bge-reranker-base
RAG_RERANK_SCORE_MODE=sigmoid
~~~

### Recuperação

~~~text
RAG_CANDIDATES_K=60
RAG_FINAL_K=6
RAG_CONTEXT_NEIGHBORS=1
RAG_MAX_CONTEXT_CHARS=16000
RAG_MIN_EVIDENCE_SCORE=0.20
RAG_EVIDENCE_TOKEN_OVERLAP=0.25
~~~

### Jurisprudência

~~~text
RAG_SYNC_JURISPRUDENCIA=1
RAG_JURISPRUDENCIA_QUERY=
RAG_JURISPRUDENCIA_QUERIES=...
RAG_JURISPRUDENCIA_LIMIT=200
RAG_JURISPRUDENCIA_MIN_RECORDS_PER_TRIBUNAL=150
RAG_JURISPRUDENCIA_DETAIL=0
RAG_JURISPRUDENCIA_WITH_CONTENT=0
RAG_JURISPRUDENCIA_STRICT=1
~~~

### Indexação e Qdrant

O embedding denso usa limite explícito de **512 tokens**. Antes de gerar o vetor, o pipeline conta os tokens sem truncagem e interrompe a indexação ou consulta quando o limite é excedido. Isso evita que um texto seja cortado silenciosamente pelo tokenizer.

A coleção usa distância **Cosine** para o vetor denso. O Qdrant normaliza automaticamente vetores em coleções Cosine, portanto não há uma normalização manual redundante no código.

Os campos utilizados pelos filtros do retrieval recebem índices de payload tipados (`keyword`, `integer` ou `bool`) na criação da coleção. O carregamento de pontos também é particionado em lotes pequenos para evitar upserts excessivamente grandes.

Configuração padrão:

~~~text
RAG_DENSE_MAX_TOKENS=512
RAG_QDRANT_UPSERT_BATCH_SIZE=100
RAG_INDEX_VERSION=14
~~~

### Sincronização

~~~text
RAG_SYNC_SOURCES=1
RAG_PRUNE_STALE=1
~~~

### OCR

~~~text
RAG_OCR_ENABLED=1
RAG_OCR_REQUIRED=0
RAG_OCR_MIN_NATIVE_CHARS_PER_PAGE=80
RAG_OCR_MIN_NATIVE_CONFIDENCE=0.60
RAG_OCR_DPI=250
RAG_OCR_LANGUAGE=por+eng
~~~

### Reranking

~~~text
RAG_RERANK_SCORE_MODE=sigmoid
RAG_RERANK_RELEVANCE_WEIGHT=0.68
RAG_RERANK_AUTHORITY_WEIGHT=0.20
RAG_RERANK_JURISDICTION_WEIGHT=0.12
~~~

## Estrutura

~~~text
.
├── config.py
├── ingest.py
├── query.py
├── metadata.py
├── chunking.py
├── index_manifest.py
├── evaluation.py
│
├── jurisprudencia/
│   ├── batch.py
│   ├── collector.py
│   ├── queries.py
│   └── schema.py
│
├── llm/
│   ├── base.py
│   ├── factory.py
│   ├── gemini.py
│   ├── ollama.py
│   └── openai_compatible.py
│
├── scripts/
│   ├── sources.py
│   ├── sync_sources.py
│   └── web_sources.py
│
├── tests/
├── evaluation/
│   └── dataset.json
├── pdfs/
└── db/
    ├── qdrant/
    ├── source_cache/
    ├── ingest_cache.json
    └── index_manifest.json
~~~

Os diretórios de cache e o índice local são dados de execução e não substituem o código ou o catálogo versionado.

## Integridade do índice

O manifesto registra parâmetros necessários para verificar compatibilidade do índice.

Alterações em itens como modelo de embedding, dimensão, chunking ou reranker podem exigir reindexação.

O cache de ingestão registra hash do documento, fingerprint de metadados/OCR e quantidade de chunks por documento. Assim, alterar a lógica de extração de metadados força a reindexação dos documentos afetados mesmo quando o PDF não mudou.

Quando **RAG_PRUNE_STALE=1**, documentos que deixaram de pertencer ao corpus atual são removidos depois da atualização bem-sucedida.

## Testes e GitHub Actions

Verificações locais:

~~~bash
python -m compileall -q .
python -m pytest -q
python scripts/sync_sources.py --check --required-only
~~~

Avaliação de recuperação, com índice já indexado:

~~~bash
python evaluation.py --k 1 3 5
~~~

Os workflows são separados por responsabilidade:

- **ci.yml**: testes determinísticos, verificação de sintaxe e presença do runtime OCR;
- **sync-sources.yml**: health-check das fontes jurídicas;
- **jurisprudencia-health.yml**: health-check dos coletores de jurisprudência e dos catálogos oficiais de súmulas;
- **legal-ingestion.yml**: execução do pipeline de ingestão.

O CI cobre regressões de chunking, filtros, autoridade e jurisdição, catálogo de fontes, temporalidade, cache, versionamento, sincronização, adaptadores de jurisprudência, recuperação e integração OpenAI-compatible.

A suíte principal não depende de sites externos para passar. O harness de avaliação é separado dos testes unitários: ele usa o índice local e dados de referência para medir a qualidade de recuperação antes/depois de alterações no pipeline.

## Limitações

Falhas de rede, CAPTCHA, WAF, mudanças estruturais dos portais ou retirada de documentos não significam ausência de jurisprudência ou legislação. O sistema deve registrar a falha de coleta explicitamente.

Da mesma forma, ausência de resultado na recuperação não deve ser interpretada como inexistência da norma, decisão ou entendimento procurado.

Conteúdo web, pareceres, manuais e decisões judiciais também não substituem a conferência da fonte primária aplicável.

Para uso jurídico real, a resposta deve ser conferida na fonte oficial correspondente, especialmente quando vigência, redação consolidada ou jurisprudência recente forem determinantes.

## Finalidade

Este repositório é um projeto técnico de recuperação e indexação de informação jurídica.

O uso de cada fonte deve respeitar seus termos, direitos autorais e eventuais restrições de acesso. O projeto prioriza fontes oficiais e conteúdo público.

**Repositório:** https://github.com/danihmorais/rag-licitacoes
