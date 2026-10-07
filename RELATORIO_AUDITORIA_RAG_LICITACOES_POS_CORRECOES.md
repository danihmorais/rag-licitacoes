# Relatório de Auditoria — RAG Licitações

## Auditoria pós-correções

**Repositório:** `danihmorais/rag-licitacoes`  
**Branch auditada:** `main`  
**Base auditada:** `7ab09d1f5e08222386e8557aeebe1d50ee83840e`  
**Data de referência da auditoria:** 07/10/2026  
**PR anterior de correções:** #19 — `Corrigir temporalidade, AST jurídico e hardening do RAG`

---

# 1. Sumário executivo

Foi realizada nova auditoria completa do estado atual do repositório após a aplicação das correções do plano de ação anterior.

As principais correções planejadas foram efetivamente implementadas:

- temporalidade passou a produzir filtro real no Qdrant;
- consultas históricas e comparativas passaram a ser diferenciadas;
- Lei nº 14.133/2021 e Manual do TCU passaram a ser contexto-base auxiliar;
- a AST jurídica passou a preservar a hierarquia interna dos anexos;
- alterações legislativas passaram a preservar múltiplas operações;
- foi adicionada suíte E2E opcional com modelos reais;
- o manifesto passou a versionar o novo schema.

A nova auditoria, entretanto, identificou **4 pontos remanescentes**:

| Severidade | Quantidade | Situação |
|---|---:|---|
| P0 — crítico | 0 | ✅ Nenhum |
| P1 — importante | 2 | ⚠️ Corrigir |
| P2 — melhoria/robustez | 2 | ⚠️ Corrigir |

O principal problema é a interação entre **temporalidade e regime jurídico**: consultas históricas que mencionam explicitamente uma lei podem deixar de receber o filtro `regime_juridico` correspondente.

Também foi identificado um problema conceitual relevante na representação da vigência: ausência de data de vigência está sendo convertida para um intervalo aberto, o que pode transformar “vigência desconhecida” em “vigência ilimitada”.

---

# 2. Estado geral

## 2.1 Arquitetura

A arquitetura atual permanece coerente:

```text
Fontes
  ↓
Sincronização / coleta
  ↓
Extração + metadata
  ↓
Chunking jurídico estrutural
  ↓
Dense + BM25
  ↓
Qdrant Server / RRF
  ↓
Reranker
  ↓
Expansão estrutural
  ↓
Evidence Gate
  ↓
LLM
```

O vetor denso, sparse retrieval, reranking e Qdrant permanecem separados logicamente.

O projeto continua utilizando **Qdrant Server**, sem retorno à abordagem legada de `QdrantClient(path=...)`.

---

# 3. Achados atuais

# P1-01 — Consulta histórica pode perder o filtro do regime jurídico

## Situação

Em `query.py`, a aplicação do regime inferido está condicionada a:

```python
if explicit_regime is None and query     and not _is_transition_query(query)     and not temporal_context.is_historicalish:
```

Isso significa que, quando a consulta é histórica, a regra que infere o regime pela menção à lei deixa de ser aplicada.

Exemplo:

```text
Qual era a regra aplicável pela Lei 8.666/1993?
```

A consulta pode ser reconhecida como histórica e, por isso, não receber:

```text
regime_juridico = lei_8666
```

Outro exemplo:

```text
A Lei 8.666/1993 estava vigente em dezembro de 2023?
```

recebe o filtro temporal, mas a restrição de regime jurídico continua podendo ser perdida.

## Por que isso importa

A temporalidade e o regime jurídico são dimensões diferentes:

```text
Regime:
    Lei 8.666/1993

Temporalidade:
    dezembro de 2023
```

Ambas devem ser aplicadas simultaneamente.

Sem o filtro de regime, a recuperação pode trazer documentos de outros regimes que apenas apresentam similaridade textual.

Isso desloca para o reranker uma tarefa que deveria ter sido resolvida no próprio retrieval.

## Impacto

Pode haver:

- mistura de regimes jurídicos;
- perda de precisão em perguntas históricas;
- recuperação de decretos, manuais ou normas relacionadas, mas não pertencentes ao regime explicitamente perguntado;
- resultados dependentes excessivamente do reranker.

## Correção recomendada

A regra deve permitir:

```text
consulta histórica
        +
regime explicitamente mencionado
        +
janela temporal
```

simultaneamente.

Em termos conceituais:

```python
regime_filter = explicit/inferred regime
temporal_filter = effective window
qdrant_filter = regime_filter AND temporal_filter
```

A exclusão de regimes históricos para consultas correntes deve continuar existindo, mas não deve impedir a aplicação de um regime histórico explicitamente solicitado.

## Testes necessários

Adicionar casos para:

```text
Lei 8.666 + consulta histórica sem data
Lei 8.666 + data exata
Lei 8.666 + mês/ano
Lei 8.666 + ano
Lei 8.666 + antes/depois
Lei 14.133 + data histórica
```

O teste deve verificar tanto a presença de:

```text
effective_from_day
effective_to_day
```

quanto de:

```text
regime_juridico
```

no mesmo `qdrant_filter`.

---

# P1-02 — “Vigência desconhecida” está sendo tratada como “vigência aberta”

## Situação

Em `ingest.py`, os limites temporais são materializados assim:

```python
_date_key(meta.get('effective_from'), 0)
_date_key(meta.get('effective_to'), 99991231)
```

Na prática:

```text
effective_from ausente → 0
effective_to ausente   → 99991231
```

Isso representa o documento como:

```text
válido desde sempre
válido até o final do horizonte temporal
```

quando, na realidade, a metadata pode apenas não ter conseguido identificar a vigência.

## Problema semântico

Há três estados distintos:

```text
1. data conhecida
2. limite efetivamente aberto
3. data desconhecida
```

O código atual reduz:

```text
2 e 3
```

ao mesmo valor.

Isso é perigoso em uma consulta histórica.

### Exemplo

Suponha uma norma com:

```text
effective_from = None
effective_to = None
```

e uma consulta:

```text
Qual regra era aplicável em 2019?
```

O documento poderá satisfazer:

```text
effective_from_day <= 20191231
effective_to_day >= 20190101
```

porque seus sentinelas correspondem a:

```text
0 <= 20191231
99991231 >= 20190101
```

Mas isso não prova que a norma estivesse vigente em 2019.

## Impacto

Pode causar falsos positivos temporais e transmitir uma falsa impressão de precisão jurídica.

## Correção recomendada

Representar explicitamente o desconhecimento.

Possíveis alternativas:

```text
effective_from_day = NULL
effective_to_day = NULL
```

com tratamento específico no retrieval,

ou adicionar flags como:

```text
effective_from_known
effective_to_known
```

ou utilizar um campo de estado:

```text
effective_range_status =
    closed
    open_start
    open_end
    unknown
```

O ponto essencial é:

> limite aberto deliberado e data desconhecida não podem ter a mesma semântica.

## Testes necessários

Cobrir pelo menos:

```text
vigência fechada
vigência sem fim conhecido por regra explícita
vigência sem início conhecido
vigência completamente desconhecida
consulta histórica sobre documento desconhecido
```

---

# P2-01 — Parser temporal pode interpretar data de citação legislativa como filtro temporal

## Situação

O parser temporal aceita mês/ano mesmo sem exigir um marcador temporal explícito:

```regex
(?:(?:em|no|na|durante)\s+)?
(janeiro|...|dezembro)
\s+de\s+(20\d{2})
```

Assim, uma consulta como:

```text
Qual é a regra da Lei 14.133, de 1º de abril de 2021, sobre ETP?
```

pode identificar:

```text
abril de 2021
```

como janela temporal.

Isso é diferente de uma consulta como:

```text
Qual regra valia em abril de 2021?
```

## Por que é uma regressão possível

A implementação anterior precisava distinguir:

```text
data de referência da consulta
```

de:

```text
data pertencente à identificação da norma
```

Com o parser novo, essas duas situações podem convergir.

## Impacto

Uma consulta atual que apenas cita a data formal de uma lei pode receber um filtro histórico sem que o usuário tenha solicitado isso.

Possíveis efeitos:

- perda de documentos atuais;
- redução indevida de recall;
- consulta atual interpretada como histórica.

## Correção recomendada

Priorizar expressões que explicitamente marquem temporalidade:

```text
em abril de 2021
durante abril de 2021
no ano de 2021
em 15/12/2023
antes de 2024
depois de 2023
```

e evitar interpretar automaticamente uma construção de identificação normativa como janela temporal.

## Testes necessários

Diferenciar:

```text
“Lei 14.133, de 1º de abril de 2021”
```

de:

```text
“regra vigente em abril de 2021”
```

---

# P2-02 — `amendment_operations` pode capturar operação dentro da redação reproduzida

## Situação

A estrutura nova:

```json
{
  "amendment_operations": [
    "alteracao",
    "revogacao"
  ]
}
```

é correta e já preserva múltiplas operações.

Porém, `_detect_amendment()` utiliza `operation_patterns` sobre o texto completo.

Ao mesmo tempo, a função já possui tratamento específico para redação legislativa reproduzida, como:

```text
Art. 5º O art. 75 passa a vigorar com a seguinte redação:
“Art. 75. Nova redação...”
```

Isso cria a possibilidade de detectar uma palavra como:

```text
revogado
```

dentro do texto reproduzido e interpretá-la como segunda operação do dispositivo alterador.

## Exemplo conceitual

```text
Fica alterado o art. 75:
“É revogado o dispositivo X...”
```

Nesse caso:

```text
alteracao
```

pode ser a operação do ato alterador, enquanto:

```text
revogacao
```

pode pertencer apenas ao conteúdo reproduzido.

## Impacto

Pode produzir metadata incorreta:

```json
"amendment_operations": [
  "alteracao",
  "revogacao"
]
```

quando existe apenas uma operação no dispositivo alterador.

## Correção recomendada

Aplicar a detecção das operações legislativas somente ao texto de operação do ato alterador, excluindo trechos de redação reproduzida quando estes não forem parte da fórmula dispositiva.

## Teste necessário

Adicionar uma regressão com:

```text
operação real
+
redação reproduzida contendo verbo legislativo
```

e garantir que a operação do texto reproduzido não seja contabilizada novamente.

---

# 4. Correções anteriores confirmadas como concluídas

## 4.1 Temporalidade real no Qdrant

Foi implementado:

```python
QueryTemporalContext
```

com suporte a:

- data exata;
- mês/ano;
- ano;
- antes de;
- depois de;
- modo histórico;
- modo comparativo.

O filtro temporal é efetivamente incorporado ao `qdrant_filter`.

Campos utilizados:

```text
effective_from_day
effective_to_day
```

O mesmo filtro é passado aos prefetches dense e sparse.

✅ **Resolvido estruturalmente.**

---

## 4.2 Contexto-base auxiliar

A política antiga de obrigatoriedade absoluta foi removida.

O prompt agora define:

```text
Lei nº 14.133/2021
Manual de Licitações e Contratos do TCU
```

como referências-base auxiliares.

A aplicação mantém a evidência principal como prioritária.

O teste de orçamento apertado confirma que a evidência principal sobrevive mesmo quando o contexto auxiliar não cabe.

✅ **Resolvido.**

---

## 4.3 AST de anexos

A AST agora pode representar:

```text
ANEXO I
└── CAPÍTULO I
    └── SEÇÃO I
        └── ART. 1º
```

O artigo deixa de apontar diretamente para o nó do anexo quando existe um pai estrutural interno válido.

Também são preservados:

```text
anexo_ref
anexo_path
path
parent_id
```

✅ **Resolvido.**

---

## 4.4 Múltiplas operações legislativas

Foi adicionado:

```text
amendment_operations
```

mantendo `amendment_type` para compatibilidade.

A ordem das operações é preservada.

Exemplo testado:

```text
alteracao
revogacao
```

✅ **Resolvido estruturalmente.**

O único ponto remanescente é a possibilidade de contaminação por texto reproduzido, registrada como P2-02.

---

## 4.5 E2E com modelos reais

Foi adicionada:

```text
tests/test_real_model_e2e.py
```

com:

```text
FastEmbed dense real
FastEmbed sparse real
reranker real
Qdrant Server real
evidence gate
```

A execução é opt-in:

```text
RAG_RUN_REAL_MODEL_E2E=1
```

A suíte determinística permanece separada para manter CI estável.

✅ **Resolvido conforme o plano.**

---

## 4.6 Manifesto

O schema do manifesto foi atualizado:

```text
manifest_schema_version = 3
legal_ast_schema_version = 2
```

e o schema passou a contemplar:

```text
effective_from
effective_to
effective_from_day
effective_to_day
amendment_operations
anexo_ref
anexo_path
device_id
```

A mudança provoca incompatibilidade deliberada com índices antigos, exigindo reindexação.

✅ **Resolvido.**

---

## 4.7 Qdrant Server

A implementação atual utiliza:

```python
QdrantClient(
    url=QDRANT_URL,
    api_key=...,
    prefer_grpc=...,
    timeout=...,
)
```

Não foram encontrados usos funcionais da abordagem:

```python
QdrantClient(path=...)
QDRANT_PATH
```

✅ **Resolvido.**

---

# 5. Validação de CI e workflows

## 5.1 CI principal

A execução mais recente verificada:

```text
CI #217
Run: 37553252861
Commit: 7ab09d1f5e08222386e8557aeebe1d50ee83840e
Conclusão: success
```

Passaram as etapas principais:

```text
instalação das dependências
runtime OCR
compileall
evidence gate
pytest
```

✅ CI principal verde.

---

## 5.2 Smoke jurídico

O smoke anterior:

```text
Smoke #132
Run: 37551597888
Conclusão: success
```

já havia concluído com sucesso.

O smoke disparado pelo merge do PR #19 estava em execução no instante da verificação final desta auditoria:

```text
Smoke #133
Run: 37553216262
Status: in_progress
```

Portanto, nesta auditoria:

```text
CI principal = verde
Smoke mais recente = ainda não concluído no momento da consulta
```

Não é correto declarar o smoke #133 como aprovado antes da conclusão do workflow.

---

# 6. Situação dos testes

A suíte recebeu novos testes para:

- parser temporal;
- filtros temporais;
- consultas históricas;
- contexto-base auxiliar;
- AST de anexos;
- múltiplas operações legislativas;
- rejeição temporal;
- E2E com Qdrant Server;
- E2E opcional com modelos reais.

A cobertura estrutural melhorou significativamente.

O principal déficit atual não é ausência total de testes, mas **casos de combinação**:

```text
regime + temporalidade
```

e:

```text
data de identificação da norma
versus
data temporal da consulta
```

---

# 7. Plano de ação recomendado

## Prioridade 1 — corrigir P1-01

Fazer o filtro funcionar como:

```text
regime jurídico explicitamente mencionado
        AND
janela temporal solicitada
```

Adicionar regressões específicas.

---

## Prioridade 2 — corrigir P1-02

Separar semanticamente:

```text
vigência aberta
```

de:

```text
vigência desconhecida
```

Evitar representar ausência de metadata como prova de validade temporal.

Adicionar testes para todas as combinações.

---

## Prioridade 3 — corrigir P2-01

Tornar a detecção de datas mais conservadora para não interpretar automaticamente a data formal da lei como data da pergunta.

Adicionar testes de falso positivo.

---

## Prioridade 4 — corrigir P2-02

Excluir redações legislativas reproduzidas da identificação de operações quando essas palavras não representarem operações do dispositivo alterador.

Adicionar regressão específica.

---

# 8. Definition of Done

A próxima rodada deve ser considerada concluída somente quando:

```text
[ ] P1-01 corrigido
[ ] P1-02 corrigido
[ ] P2-01 corrigido
[ ] P2-02 corrigido

[ ] testes unitários adicionados para cada correção
[ ] suíte offline verde
[ ] CI verde
[ ] smoke jurídico verde
[ ] E2E Qdrant determinístico verde
[ ] E2E de modelos reais validado manualmente/opt-in
[ ] manifesto compatível com o novo schema
```

---

# 9. Veredito final da auditoria

## Resultado

```text
P0: 0
P1: 2
P2: 2
```

### Conclusão

O projeto apresentou evolução substancial e as correções do PR #19 resolveram os problemas estruturais identificados anteriormente.

O sistema já possui:

- Qdrant Server como backend vetorial;
- retrieval híbrido;
- reranking;
- filtros jurídicos;
- temporalidade efetiva;
- AST jurídica;
- identificação estrutural de dispositivos;
- contexto-base auxiliar;
- evidence gate;
- avaliação versionada;
- E2E determinístico;
- E2E opcional com modelos reais;
- versionamento do schema do índice.

Entretanto, **a auditoria ainda não recomenda considerar o retrieval juridicamente fechado** enquanto não forem corrigidos principalmente:

1. a perda do filtro de regime nas consultas históricas;
2. a confusão entre vigência desconhecida e vigência aberta.

Esses dois pontos afetam diretamente a confiabilidade temporal e jurídica da recuperação.

**Veredito:** arquitetura significativamente fortalecida, sem P0, porém ainda com **2 P1 e 2 P2 remanescentes**.
