# Relatório técnico — auditoria de código: `danihmorais/rag-licitacoes`

**Formato:** destinado a consumo por outro agente de IA (contexto denso, sem prosa decorativa).
**Método:** clone raso do `main` (commit HEAD no momento da auditoria) e leitura manual de `ingest.py`, `query.py`, `chunking.py`, `metadata.py`, `config.py`, `index_manifest.py`, `scripts/sync_sources.py`, `jurisprudencia/collector.py`, `llm/openai_compatible.py`. Não foram executados testes nem o pipeline completo (sem Qdrant/embeddings reais); achados são de leitura estática + raciocínio sobre fluxo de dados.
**Escopo não coberto:** `jurisprudencia/batch.py`, `jurisprudencia/schema.py`, `jurisprudencia/queries.py`, `llm/gemini.py`, `llm/ollama.py`, `scripts/sources.py`/`sources_additional.py` (conteúdo de dados), suíte de testes.

---

## Achados críticos

### 1. `query.py` — perda de evidência de alta relevância no truncamento de contexto
`expand_context()` reordenava a lista por `(source, unit_id, chunk_index)`, e não por score. Com `FINAL_K=8`, `CONTEXT_NEIGHBORS=1` e `MAX_CONTEXT_CHARS=26000`, chunks de maior evidência podiam ser descartados quando o contexto atingia o limite.

### 2. `metadata.py` — classificação de jurisdição ambígua para Lei 14.133 + regulamentação paulista
O teste de nomes contendo `14.133` ocorria antes do teste de São Paulo. Regulamentação estadual paulista da Lei 14.133 podia ser classificada como federal.

### 3. `metadata.py` — falso positivo em `name.startswith('sp')`
Arquivos iniciados literalmente por `sp` podiam cair na classificação estadual paulista mesmo sem relação com o Estado de São Paulo.

### 4. `metadata.py` — ano extraído pelo primeiro `20xx`
O primeiro ano encontrado nos primeiros 30.000 caracteres podia ser uma referência normativa anterior e não o ano do próprio documento.

### 5. `metadata.py` — TJSP com o mesmo `authority_level` de STF/STJ/TCU/TCESP
A escala documentada era `STF=2, STJ=3, TCU=3, TCESP=4, TJSP=4`, mas algumas rotinas antigas atribuíam `2` uniformemente a tribunais.

### 6. `chunking.py` — colisão potencial de `unit_id`
O identificador derivado apenas de tipo + referência textual podia colidir quando a mesma referência fosse repetida no documento.

### 7. `chunking.py` — atribuição de página por aproximação silenciosa
Quando o trecho não era encontrado exatamente no texto, o fallback podia usar a última posição conhecida sem indicar incerteza.

### 8. `index_manifest.py` — manifesto não versionava a lógica de chunking
Os parâmetros numéricos eram registrados, mas alterações nas regex/regras do algoritmo podiam não invalidar o índice existente.

### 9. `ingest.py` — cache persistido apenas ao fim
Uma interrupção no meio da ingestão podia causar reprocessamento desnecessário no próximo ciclo, embora os IDs determinísticos mantivessem o upsert idempotente.

---

## Observações menores

- `query.py::qfilter` tinha somente igualdade, sem intervalo/OR.
- Adapters de tribunais dependiam de HTML/JSON externo sem fixtures versionadas.
- A classificação por nome era uma cadeia `elif`, sem sinalização forte de ambiguidade.
- Não havia conjunto de avaliação golden para recall@k/MRR/nDCG.
- TJSP e súmulas do TCU tinham cobertura estruturada incompleta.

---

## Priorização registrada

1. Truncamento de contexto.
2. Jurisdição e autoridade.
3. Extração de ano.
4. Robustez de citações.
5. Manifesto e cache.

