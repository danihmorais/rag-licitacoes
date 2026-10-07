# Relatório de Auditoria — RAG Licitações
## Achados remanescentes e Plano de Ação

**Repositório:** `danihmorais/rag-licitacoes`  
**Base auditada:** `main` em `0aa834017154f017a5cab8a46bc5845568cd8d88`  
**Data da auditoria:** 07/10/2026  
**Objetivo:** verificar novamente o estado do projeto após a segunda rodada de correções e registrar somente os problemas ainda remanescentes.

---

# 1. Sumário executivo

A segunda rodada de correções eliminou os dois problemas P0 identificados na auditoria anterior:

- a avaliação passou a utilizar o mesmo **Qdrant Server** empregado pela ingestão e pela consulta;
- `document_regime` passou a representar o regime do próprio documento, separado de `cited_regimes`.

Também foram implementados avanços estruturais importantes:

- AST jurídica formal;
- `source_start/source_end` verificáveis;
- identidade estrutural e `device_id`;
- múltiplos dispositivos-alvo em alterações;
- tolerância a artigos sem espaço;
- anexos com identidade própria;
- controle explícito do limite de tokens;
- limpeza de ruído repetido de borda de página;
- distinção entre consulta histórica e comparativa;
- fixtures jurídicas reais;
- E2E com Qdrant Server;
- expansão dos gatilhos do workflow de ingestão jurídica.

**Situação atual:** não foram identificados novos problemas P0. Permanecem **3 achados P1** e **2 achados P2**.

O principal ponto restante é a **temporalidade no retrieval**: a consulta pode ser reconhecida como histórica, mas essa intenção ainda não é transformada em filtro temporal efetivo no Qdrant.

---

# 2. Estado atual por severidade

| Severidade | Quantidade | Situação |
|---|---:|---|
| P0 — crítico | 0 | ✅ Resolvido |
| P1 — importante | 3 | ⚠️ Remanescente |
| P2 — melhoria/robustez | 2 | ⚠️ Remanescente |

---

# 3. Validações já realizadas

## 3.1 CI principal

O workflow **CI #208** terminou com `success`.

Etapas observadas como aprovadas:

- instalação das dependências;
- runtime OCR;
- `compileall`;
- verificação do Tesseract;
- evidence gate offline;
- suíte completa de testes.

## 3.2 Qdrant

A implementação utiliza:

```python
config.create_qdrant_client()
```

na avaliação, ingestão e runtime da consulta.

Não há mais dependência funcional da antiga abordagem:

```python
config.QDRANT_PATH
QdrantClient(path=...)
```

## 3.3 Testes estruturais

Foram adicionados testes para:

- `Art.1º`;
- `Artigo1º`;
- `Art.75-A`;
- múltiplos dispositivos-alvo;
- alínea/parágrafo como alvo de alteração;
- AST;
- spans exatos;
- anexos;
- regime documental separado de regimes citados;
- consulta histórica;
- consulta comparativa;
- prioridade da evidência principal sobre contexto auxiliar;
- ruído repetido de página;
- manifest com versão do AST.

## 3.4 E2E

O projeto agora possui E2E com Qdrant Server real, cobrindo:

```text
fixture oficial
      ↓
extração
      ↓
chunking
      ↓
metadata
      ↓
embedding de teste
      ↓
Qdrant Server
      ↓
hybrid retrieval
      ↓
reranking
      ↓
context expansion
      ↓
evidence gate
```

Esse E2E utiliza doubles determinísticos para os modelos de embedding/reranker, mantendo o Qdrant real.

---

# 4. Achados remanescentes

# P1-01 — Temporalidade reconhecida, mas não aplicada integralmente ao retrieval

## Situação

A camada de consulta agora distingue:

- consulta normal;
- consulta histórica;
- consulta comparativa/transição.

Exemplo:

```text
A Lei 8.666/1993 estava vigente em dezembro de 2023?
```

é reconhecida como:

```text
is_transition = false
is_historical = true
regime_hint = lei_8666
```

Isso é correto como classificação semântica.

Porém, a intenção temporal ainda não é convertida em um filtro Qdrant correspondente a:

```text
effective_from <= data
effective_to >= data
```

ou equivalente para documentos sem limite final.

## Problema adicional

A chave:

```python
filtered_for_current_only
```

continua sendo derivada somente de `is_transition` e `regime_hint`.

Assim, uma consulta histórica específica pode aparecer como se estivesse no modo de recuperação de regime corrente, apesar de a própria consulta pedir uma data histórica.

## Impacto

Em um corpus com:

- versões históricas;
- normas substituídas;
- decretos anuais;
- alterações sucessivas;
- versões consolidadas;

o sistema pode recuperar uma evidência correta quanto ao **regime**, mas incorreta quanto à **vigência temporal**.

Isso é particularmente perigoso para:

- valores atualizados por ano;
- vigência de normas;
- transição legislativa;
- regras substituídas;
- perguntas com data explícita.

## Plano de ação

### Fase A — Modelo temporal da consulta

Criar um objeto interno semelhante a:

```python
QueryTemporalContext(
    mode="current|historical|comparative",
    effective_on=date | None,
    effective_from=date | None,
    effective_to=date | None,
)
```

### Fase B — Extração de datas

Reconhecer pelo menos:

```text
em 2023
em dezembro de 2023
em 15/12/2023
em 2024
na época
antes de 2024
depois de 2023
```

### Fase C — Filtro Qdrant

Quando houver `effective_on`:

```text
effective_from <= effective_on
AND
(effective_to IS NULL OR effective_to >= effective_on)
```

Quando a infraestrutura atual não suportar ausência de campo com a mesma semântica, estabelecer uma regra explícita para representar vigência aberta.

### Fase D — Dataset

Adicionar casos de:

```text
versão correta
versão histórica incorreta
mesmo regime em versões diferentes
ano de vigência
data fora da janela
```

### Fase E — Métrica

Separar:

```text
regime_accuracy
temporal_accuracy
temporal_rejection_accuracy
```

### Critério de conclusão

Uma consulta histórica com data explícita deve:

1. classificar corretamente a intenção;
2. aplicar filtro temporal real;
3. não depender apenas do reranker para corrigir versões incompatíveis.

---

# P1-02 — Regra de contexto obrigatório ainda está semanticamente contraditória

## Situação

O `SYSTEM_PROMPT` determina que toda resposta deve ter:

```text
Lei 14.133/2021
Manual de Licitações e Contratos do TCU
```

como fontes obrigatórias.

Ao mesmo tempo, a implementação atual deliberadamente dá prioridade às evidências principais e adiciona essas duas fontes como `context_only`.

Quando o limite:

```text
RAG_MAX_CONTEXT_CHARS
```

é atingido, `context_with_sources()` pode descartar os itens marcados como:

```text
_context_only = true
```

antes de descartar a evidência principal.

## Resultado

Pode existir um estado operacional em que:

```text
evidência principal = presente
Lei 14.133 = ausente
Manual TCU = ausente
```

enquanto o prompt ainda exige as duas fontes.

Isso representa uma divergência entre:

```text
política declarada
```

e

```text
política efetivamente executada
```

## Impacto

O principal risco não é de segurança, mas de consistência:

- o prompt pode exigir uma fonte que a aplicação efetivamente não entregou;
- uma futura alteração do limite de contexto pode mudar silenciosamente essa propriedade;
- o comportamento fica difícil de interpretar no debugging.

## Plano de ação

Há duas alternativas válidas. A recomendação é a segunda.

### Opção 1 — Obrigatório absoluto

Reservar espaço de contexto para:

```text
1 evidência Lei 14.133
1 evidência Manual TCU
```

e só então preencher o restante.

**Problema:** pode reduzir demais a evidência principal em perguntas específicas.

### Opção 2 — Reclassificar como contexto auxiliar

Alterar a política para:

```text
A Lei 14.133/2021 e o Manual do TCU são fontes-base auxiliares.
Eles não podem expulsar a evidência primária principal.
```

Nesse caso:

- remover a promessa de obrigatoriedade absoluta;
- manter `mandatory_context = true` apenas quando efetivamente inserido;
- deixar o prompt refletir a mesma regra da aplicação.

**Recomendação:** Opção 2.

### Testes

Criar pelo menos:

```text
contexto folgado → fontes auxiliares presentes
contexto apertado → evidência principal preservada
contexto mínimo → política ainda consistente
```

### Critério de conclusão

Não deve existir divergência entre o que o código recupera e o que o prompt afirma estar garantido.

---

# P1-03 — AST jurídica ainda possui uma lacuna na hierarquia interna de anexos

## Situação

A AST passou a representar:

```text
norma
 ├── estrutura
 ├── anexo I
 ├── artigo
 └── anexo II
```

e a identidade de artigos repetidos em anexos foi corretamente diferenciada.

Porém, em estruturas internas de anexo, a ligação estrutural ainda pode não seguir todo o caminho:

```text
ANEXO I
└── CAPÍTULO I
    └── SEÇÃO I
        └── ART. 1º
```

porque o código trata o artigo com `anexo_ref` usando o nó do anexo como pai estrutural preferencial.

## Impacto

Isso não costuma gerar colisão de IDs, mas reduz a fidelidade da AST como representação jurídica.

Pode afetar no futuro:

- navegação estrutural;
- expansão de contexto;
- breadcrumbs;
- filtragem por capítulo dentro de anexo;
- avaliação por dispositivo;
- reconstrução de contexto.

## Plano de ação

### Fase A — Pai estrutural do artigo

Quando o artigo estiver dentro de anexo:

```text
parent = último header estrutural válido dentro do anexo
```

e somente na ausência dele:

```text
parent = nó do anexo
```

### Fase B — Propagação do caminho

Garantir:

```python
anexo_path
hierarchy_path
parent_id
```

com todos os níveis efetivamente percorridos.

### Fase C — IDs

Manter:

```text
norma/anexo:I/capitulo:I/artigo:1
```

ou equivalente estável.

### Testes

Cobrir:

```text
Anexo I → Capítulo → Seção → Artigo
Anexo II → Capítulo → Artigo
Art. 1º no corpo
Art. 1º no Anexo I
Art. 1º no Anexo II
```

### Critério de conclusão

Todo dispositivo deve possuir o pai jurídico imediatamente superior disponível na AST.

---

# P2-01 — `amendment_type` continua singular

## Situação

Os múltiplos dispositivos-alvo já são preservados:

```json
{
  "target_devices": [
    {"kind": "alinea", "...": "..."},
    {"kind": "paragrafo", "...": "..."}
  ]
}
```

Porém a operação da alteração ainda é representada por um único:

```text
amendment_type
```

## Problema

Um único artigo de uma norma alteradora pode combinar operações como:

```text
altera X
revoga Y
acrescenta Z
```

Nesse caso, o modelo atual perde parte da informação operacional.

## Plano de ação

Substituir ou complementar:

```text
amendment_type
```

por:

```json
"amendment_operations": [
  "alteracao",
  "revogacao",
  "acrescimo"
]
```

Opcionalmente, associar operação ao alvo:

```json
{
  "operation": "revogacao",
  "targets": [...]
}
```

## Critério de conclusão

Nenhuma operação legislativa deve ser perdida quando múltiplas ações coexistirem no mesmo dispositivo.

---

# P2-02 — E2E usa Qdrant real, mas os modelos são doubles

## Situação

O E2E atual usa:

```text
Qdrant Server real
```

com:

```text
dense fake
sparse fake
reranker fake
```

Essa escolha é correta para estabilidade e velocidade do CI.

## O que o teste já cobre

Ele valida de fato:

- criação da coleção;
- schema;
- payload;
- upsert;
- hybrid retrieval;
- RRF;
- reranking;
- expansão de contexto;
- evidence gate;
- integridade dos spans.

## O que ainda não cobre

Não valida o comportamento de:

```text
FastEmbed real
tokenizer real
modelo dense real
BM25 real
reranker real
```

integrados no mesmo fluxo.

## Plano de ação

Não substituir o E2E determinístico.

Adicionar uma segunda suíte:

```text
E2E-lite offline/CI
    doubles determinísticos

E2E-modelos
    modelos reais
```

Executar a segunda:

- manualmente;
- nightly;
- ou apenas em ambiente com cache dos modelos.

## Critério de conclusão

Existirem duas camadas de validação claramente separadas, sem tornar o CI principal frágil.

---

# 5. Pontos importantes já resolvidos

## 5.1 Avaliação e Qdrant

Resolvido:

```python
client = config.create_qdrant_client()
```

A avaliação agora compartilha a mesma arquitetura do runtime.

## 5.2 Regime documental

Resolvido:

```text
document_regime
```

representa a norma/documento.

Enquanto:

```text
cited_regimes[]
```

representa referências a outros regimes.

Uma Lei 14.133 que mencione a Lei 8.666 não vira automaticamente:

```text
transicao
```

## 5.3 Alterações múltiplas

Resolvido em grande parte:

```text
target_devices[]
target_articles[]
```

e preservação de referências como:

```text
§ 2º do art. 75
alínea "a" do inciso IV do art. 75
item 2
```

## 5.4 Artigos sem espaço

Resolvido:

```text
Art.1º
Artigo1º
Art.75-A
```

## 5.5 AST

Já existe `LegalNode` com:

```text
node_id
kind
ref
parent_id
source_start
source_end
source_text
children
path
anexo_ref
anexo_path
```

## 5.6 Spans

A implementação verifica:

```python
full_text[source_start:source_end] == source_text
```

Isso é uma das invariantes mais importantes do pipeline.

## 5.7 Token budget

O sistema deixou de depender de truncamento implícito.

Antes de gerar o embedding:

```text
embedding_text <= RAG_DENSE_MAX_TOKENS
```

é validado explicitamente.

---

# 6. Plano de ação consolidado

## Fase 1 — Temporalidade de retrieval
**Prioridade: P1**

### Implementar

- parser de data na consulta;
- modelo interno de contexto temporal;
- filtros temporais Qdrant;
- tratamento de vigência aberta;
- testes de versões concorrentes;
- métricas temporais.

### Definição de pronto

```text
consulta histórica + data
        ↓
classificação temporal
        ↓
filtro Qdrant
        ↓
somente versões compatíveis
```

---

## Fase 2 — Política de contexto obrigatório
**Prioridade: P1**

### Implementar

- alinhar `SYSTEM_PROMPT` com o comportamento real;
- transformar Lei 14.133 + Manual TCU em contexto auxiliar;
- preservar evidência principal em contexto pequeno;
- adicionar testes de orçamento.

### Definição de pronto

O prompt e o código devem descrever exatamente a mesma política.

---

## Fase 3 — Hierarquia completa de anexos
**Prioridade: P1**

### Implementar

- pai imediato dos dispositivos;
- propagação de capítulos/seções/subseções;
- IDs estruturais completos;
- testes de anexos com hierarquia interna.

### Definição de pronto

```text
norma
└── anexo
    └── capítulo
        └── seção
            └── artigo
                └── inciso
```

ser reconhecido como árvore real.

---

## Fase 4 — Operações múltiplas em alterações
**Prioridade: P2**

### Implementar

- `amendment_operations[]`;
- associação opcional operação → alvo;
- cobertura de alterações compostas.

### Definição de pronto

Nenhuma operação legislativa relevante é perdida.

---

## Fase 5 — E2E com modelos reais
**Prioridade: P2**

### Implementar

- suíte separada;
- modelos reais;
- execução controlada;
- comparação com E2E determinístico.

### Definição de pronto

Existir validação:

```text
source
→ extraction
→ AST
→ chunks
→ embeddings reais
→ Qdrant
→ retrieval real
→ gate
```

sem contaminar a confiabilidade do CI principal.

---

# 7. Ordem recomendada de implementação

A ordem técnica recomendada é:

```text
1. Temporalidade
2. Política de contexto
3. Hierarquia de anexos
4. Operações múltiplas
5. E2E com modelos reais
```

A temporalidade deve ser feita primeiro porque é a única lacuna remanescente com potencial direto de produzir **evidência juridicamente correta no regime errado para a data perguntada**.

---

# 8. Definition of Done da próxima rodada

A próxima rodada deve ser considerada concluída somente quando:

- [ ] nenhuma inconsistência temporal relevante permanecer no retrieval;
- [ ] consulta histórica com data gerar filtro temporal real;
- [ ] `SYSTEM_PROMPT` e implementação de contexto utilizarem a mesma política;
- [ ] artigos dentro de anexos possuírem pai estrutural correto;
- [ ] alterações com operações múltiplas não perderem informação;
- [ ] E2E determinístico permanecer verde;
- [ ] suíte principal permanecer verde;
- [ ] smoke jurídico permanecer verde;
- [ ] nenhum P0 novo for introduzido;
- [ ] manifest/schema continuarem compatíveis;
- [ ] testes de regressão cobrirem cada correção.

---

# 9. Veredito final da auditoria

**Classificação atual:**

```text
P0  → 0
P1  → 3
P2  → 2
```

O projeto está em um estado substancialmente mais maduro do que na auditoria anterior e **não apresenta, neste momento, os dois P0 que anteriormente impediam considerar a segunda fase concluída**.

Ainda assim, para um RAG jurídico orientado à recuperação confiável, a implementação deve avançar principalmente na **temporalidade aplicada ao índice**. Depois dela, as questões restantes são de consistência arquitetural e completude da representação jurídica, e não de falhas críticas já identificadas.

