# Plano de Correções — RAG Licitações
## Segunda auditoria pós-correções

**Repositório:** `danihmorais/rag-licitacoes`  
**Base auditada:** `2a3cf4ab8a2728421956970fb35dcefd6a879bc6`  
**Objetivo:** eliminar as falhas remanescentes identificadas após a primeira rodada de correções, com prioridade máxima para integridade jurídica do chunking, consistência de metadados, avaliação real e integração com Qdrant Server.

---

# Visão geral

As correções anteriores resolveram grande parte dos problemas estruturais, mas a nova auditoria encontrou cinco blocos ainda críticos:

1. `evaluation.py` ainda usa a API antiga de Qdrant local por caminho.
2. `document_regime` ainda pode virar `transicao` apenas porque o texto cita mais de uma lei.
3. O parser de alterações legislativas ainda é heurístico e não representa completamente múltiplos dispositivos e tipos de alteração.
4. O limite de tokens está protegido por falha posterior, mas o gerador de chunks ainda pode produzir estruturas que excedem o orçamento.
5. Os testes chamados de “reais” ainda usam fixture sintética e não existe E2E completo até Qdrant/retrieval.

Além disso, permanecem melhorias importantes em artigos mal espaçados, anexos, OCR/PDF, consultas históricas e cobertura do CI.

---

# Critérios globais de sucesso

Ao final das fases, o sistema deve obedecer estas invariantes:

```text
1. Nenhum documento normativo pode ser classificado como "transicao"
   somente porque cita outra norma.

2. Todo chunk possui localização verificável na fonte:
   source_start/source_end → source_text == fonte[start:end].

3. Nenhum embedding é enviado acima de RAG_DENSE_MAX_TOKENS.

4. Um artigo reproduzido dentro de uma lei alteradora nunca vira,
   por engano, um novo artigo irmão da norma alteradora.

5. Todos os dispositivos relevantes de uma alteração múltipla são preservados.

6. Artigos equivalentes em anexos diferentes são distinguíveis
   pela identidade estrutural.

7. A avaliação live usa exatamente o mesmo backend Qdrant Server
   utilizado pela ingestão e pela consulta normal.

8. Existe pelo menos uma bateria com legislação real e uma bateria E2E
   source → extração → chunk → embedding → Qdrant → retrieval → gate.

9. CI verde sozinho não é considerado suficiente: os gates jurídicos
   precisam executar as invariantes acima.
```

---

# Fase 0 — Baseline e congelamento da situação atual

## Objetivo

Estabelecer uma fotografia reprodutível antes das próximas mudanças.

## Ações

Registrar:

```text
HEAD atual
versão Python
versões das dependências
configuração de embedding
limite de tokens
configuração Qdrant
resultado de pytest
resultado do CI
resultado do smoke jurídico
```

Executar localmente:

```bash
python -m compileall -q .
python -m pytest -q
python evaluation.py --gate-only --strict --min-gate-rejection 0.80
```

Validar também:

```text
RAG_QDRANT_URL
RAG_QDRANT_PREFER_GRPC
RAG_DENSE_MAX_TOKENS
RAG_INDEX_VERSION
```

## Resultado esperado

Uma baseline armazenada em teste/log, sem modificar comportamento.

## Critério de conclusão

- `pytest` verde.
- evidence gate verde.
- configuração sem referências residuais ao antigo Qdrant local.

---

# Fase 1 — Corrigir completamente a avaliação live e Qdrant Server

## Prioridade

**P0**

## Problema

`evaluation.py` ainda referencia:

```python
config.QDRANT_PATH
QdrantClient(path=...)
```

enquanto o restante do projeto usa Qdrant Server.

Isso quebra a avaliação live.

## Implementação

Substituir a criação do cliente em `evaluation.py` por:

```python
client = config.create_qdrant_client()
```

Eliminar qualquer dependência de:

```text
QDRANT_PATH
QdrantClient(path=...)
```

na avaliação.

A validação do índice deve continuar baseada em:

```text
index_manifest.json
coleção Qdrant Server
configuração atual
```

## Testes obrigatórios

Criar teste que verifique que `build_retriever()`:

- chama `config.create_qdrant_client()`;
- não acessa `QDRANT_PATH`;
- verifica existência da coleção no servidor;
- valida o manifest.

Criar teste de compatibilidade do cliente:

```text
evaluation
        ↓
config.create_qdrant_client()
        ↓
QDRANT_URL
```

## Critério de conclusão

Nenhuma ocorrência funcional de:

```text
QDRANT_PATH
QdrantClient(path=
```

no runtime.

A avaliação live deve inicializar com o mesmo backend usado por `ingest.py` e `query.py`.

---

# Fase 2 — Separar definitivamente regime do documento e regimes citados

## Prioridade

**P0**

## Problema

Atualmente `_detect_regime()` pode fazer:

```text
Lei 14.133 + citação da Lei 8.666
        ↓
transicao
```

Isso corrompe a identidade jurídica do documento.

## Regra correta

Definir claramente:

```text
document_regime
    = regime jurídico da própria norma/documento

cited_regimes[]
    = regimes de outras normas mencionadas ou remetidas

transicao
    = somente quando o próprio documento representar conteúdo
      de transição/comparação legislativa.
```

## Estratégia

A prioridade de identificação deve ser:

```text
1. sidecar explícito
2. source_id/catalogo
3. título/nome da própria fonte
4. cabeçalho normativo da própria fonte
5. heurística textual somente como último recurso
```

Não usar simplesmente:

```python
len(detected) > 1
```

como critério de transição.

## Exemplo obrigatório

Documento:

```text
LEI Nº 14.133, DE 1º DE ABRIL DE 2021

Art. ...
Conforme a Lei nº 8.666/1993...
```

deve resultar em:

```json
{
  "document_regime": "lei_14133",
  "regime_juridico": "lei_14133",
  "cited_regimes": ["lei_8666"]
}
```

## Documento de transição

Somente uma fonte realmente dedicada a:

```text
regime de transição
comparação entre regimes
regras de aplicação temporal
```

poderá ser:

```text
transicao
```

## Testes obrigatórios

Adicionar:

```text
Lei 14.133 citando Lei 8.666 → regime = lei_14133
Lei 14.133 citando LC 123 → regime = lei_14133
Lei 8.666 citando Lei 14.133 → regime = lei_8666
documento de comparação explícita → transicao
```

## Critério de conclusão

Nenhuma norma primária pode mudar de regime apenas por citar outra norma.

---

# Fase 3 — Modelar alterações legislativas de forma completa

## Prioridade

**P0/P1**

## Problema

O detector atual identifica alguns padrões, mas ainda trabalha com:

```text
target_article
```

no singular.

Isso é insuficiente para alterações como:

```text
Ficam acrescentados os arts. 75-A e 76-A.
```

e não cobre toda a gramática de alteração normativa.

## Objetivo

Transformar alteração legislativa em uma estrutura explícita.

Modelo recomendado:

```json
{
  "amendment": true,
  "amendment_type": "acrescimo",
  "target_devices": [
    {
      "kind": "artigo",
      "ref": "Art. 75-A"
    },
    {
      "kind": "artigo",
      "ref": "Art. 76-A"
    }
  ]
}
```

## Tipos mínimos

Suportar explicitamente:

```text
redacao
acrescimo
revogacao
supressao
substituicao
inclusao
alteracao
inciso
paragrafo
alinea
item
```

## Dispositivos alvo

O alvo deve poder ser:

```text
artigo
paragrafo
inciso
alinea
item
```

e não apenas artigo.

Exemplos:

```text
Art. 75
§ 2º do art. 75
inciso IV do art. 75
alínea "a" do inciso IV
item 2
```

## Regras de reprodução entre aspas

Uma sequência como:

```text
Art. 5º O art. 75 passa a vigorar com a seguinte redação:
“Art. 75. Nova redação.”
```

deve gerar:

```text
unidade Art. 5º
    amendment = true
    target = Art. 75

não:
    unidade Art. 75 irmã
```

A reprodução continua sendo conteúdo da alteração, não uma nova unidade estrutural da lei alteradora.

## Alterações múltiplas

Preservar todos os alvos:

```text
75-A
76-A
77
§ 2º do 77
```

sem perder os demais por pegar apenas o primeiro match.

## Critério de conclusão

Testes cobrindo no mínimo:

```text
um alvo
dois alvos
mais de dois alvos
artigo
parágrafo
inciso
alínea
item
revogação
redação nova
acréscimo
bloco entre aspas
(NR)
```

---

# Fase 4 — Formalizar a árvore estrutural jurídica

## Prioridade

**P1**

## Problema

O parser atual possui caminhos hierárquicos, mas ainda não possui uma árvore jurídica como fonte de verdade.

## Objetivo

Introduzir estrutura intermediária do tipo:

```python
LegalNode(
    node_id=...,
    kind=...,
    ref=...,
    parent_id=...,
    children=...,
    source_start=...,
    source_end=...,
    source_text=...,
)
```

## Hierarquia

A árvore deve permitir:

```text
norma
└── parte
    └── livro
        └── titulo
            └── capitulo
                └── secao
                    └── subseção
                        └── artigo
                            ├── caput
                            └── paragrafo
                                └── inciso
                                    └── alinea
                                        └── item
```

## Regra arquitetural

A árvore passa a ser a fonte de verdade.

Os chunks tornam-se uma projeção:

```text
AST jurídico
      ↓
segmentação
      ↓
chunks de recuperação
```

Não o contrário.

## Benefícios

Isso resolve de forma mais segura:

```text
parent/child
anexos
dispositivos repetidos
unidade_id
contexto
alterações
navegação
avaliação por dispositivo
```

## Critério de conclusão

Cada dispositivo reconhecido deve possuir:

```text
parent_id
node_id
kind
ref
source_start
source_end
```

---

# Fase 5 — Garantia absoluta do orçamento de tokens

## Prioridade

**P0/P1**

## Problema

A implementação atual pode gerar um chunk cujo contexto estrutural exceda o limite e somente depois provocar `RuntimeError`.

Isso é seguro contra truncamento silencioso, mas não é suficiente.

## Objetivo

Garantir:

```text
token_count(embedding_text) <= RAG_DENSE_MAX_TOKENS
```

como invariável de saída.

## Estratégia

Separar claramente:

```text
source_text
```

e:

```text
retrieval_text
```

O texto jurídico original nunca deve ser truncado por motivo de embedding.

Quando o contexto não couber:

```text
preservar source_text integralmente
reduzir apenas contexto auxiliar
reduzir hierarquia textual redundante
dividir body
```

Nunca:

```text
truncar a evidência jurídica original de forma silenciosa.
```

## Ordem para reduzir contexto

```text
1. título da norma
2. níveis hierárquicos mais altos
3. rótulos auxiliares
4. caput contextual, somente se houver uma representação alternativa
5. nunca truncar silenciosamente source_text
```

## Regra para caput enorme

Quando o caput ultrapassar o espaço disponível:

```text
source_text = filho original
retrieval_text = filho + resumo/trecho contextual limitado
```

O caput completo permanece armazenado na unidade/árvore e disponível para expansão.

## Testes

Criar casos com:

```text
caput de 1.000 tokens
caput de 2.000 tokens
hierarquia extensa
child de 500 tokens
limite 128
limite 256
limite 512
```

e verificar:

```text
nenhum embedding_text > limite
source_text sem truncamento
```

## Critério de conclusão

A função de chunking deve produzir estruturas sempre compatíveis com o limite configurado.

---

# Fase 6 — Artigos e marcadores com espaçamento irregular

## Prioridade

**P1**

## Problema

Ainda há dependência de espaço:

```text
Art. 1º
```

funciona, mas:

```text
Art.1º
```

pode falhar.

## Objetivo

Aceitar variações legítimas ou provenientes de OCR/PDF:

```text
Art. 1º
Art.1º
Artigo 1º
Artigo1º
Art. 1
Art.1
Art. 75-A
Art.75-A
```

sem transformar números em artigos indevidos.

## Regra

Normalização para análise estrutural deve ser tolerante.

Offsets devem continuar sendo os do texto original.

## Testes

Adicionar casos para:

```text
Art.1º
Art. 1º
Artigo1º
Artigo 1º
Art. 75-A
Art.75-A
Art. 1.045
```

e falsos positivos:

```text
art. 1.045 de uma frase
referência "conforme Art. 75..."
```

---

# Fase 7 — Anexos como subárvores reais

## Prioridade

**P1**

## Problema

O parser usa `inside_anexo`, mas o anexo ainda não é representado de maneira completa no caminho estrutural.

## Objetivo

Representar:

```text
Norma
 ├── corpo
 ├── ANEXO I
 │    ├── Art. 1º
 │    └── Art. 2º
 └── ANEXO II
      └── Art. 1º
```

## Regra

`Art. 1º` do corpo e `Art. 1º` do ANEXO I devem ser diferentes por identidade estrutural.

Exemplo:

```text
norma:lei14133/artigo:1
norma:lei14133/anexo:I/artigo:1
norma:lei14133/anexo:II/artigo:1
```

## Metadados

Adicionar, quando aplicável:

```text
anexo_ref
anexo_path
```

ou equivalente na estrutura do nó.

## Critério de conclusão

Teste com múltiplos anexos e artigos repetidos em cada anexo.

---

# Fase 8 — Robustez de extração PDF/OCR

## Prioridade

**P1**

## Objetivo

Separar:

```text
extração
normalização
estruturação
```

e evitar que problemas físicos do PDF alterem a semântica jurídica.

## Casos obrigatórios

Testar:

```text
cabeçalho repetido
rodapé repetido
número de página
hifenização
palavras quebradas
duas colunas
parágrafo quebrado entre páginas
Artigo quebrado entre páginas
§ quebrado entre páginas
OCR de "Artig0"
OCR de "Paragraf0"
```

## Cuidado com remoção de ruído

O sanitizer não deve remover automaticamente uma linha normativa legítima somente por parecer:

```text
LEI...
DECRETO...
PORTARIA...
```

A detecção de cabeçalho/rodapé deve utilizar contexto de repetição e posição de página quando possível.

## Critério de conclusão

Nenhuma limpeza pode modificar o `source_start/source_end` do texto original sem manter mapeamento verificável.

---

# Fase 9 — Separar consulta histórica, consulta de transição e consulta específica

## Prioridade

**P1**

## Problema

Hoje mencionar a Lei 8.666 automaticamente pode transformar qualquer pergunta em consulta de transição.

Isso mistura:

```text
consulta histórica
consulta comparativa
consulta normativa específica
```

## Política recomendada

### Consulta específica

```text
Qual era o prazo na Lei 8.666/1993?
```

→ foco:

```text
lei_8666
```

### Consulta histórica temporal

```text
A Lei 8.666 era aplicável em dezembro de 2023?
```

→ foco:

```text
lei_8666
```

com filtro temporal.

### Consulta comparativa

```text
O que mudou entre a Lei 8.666 e a Lei 14.133?
```

→ abrir:

```text
lei_8666
lei_14133
```

### Consulta genérica atual

```text
Qual é a regra atual para...
```

→ privilegiar norma vigente.

## Critério de conclusão

Adicionar testes específicos para as quatro classes acima.

---

# Fase 10 — Reorganizar o contexto obrigatório

## Prioridade

**P1**

## Problema

Lei 14.133 e Manual do TCU são obrigatórios em toda consulta e competem pelo orçamento de contexto.

## Objetivo

Separar:

```text
evidência principal
```

de:

```text
referência auxiliar obrigatória
```

## Política

A evidência principal deve ser definida por:

```text
relevância
jurisdição
regime
temporalidade
autoridade
```

O bloco obrigatório pode aparecer como:

```text
contexto auxiliar
```

sem expulsar as evidências juridicamente mais importantes.

## Regra

Uma pergunta específica sobre:

```text
Constituição
TCESP
STJ
Lei SP 10.177
```

não deve perder a principal evidência porque duas fontes obrigatórias ocuparam o contexto.

## Critério de conclusão

Criar teste com contexto pequeno e verificar que as fontes principais continuam presentes.

---

# Fase 11 — Fixture de legislação real

## Prioridade

**P0**

## Problema

`tests/fixtures/legal_act.txt` é sintética e não comprova comportamento perante uma legislação real.

## Objetivo

Criar fixtures extraídas de fontes oficiais.

## Mínimo recomendado

```text
Lei 14.133/2021
Lei 8.666/1993
LC 123/2006
LINDB
CF/1988
```

Mais pelo menos:

```text
5 normas alteradoras
```

e material contendo:

```text
ANEXO
NR
artigos com letras
revogações
alterações
múltiplos incisos
múltiplas alíneas
```

## Regras

As fixtures devem permanecer:

```text
determinísticas
versionadas
reproduzíveis
```

e preferencialmente identificadas por:

```text
fonte oficial
data de coleta
hash
```

## Critério de conclusão

O parser deve passar pelas fixtures reais preservando:

```text
ordem
referência
hierarquia
offset
identidade
alterações
```

---

# Fase 12 — Avaliação por dispositivo

## Prioridade

**P0**

## Objetivo

Não basta verificar:

```text
expected_source_id
```

É necessário medir:

```text
artigo
parágrafo
inciso
alínea
item
unit_id
```

## Métricas

Manter:

```text
recall@k
nDCG@k
MRR
```

e acrescentar/fortalecer:

```text
article_recall@k
device_recall@k
false_positive_article_rate@k
```

## Novas dimensões

Avaliar separadamente:

```text
caput
parágrafo
inciso
alínea
item
anexo
alteração
```

## Critério de conclusão

Casos de avaliação devem indicar os dispositivos esperados sempre que a pergunta tiver resposta localizada.

---

# Fase 13 — E2E verdadeiro com Qdrant Server

## Prioridade

**P0**

## Pipeline

Criar uma suíte que execute:

```text
fixture legal
    ↓
extração
    ↓
normalização
    ↓
metadata
    ↓
chunking
    ↓
validação de tokens
    ↓
embedding
    ↓
upsert Qdrant Server
    ↓
consulta hybrid
    ↓
reranking
    ↓
expansão de contexto
    ↓
evidence gate
```

## Ambiente

Usar um Qdrant Server temporário/de teste.

Não voltar ao modo:

```text
Qdrant local em path
```

## Requisitos

O teste deve verificar:

```text
documento indexado
coleção correta
payload correto
unit_id correto
retrieval do dispositivo correto
fonte correta
regime correto
offset correto
```

## Critério de conclusão

Existe pelo menos um teste E2E determinístico que prove o pipeline inteiro.

---

# Fase 14 — CI jurídico completo

## Prioridade

**P1**

## Problema

`legal-ingestion.yml` não reage diretamente a alterações no núcleo:

```text
chunking.py
ingest.py
metadata.py
query.py
config.py
evaluation.py
index_manifest.py
```

## Alteração

Adicionar os arquivos críticos aos `paths`.

Também considerar:

```text
embedding_utils.py
tests/fixtures/**
evaluation/**
```

## Gates mínimos

### Gate estrutural

```text
pytest
```

### Gate de evidence

```text
evaluation.py --gate-only --strict ...
```

### Gate de parser jurídico

```text
fixtures reais
```

### Gate de integração

```text
Qdrant Server
```

quando o ambiente suportar.

## Critério de conclusão

Uma alteração no parser não pode escapar do conjunto de testes jurídicos.

---

# Fase 15 — Manifest, cache e invalidação

## Prioridade

**P1**

## Objetivo

Garantir que mudanças semânticas obriguem a reindexação.

## Verificar

O manifest deve considerar:

```text
algoritmo de chunking
modelo dense
dimensão
limite de tokens
chunk size
overlap
OCR
schema do payload
```

## Novos campos, se introduzidos

Se a estrutura mudar para AST:

```text
manifest_schema_version
legal_ast_schema_version
```

ou equivalente.

## Regra

Mudança estrutural incompatível:

```text
não reutilizar índice antigo.
```

---

# Fase 16 — Limpeza e endurecimento final

## Prioridade

**P2**

Depois de todas as fases anteriores:

- remover `_split_trailing_structure()` se realmente não houver mais uso;
- eliminar compatibilidade residual com Qdrant local;
- remover código morto;
- padronizar formatação;
- revisar nomenclatura;
- documentar invariantes;
- atualizar README;
- executar auditoria final.

## Busca final

Procurar referências residuais a:

```text
QDRANT_PATH
QdrantClient(path
AI_CHUNKING
semantic_chunking
precomputed_chunks
```

e outras APIs removidas.

---

# Ordem de implementação recomendada

A sequência recomendada é:

```text
FASE 0
  ↓
FASE 1 — Qdrant Server na avaliação
  ↓
FASE 2 — regime documental
  ↓
FASE 3 — alterações legislativas
  ↓
FASE 5 — limite de tokens
  ↓
FASE 11 — fixtures reais
  ↓
FASE 12 — avaliação por dispositivo
  ↓
FASE 13 — E2E
  ↓
FASE 14 — CI
  ↓
FASE 4 — AST formal
  ↓
FASE 6 — espaçamento de Art.
  ↓
FASE 7 — anexos
  ↓
FASE 8 — OCR/PDF
  ↓
FASE 9 — política histórica
  ↓
FASE 10 — contexto obrigatório
  ↓
FASE 15 — manifest
  ↓
FASE 16 — limpeza
```

A razão de colocar fixtures reais e E2E antes da limpeza final é simples: eles devem validar a arquitetura enquanto ela ainda está sendo endurecida.

---

# Definition of Done

O projeto só deve ser considerado concluído quando:

```text
[ ] evaluation.py usa Qdrant Server
[ ] não existe QDRANT_PATH funcional
[ ] regime documental não depende de citações externas
[ ] cited_regimes é separado de document_regime
[ ] alterações múltiplas preservam todos os dispositivos
[ ] alteração não gera falso artigo irmão
[ ] dispositivos podem ser artigo/parágrafo/inciso/alínea/item
[ ] limite de tokens é uma invariável de saída
[ ] source_text nunca é truncado silenciosamente
[ ] Art. sem espaço é tratado
[ ] anexos possuem identidade estrutural própria
[ ] OCR mantém offsets verificáveis
[ ] consultas históricas não são confundidas com comparação
[ ] contexto obrigatório não expulsa evidência principal
[ ] existem fixtures de legislação real
[ ] avaliação mede artigo e dispositivo
[ ] existe E2E completo até Qdrant
[ ] CI cobre alterações do núcleo jurídico
[ ] manifest força reindexação quando a estrutura muda
[ ] pytest verde
[ ] evidence gate verde
[ ] smoke jurídico verde
[ ] E2E verde
```

---

# Resultado esperado

Depois dessas fases, a arquitetura deixa de ser apenas um **chunker heurístico endurecido** e passa a ter uma separação clara:

```text
FONTE
  ↓
EXTRAÇÃO
  ↓
NORMALIZAÇÃO
  ↓
AST JURÍDICO
  ↓
DISPOSITIVOS
  ↓
CHUNKS DE RECUPERAÇÃO
  ↓
EMBEDDINGS
  ↓
QDRANT SERVER
  ↓
RETRIEVAL
  ↓
RERANKING
  ↓
CONTEXTO
  ↓
EVIDENCE GATE
```

A propriedade mais importante é:

> **A estrutura jurídica original é a fonte de verdade; o chunking é apenas uma representação de recuperação, nunca a autoridade sobre o texto legal.**
