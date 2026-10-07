# RAG de Licitações

RAG especializado em **licitações, contratos administrativos e Direito Público brasileiro**, com foco em recuperação de evidências jurídicas e cobertura relevante do Estado de São Paulo.

O projeto:

- coleta e versiona fontes jurídicas;
- transforma documentos em chunks jurídicos estruturados;
- indexa e recupera evidências com busca híbrida;
- aplica filtros de jurisdição, autoridade e temporalidade;
- opcionalmente usa um LLM para gerar a resposta final.

> **Importante:** este projeto é uma ferramenta técnica de recuperação e apoio à pesquisa. O resultado não substitui a conferência da fonte oficial aplicável.

---

## 1. Visão geral

O fluxo completo é:

~~~text
FONTES
  ├─ legislação oficial
  ├─ jurisprudência / tribunais
  ├─ súmulas TCU e TCESP
  ├─ conteúdo jurídico web
  └─ PDFs locais
        │
        ▼
COLETA / SINCRONIZAÇÃO
        │
        ▼
CACHE + METADADOS + HASHES
        │
        ▼
CHUNKING JURÍDICO ESTRUTURAL
        │
        ├───────────────┐
        ▼               ▼
      DENSE          SPARSE / BM25
        └───────┬───────┘
                ▼
               RRF
                ▼
            RERANKER
                │
                ▼
 FILTROS + AUTORIDADE + JURISDIÇÃO + TEMPO
                │
                ▼
       EXPANSÃO DE CONTEXTO
                │
                ▼
          EVIDÊNCIAS [F#]
                │
                ▼
               LLM
                │
                ▼
             RESPOSTA
~~~

O Qdrant é usado como servidor separado. O LLM é desacoplado do índice: trocar o modelo de geração não exige reindexar o corpus.

---

# 2. Pré-requisitos

## Obrigatórios

| Componente | Função |
|---|---|
| **Python 3.12** | execução do projeto |
| **pip** | instalação das dependências |
| **Qdrant Server** | banco vetorial |
| **requirements.txt** | dependências de ingestão, recuperação e coleta |

## Necessários para funções específicas

| Componente | Quando |
|---|---|
| **Chromium via Playwright** | coleta que usa automação de navegador |
| **Tesseract OCR** | PDFs escaneados ou páginas com extração nativa insuficiente |
| **GPU NVIDIA + driver compatível** | configuração padrão de embeddings/reranking com CUDA |

### Não é obrigatório

**Docker não é requisito do projeto.**

O projeto usa **Qdrant Server**, não o modo de armazenamento local embutido no cliente Python.

---

# 3. Python e uv

O projeto usa **Python 3.12**.

O método recomendado é instalar o **uv** e deixar o próprio uv gerenciar o Python e o ambiente virtual do projeto. Assim, a instalação não depende do Python global já existente na máquina.

O uv pode instalar uma versão de Python automaticamente quando ela ainda não estiver disponível. citeturn952369search0turn952369search2

## Instalar o uv

### Linux / WSL / macOS

~~~bash
curl -LsSf https://astral.sh/uv/install.sh | sh
~~~

Reabra o terminal, se necessário, para que `uv` esteja disponível no PATH.

### Windows / PowerShell

~~~powershell
irm https://astral.sh/uv/install.ps1 | iex
~~~

Feche e abra o PowerShell novamente, se necessário.

Verifique:

~~~bash
uv --version
~~~

Documentação oficial:

https://docs.astral.sh/uv/

---

# 4. Instalação do projeto

## Linux / WSL / macOS

~~~bash
git clone https://github.com/danihmorais/rag-licitacoes.git
cd rag-licitacoes

uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements.txt

uv run python -m playwright install chromium

cp .env.example .env
~~~

O comando `uv venv --python 3.12 .venv` cria o ambiente virtual `.venv` usando Python 3.12. Se essa versão ainda não estiver instalada, o uv pode baixá-la e gerenciá-la automaticamente. citeturn952369search0turn952369search2

**Não é necessário instalar Python 3.12 manualmente nem usar o Python global.**

### Ativar o ambiente — opcional

Você pode trabalhar sem ativar o ambiente e executar os comandos com `uv run`.

Caso prefira ativá-lo:

~~~bash
source .venv/bin/activate
~~~

Depois da ativação, `python` e `pip` apontam para o ambiente do projeto.

### OCR no Linux

Para utilizar OCR em PDFs:

~~~bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-por
~~~

## Windows / PowerShell

~~~powershell
git clone https://github.com/danihmorais/rag-licitacoes.git
cd rag-licitacoes

uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements.txt

uv run python -m playwright install chromium

Copy-Item .env.example .env
~~~

Também no Windows, não é necessário instalar Python 3.12 globalmente: o uv gerencia a versão usada pelo ambiente do projeto. citeturn952369search0

### Ativar o ambiente — opcional

~~~powershell
.venv\Scripts\Activate.ps1
~~~

No Windows, o Tesseract precisa ser instalado separadamente caso OCR seja utilizado.

> **Regra prática:** para não depender de qual Python está instalado na máquina, prefira executar o projeto com `uv run ...`. O uv detecta o ambiente virtual do projeto e executa nele. citeturn952369search1turn952369search3

---

# 5. Qdrant Server

O RAG usa **Qdrant Server**.

Configuração padrão:

~~~text
RAG_QDRANT_URL=http://127.0.0.1:6333
RAG_QDRANT_API_KEY=
RAG_QDRANT_PREFER_GRPC=1
RAG_QDRANT_TIMEOUT=30
~~~

A coleção usada pelo projeto é:

~~~text
licitacoes
~~~

Antes de indexar ou consultar, o servidor deve estar disponível em:

~~~text
http://127.0.0.1:6333
~~~

Documentação oficial:

https://qdrant.tech/documentation/

### Teste rápido

Com o Qdrant em execução:

~~~bash
uv run python -c "from qdrant_client import QdrantClient; c=QdrantClient(url='http://127.0.0.1:6333'); print(c.get_collections())"
~~~

Se essa chamada não conectar, corrija primeiro o Qdrant ou RAG_QDRANT_URL.

---

# 6. Configuração

A configuração completa está no arquivo:

~~~text
.env.example
~~~

Copie para:

~~~text
.env
~~~

Nunca versione chaves reais.

## Configuração principal

~~~text
RAG_INDEX_VERSION=1

RAG_QDRANT_URL=http://127.0.0.1:6333
RAG_QDRANT_API_KEY=
RAG_QDRANT_PREFER_GRPC=1
RAG_QDRANT_TIMEOUT=30

RAG_DENSE_MODEL=intfloat/multilingual-e5-large
RAG_DENSE_DIM=1024
RAG_DENSE_MAX_TOKENS=512

RAG_SPARSE_MODEL=Qdrant/bm25

RAG_RERANK_MODEL=BAAI/bge-reranker-base
RAG_RERANK_SCORE_MODE=sigmoid
RAG_RERANK_RELEVANCE_WEIGHT=0.68
RAG_RERANK_AUTHORITY_WEIGHT=0.20
RAG_RERANK_JURISDICTION_WEIGHT=0.12

RAG_CHUNK_SIZE=1000
RAG_CHUNK_OVERLAP=150

RAG_CANDIDATES_K=60
RAG_FINAL_K=6
RAG_CONTEXT_NEIGHBORS=1
RAG_MAX_CONTEXT_CHARS=16000

RAG_MIN_EVIDENCE_SCORE=0.20
RAG_EVIDENCE_TOKEN_OVERLAP=0.25
RAG_EVIDENCE_STEM_OVERLAP=0.20
RAG_EVIDENCE_MIN_SHARED_STEMS=2
~~~

As demais variáveis estão documentadas no próprio .env.example.

---

# 7. GPU ou CPU

## GPU — padrão

O projeto usa:

~~~text
fastembed-gpu
onnxruntime-gpu
CUDAExecutionProvider
~~~

Configuração padrão:

~~~text
RAG_FASTEMBED_REQUIRE_CUDA=1
RAG_FASTEMBED_PROVIDERS=CUDAExecutionProvider
~~~

As bibliotecas CUDA necessárias também são pinadas no requirements.txt.

## CPU

CPU é suportada explicitamente.

Use:

~~~text
RAG_FASTEMBED_REQUIRE_CUDA=0
RAG_FASTEMBED_PROVIDERS=CPUExecutionProvider
~~~

Nesse modo o projeto não exige CUDA.

---

# 8. Primeira execução

Depois de instalar as dependências e iniciar o Qdrant:

### 8.1 Verificar sintaxe

~~~bash
uv run python -m compileall -q .
~~~

### 8.2 Rodar testes

~~~bash
uv run python -m pytest -q
~~~

### 8.3 Verificar fontes obrigatórias

~~~bash
uv run python scripts/sync_sources.py --check --required-only
~~~

### 8.4 Construir / atualizar o índice

~~~bash
uv run python ingest.py
~~~

A partir daí o índice está disponível para consulta.

---

# 9. O que o ingest.py faz

O comando principal de ingestão executa, conforme a configuração:

~~~text
1. sincronização das fontes
2. coleta de jurisprudência
3. leitura dos documentos
4. extração de texto / OCR
5. normalização de metadados
6. chunking jurídico
7. embeddings dense
8. representação sparse / BM25
9. upsert no Qdrant
10. atualização do manifesto
11. atualização do cache de ingestão
12. remoção de documentos obsoletos, quando habilitada
~~~

Para indexar sem sincronizar novamente:

~~~bash
uv run python ingest.py --no-sync
~~~

Isso é útil quando o conteúdo já está disponível no cache e você quer reconstruir o índice sem disparar nova coleta.

---

# 10. Fontes e corpus

O catálogo principal de fontes está em:

~~~text
scripts/sources.py
~~~

Fontes complementares:

~~~text
scripts/sources_additional.py
~~~

Cada fonte possui metadados jurídicos que permitem distinguir:

~~~text
jurisdição
esfera
órgão
tipo documental
papel da fonte
nível de autoridade
status
vigência
ramo do Direito
~~~

A política de autoridade é:

| Nível | Tipo |
|---:|---|
| 1 | norma |
| 2 | jurisprudência / controle |
| 3 | orientação oficial |
| 4 | doutrina / conteúdo secundário |

A fonte primária não é tratada da mesma forma que conteúdo secundário.

---

# 11. Conteúdo web

A coleta de conteúdo web está em:

~~~text
scripts/web_sources.py
~~~

As fontes configuradas atualmente são:

| Fonte | Classificação |
|---|---|
| Nova Lei de Licitação | conteúdo secundário especializado |
| Licitações Públicas | conteúdo secundário especializado |
| Zênite | conteúdo secundário especializado |
| Migalhas | Direito Administrativo / Direito Público |
| ConJur | Direito Administrativo / Direito Público |

Esse conteúdo não é tratado como legislação.

Os documentos web recebem metadados equivalentes a:

~~~text
source_role=doutrina
authority_level=4
is_official=false
status=orientativo
~~~

O coletor não tenta contornar:

~~~text
login
paywall
CAPTCHA
controles de acesso
~~~

Páginas de arquivo, navegação, paginação e assets estáticos não entram no corpus como matérias.

PDFs públicos apontados por essas fontes podem ser tratados como documentos de origem web.

### Testar somente a coleta web

~~~bash
uv run python scripts/sync_sources.py --web-only --strict
~~~

### Teste com quantidade reduzida

~~~bash
uv run python scripts/sync_sources.py --web-only --max-web-documents 5
~~~

### Limitar páginas de descoberta

~~~bash
uv run python scripts/sync_sources.py --web-only --max-web-discovery-pages 25
~~~

---

# 12. Sincronização de fontes

O sincronizador é:

~~~text
scripts/sync_sources.py
~~~

### Normal

~~~bash
uv run python scripts/sync_sources.py
~~~

### Estrito

~~~bash
uv run python scripts/sync_sources.py --strict
~~~

### Verificar fontes obrigatórias sem ingestão

~~~bash
uv run python scripts/sync_sources.py --check --required-only
~~~

### Somente legislação

~~~bash
uv run python scripts/sync_sources.py --legislation-only
~~~

### Somente web

~~~bash
uv run python scripts/sync_sources.py --web-only
~~~

### Não seguir links de descoberta

~~~bash
uv run python scripts/sync_sources.py --no-follow-links
~~~

O cache das fontes fica em:

~~~text
db/source_cache/
~~~

Falhas de rede ou de um portal não significam ausência da norma ou do conteúdo jurídico. O modo estrito existe para tornar uma coleta incompleta explícita.

---

# 13. Jurisprudência

O pipeline de jurisprudência fica em:

~~~text
jurisprudencia/
~~~

Tribunais suportados:

~~~text
TCU
TCESP
STJ
STF
TJSP
~~~

Os registros são normalizados para um schema único e podem conter:

~~~text
tribunal
tipo_documento
numero_processo
numero_sumula
orgao_julgador
relator
data
data_publicacao
assunto
ementa
tese
decisao
inteiro_teor
url_oficial
tipo_decisao
numero_decisao
origem
situacao
retrieved_at
sha256
version_sha256
~~~

O identificador estável do registro permite deduplicação e controle de versão.

---

# 14. Coleta simples de jurisprudência

Consulta única:

~~~bash
uv run python -m jurisprudencia.collector --query "licitação contrato administrativo" --limit 50
~~~

Com detalhamento:

~~~bash
uv run python -m jurisprudencia.collector --query "licitação contrato administrativo" --limit 50 --detail
~~~

Tentando obter também o inteiro teor:

~~~bash
uv run python -m jurisprudencia.collector --query "licitação contrato administrativo" --limit 50 --with-content
~~~

Selecionando tribunais:

~~~bash
uv run python -m jurisprudencia.collector --tribunais tcu,tcesp,stj,stf,tjsp --query "licitação" --limit 50
~~~

---

# 15. Coleta temática de jurisprudência

O lote usa consultas definidas em:

~~~text
jurisprudencia/queries.py
~~~

Entre os temas cobertos estão:

~~~text
Lei 14.133/2021
contratação direta
edital e habilitação
ETP e Termo de Referência
registro de preços
sanções
equilíbrio econômico-financeiro
fiscalização contratual
processo administrativo
servidores públicos
improbidade
responsabilidade do Estado
transparência
LGPD
Direito Financeiro
meio ambiente
saúde
educação
São Paulo
~~~

Execução padrão:

~~~bash
uv run python -m jurisprudencia.batch --strict
~~~

Exemplo com limite e mínimo por tribunal:

~~~bash
uv run python -m jurisprudencia.batch --limit 200 --min-records-per-tribunal 150 --strict
~~~

Consultas personalizadas podem ser repetidas com:

~~~bash
uv run python -m jurisprudencia.batch --query "Lei 14.133 licitação contrato" --query "contratação direta dispensa inexigibilidade" --limit 100
~~~

### Súmulas

Por padrão, a coleta em lote inclui as súmulas.

Para coletar explicitamente:

~~~bash
uv run python -m jurisprudencia.batch --with-sumulas
~~~

Para uma execução sem súmulas:

~~~bash
uv run python -m jurisprudencia.batch --without-sumulas
~~~

Para executar a coleta de súmulas diretamente:

~~~bash
uv run python -m jurisprudencia.sumulas --strict
~~~

As súmulas são registros próprios e não entram na contagem de acórdãos por tribunal.

---

# 16. PDFs locais

PDFs locais ficam em:

~~~text
pdfs/
~~~

O pipeline tenta primeiro a extração nativa.

Quando a página apresenta pouco texto ou baixa confiança heurística, o OCR pode ser acionado.

O documento pode carregar informações como:

~~~text
text_origin
extraction_confidence
page_extraction
~~~

Isso permite diferenciar texto nativo de texto obtido por OCR.

---

# 17. OCR

Configuração padrão:

~~~text
RAG_OCR_ENABLED=1
RAG_OCR_REQUIRED=0
RAG_OCR_MIN_NATIVE_CHARS_PER_PAGE=80
RAG_OCR_MIN_NATIVE_CONFIDENCE=0.60
RAG_OCR_DPI=250
RAG_OCR_LANGUAGE=por+eng
~~~

Para exigir que OCR necessário não falhe silenciosamente:

~~~text
RAG_OCR_REQUIRED=1
~~~

No Linux, instale o idioma português do Tesseract:

~~~bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-por
~~~

---

# 18. Chunking jurídico

O chunking é **determinístico e estrutural**. Não depende de um LLM para decidir onde cortar os documentos.

O componente principal é:

~~~text
chunking.py
~~~

A estrutura jurídica preservada inclui, quando reconhecida:

~~~text
norma
capítulos
seções
artigos
parágrafos
incisos
alíneas
itens
anexos
~~~

Cada unidade possui identidade estrutural e posição verificável na fonte.

Metadados importantes:

~~~text
node_id
parent_id
kind
ref
source_start
source_end
source_text
~~~

Antes da indexação, o pipeline valida a relação entre o texto do chunk e a posição correspondente na fonte.

---

# 19. Embeddings e recuperação

## Dense

Modelo padrão:

~~~text
intfloat/multilingual-e5-large
~~~

Dimensão:

~~~text
1024
~~~

Limite:

~~~text
RAG_DENSE_MAX_TOKENS=512
~~~

O pipeline verifica o número de tokens antes de gerar o vetor, evitando truncamento silencioso.

## Sparse / BM25

Modelo:

~~~text
Qdrant/bm25
~~~

## Fusão e reranking

O fluxo é:

~~~text
Dense + BM25
      ↓
     RRF
      ↓
  Reranker
      ↓
ordenação final
~~~

Reranker padrão:

~~~text
BAAI/bge-reranker-base
~~~

Pesos padrão:

~~~text
relevância      0.68
autoridade      0.20
jurisdição      0.12
~~~

Esses três pesos precisam somar 1.

---

# 20. Parâmetros principais de recuperação

~~~text
RAG_CANDIDATES_K=60
RAG_FINAL_K=6
RAG_CONTEXT_NEIGHBORS=1
RAG_MAX_CONTEXT_CHARS=16000
~~~

Em termos práticos:

- CANDIDATES_K = candidatos recuperados antes do estágio final;
- FINAL_K = evidências finais mantidas;
- CONTEXT_NEIGHBORS = chunks vizinhos que podem complementar a evidência;
- MAX_CONTEXT_CHARS = limite do contexto enviado ao estágio de resposta.

---

# 21. Evidência e citações

Cada resultado pode carregar, entre outros:

~~~text
fonte
jurisdição
esfera
órgão
tipo documental
autoridade
status
vigência
origem da extração
qualidade da extração
~~~

As evidências são referenciadas no contexto por identificadores:

~~~text
[F1]
[F2]
[F3]
...
~~~

A camada de evidência possui um gate próprio:

~~~text
RAG_MIN_EVIDENCE_SCORE=0.20
RAG_EVIDENCE_TOKEN_OVERLAP=0.25
RAG_EVIDENCE_STEM_OVERLAP=0.20
RAG_EVIDENCE_MIN_SHARED_STEMS=2
~~~

O objetivo é evitar que um resultado apenas semanticamente parecido seja tratado como fundamento suficiente para uma afirmação jurídica.

---

# 22. Temporalidade e vigência

O corpus preserva campos como:

~~~text
status
revogado
effective_from
effective_to
data_publicacao
data_vigencia
retrieved_at
~~~

Consultas com referência temporal podem transformar essa informação em filtros reais do Qdrant.

Para uma data D, a regra é conceitualmente:

~~~text
effective_from <= D <= effective_to
~~~

Para intervalos, as janelas precisam se sobrepor.

Consultas comparativas com mais de uma data não são reduzidas artificialmente a uma única data.

---

# 23. Regime jurídico

O projeto diferencia:

~~~text
regime jurídico do documento
versus
regimes apenas citados no documento
~~~

Isso evita inferir que uma norma pertence automaticamente ao regime de uma lei que apenas aparece citada em seu texto.

A distinção é particularmente importante quando se consultam regimes como:

~~~text
Lei 14.133/2021
Lei 8.666/1993
Lei 10.520/2002
RDC
~~~

Normas históricas permanecem disponíveis com metadados próprios, sem serem apresentadas automaticamente como regime vigente.

---

# 24. Consulta

Consulta interativa:

~~~bash
uv run python query.py
~~~

Consulta única:

~~~bash
uv run python query.py --query "Quais são os requisitos do estudo técnico preliminar?"
~~~

Saída JSON:

~~~bash
uv run python query.py --query "Quais são os requisitos do ETP?" --json
~~~

O modo JSON exige uma consulta única com --query.

---

# 25. Filtros

Os filtros são embutidos na própria consulta usando @.

Exemplos:

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

Também há comparadores numéricos:

~~~text
@ano>=2025
@ano<=2026
@authority_level<3
~~~

Exemplo:

~~~bash
uv run python query.py --query "@jurisdicao=estadual_sp @ano=2026 regra do ETP"
~~~

Filtros desconhecidos são rejeitados em vez de serem silenciosamente ignorados.

---

# 26. LLM

O LLM gera a resposta final; ele não constrói o índice.

Os provedores implementados são:

~~~text
openai_compatible
ollama
gemini
~~~

O código também aceita openrouter como alias do adaptador OpenAI-compatible por compatibilidade.

## OpenAI-compatible

Configuração padrão:

~~~text
RAG_LLM_PROVIDER=openai_compatible
RAG_LLM_MODEL=local
RAG_OPENAI_BASE_URL=http://127.0.0.1:8888/v1
RAG_OPENAI_API_KEY=
~~~

A chamada é feita para:

~~~text
/v1/chat/completions
~~~

Qualquer servidor compatível com essa interface pode ser usado.

## Ollama

~~~text
RAG_LLM_PROVIDER=ollama
RAG_LLM_MODEL=nome-do-modelo
OLLAMA_HOST=http://127.0.0.1:11434
RAG_OLLAMA_NUM_CTX=16384
~~~

## Gemini

~~~text
RAG_LLM_PROVIDER=gemini
RAG_LLM_MODEL=nome-do-modelo
GEMINI_API_KEY=sua-chave
~~~

---

# 27. O LLM é necessário para tudo?

Não.

| Operação | LLM de geração |
|---|---|
| sincronização | não |
| coleta de jurisprudência | não |
| indexação | não |
| testes | não |
| avaliação da recuperação | não |
| geração da resposta textual | sim |

Isso permite testar o RAG e medir a recuperação sem depender do servidor de geração.

---

# 28. Avaliação

O harness está em:

~~~text
evaluation.py
evaluation/dataset.json
~~~

### Avaliação padrão

~~~bash
uv run python evaluation.py
~~~

### Escolher k

~~~bash
uv run python evaluation.py --k 1 3 5 10
~~~

### Somente evidence gate

~~~bash
uv run python evaluation.py --gate-only
~~~

### Modo estrito

~~~bash
uv run python evaluation.py --k 1 3 5 10 --strict --min-recall 0.80 --min-ndcg 0.60 --min-gate-rejection 0.80
~~~

As métricas de recuperação incluem:

~~~text
recall@k
nDCG@k
MRR
acerto de jurisdição
acerto temporal
~~~

O evidence gate possui métricas próprias, incluindo:

~~~text
accuracy
correct_rejection_rate
false_accept_rate
correct_acceptance_rate
observed_rejection_rate
~~~

A avaliação de recuperação reutiliza o pipeline real de dense + BM25 + RRF + reranker e não chama o LLM.

---

# 29. Cache e manifesto

O estado local fica principalmente em:

~~~text
db/
├── source_cache/
├── ingest_cache.json
├── index_manifest.json
└── ...
~~~

O armazenamento do Qdrant é administrado pelo próprio Qdrant Server e não deve ser confundido com o cache do projeto.

O manifesto registra os parâmetros necessários para verificar a compatibilidade do índice.

A versão atual é:

~~~text
RAG_INDEX_VERSION=1
~~~

Mudanças em itens como modelo de embedding, dimensão, chunking ou reranker podem exigir reindexação.

O cache também acompanha hashes e fingerprints de extração/metadados para detectar documentos que precisam ser processados novamente.

---

# 30. Remoção de documentos obsoletos

Configuração padrão:

~~~text
RAG_PRUNE_STALE=1
~~~

Quando habilitada, fontes que deixaram de fazer parte do corpus atual podem ser removidas do índice após a atualização bem-sucedida.

---

# 31. Testes

Verificação de sintaxe:

~~~bash
uv run python -m compileall -q .
~~~

Suíte principal:

~~~bash
uv run python -m pytest -q
~~~

Verificação das fontes obrigatórias:

~~~bash
uv run python scripts/sync_sources.py --check --required-only
~~~

---

# 32. GitHub Actions

O repositório possui:

| Workflow | Função |
|---|---|
| ci.yml | testes determinísticos, sintaxe, OCR e evidence gate offline |
| sync-sources.yml | health-check das fontes jurídicas |
| jurisprudencia-health.yml | health-check de jurisprudência e súmulas |
| legal-ingestion.yml | smoke test do pipeline de ingestão |

A validação do pipeline de ingestão usa Qdrant Server no CI.

---

# 33. Estrutura do projeto

~~~text
.
├── README.md
├── config.py
├── ingest.py
├── query.py
├── metadata.py
├── chunking.py
├── embedding_utils.py
├── index_manifest.py
├── evaluation.py
│
├── jurisprudencia/
│   ├── batch.py
│   ├── collector.py
│   ├── queries.py
│   ├── schema.py
│   └── sumulas.py
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
│   ├── sources_additional.py
│   ├── sync_sources.py
│   └── web_sources.py
│
├── evaluation/
│   └── dataset.json
│
├── tests/
│   └── ...
│
├── pdfs/
│
└── db/
    └── ...
~~~

---

# 34. Arquivos principais

| Arquivo | Responsabilidade |
|---|---|
| config.py | configuração e validações |
| ingest.py | ingestão e indexação |
| query.py | consulta e geração da resposta |
| chunking.py | parsing e chunking jurídico |
| metadata.py | normalização de metadados |
| embedding_utils.py | utilidades de embeddings |
| index_manifest.py | manifesto e compatibilidade do índice |
| evaluation.py | avaliação |
| scripts/sources.py | catálogo de fontes normativas |
| scripts/web_sources.py | coleta web |
| scripts/sync_sources.py | sincronização |
| jurisprudencia/collector.py | coleta de jurisprudência |
| jurisprudencia/batch.py | coleta temática |
| jurisprudencia/sumulas.py | coleta de súmulas |
| llm/ | adapters de LLM |

---

# 35. Integração com aplicações externas

A separação entre recuperação e geração permite um desenho retrieval-first:

~~~text
aplicação
   │
   ▼
RAG
   │
   ├─ filtros
   ├─ recuperação
   ├─ autoridade
   ├─ jurisdição
   ├─ temporalidade
   └─ evidências [F#]
   │
   ▼
LLM
   │
   ▼
resposta
~~~

Isso permite que uma aplicação externa reutilize o mesmo pacote de evidências em diferentes etapas de geração.

Credenciais do Qdrant e do LLM devem permanecer no backend, nunca no navegador.

---

# 36. Diagnóstico rápido

## Qdrant não conecta

Confirme:

~~~text
RAG_QDRANT_URL
~~~

e verifique se o servidor responde na porta 6333.

## Erro de CUDA

Confirme:

~~~text
RAG_FASTEMBED_REQUIRE_CUDA=1
RAG_FASTEMBED_PROVIDERS=CUDAExecutionProvider
~~~

ou mude explicitamente para CPU:

~~~text
RAG_FASTEMBED_REQUIRE_CUDA=0
RAG_FASTEMBED_PROVIDERS=CPUExecutionProvider
~~~

## OCR não funciona

Confirme:

~~~bash
tesseract --version
~~~

e que o idioma português está instalado.

## Coleta web falha

Pode ser:

~~~text
timeout
erro de rede
mudança no HTML
WAF
CAPTCHA
indisponibilidade temporária
~~~

Uma falha de coleta não deve ser interpretada como inexistência do conteúdo jurídico.

## Jurisprudência não retorna resultados

Verifique:

~~~text
tribunal
consulta
limite
disponibilidade do portal
~~~

Ausência de resultado também não prova inexistência do entendimento.

---

# 37. Comandos essenciais

### Instalação

~~~bash
uv run python -m pip install -r requirements.txt
uv run python -m playwright install chromium
~~~

### Configuração

~~~text
.env.example → .env
~~~

### Verificação

~~~bash
uv run python -m compileall -q .
uv run python -m pytest -q
uv run python scripts/sync_sources.py --check --required-only
~~~

### Indexação

~~~bash
uv run python ingest.py
~~~

### Indexação sem sincronização

~~~bash
uv run python ingest.py --no-sync
~~~

### Consulta

~~~bash
uv run python query.py
~~~

### Consulta única

~~~bash
uv run python query.py --query "pergunta"
~~~

### JSON

~~~bash
uv run python query.py --query "pergunta" --json
~~~

### Web

~~~bash
uv run python scripts/sync_sources.py --web-only --strict
~~~

### Jurisprudência

~~~bash
uv run python -m jurisprudencia.batch --strict
~~~

### Súmulas

~~~bash
uv run python -m jurisprudencia.sumulas --strict
~~~

### Avaliação

~~~bash
uv run python evaluation.py
~~~

---

# 38. Limitações e responsabilidade jurídica

O sistema depende de fontes externas e pode sofrer com:

~~~text
mudanças de sites
indisponibilidade temporária
bloqueios
mudanças de estrutura
documentos removidos
falhas de extração
OCR imperfeito
mudanças legislativas
atualização de jurisprudência
~~~

Portanto:

> **ausência de resultado não significa ausência de norma, decisão ou entendimento.**

E:

> **um resultado recuperado não significa, sozinho, que a regra seja aplicável ao caso concreto.**

Para uso jurídico real, confirme a fonte primária, a redação vigente, a competência e a jurisprudência aplicável.

---

## Uso e fontes

O projeto prioriza fontes oficiais e conteúdo publicamente acessível.

O uso dos dados coletados deve respeitar os termos de uso, direitos autorais e eventuais restrições de cada fonte.

Este repositório é uma ferramenta técnica de recuperação de informação jurídica e não constitui parecer jurídico.

---

**Repositório:** https://github.com/danihmorais/rag-licitacoes
