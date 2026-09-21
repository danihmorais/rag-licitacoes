# Auditoria do RAG — 28/08/2026

## O que foi verificado

A estrutura atual foi revisada em relação a ingestão, recuperação híbrida, metadados, intercambialidade do LLM, sincronização de fontes e GitHub Actions. O histórico do repositório também foi consultado.

Os PDFs jurídicos versionados que existiam em commit anterior já foram removidos da `main`. Eles incluíam Constituição compilada, Lei 14.133, Decreto 12.807, material de contratações sustentáveis, material de Direito Administrativo/LINDB/Improbidade e material do TCESP. A estratégia atual é preferível: fontes oficiais são consultadas automaticamente e o cache fica fora do Git.

## Melhorias aplicadas

1. Correção da descoberta de PDFs: padrões antigos com `\\.pdf`/`\\?` eram normalizados antes da expressão regular ser compilada.
2. Limpeza segura de cache: documentos linkados que deixam de existir na página de origem são removidos somente depois de uma sincronização bem-sucedida daquela fonte; falha de rede preserva o cache anterior.
3. Corpus ampliado com alterações relevantes da Lei 14.133 e legislação transversal de Direito Administrativo, integridade, meio ambiente e contratos.
4. Portais oficiais de jurisprudência do TCU, STJ e STF foram catalogados para a próxima etapa.
5. `Lei 6.544/1989` paulista passou a ser tratada como `historico` no catálogo efetivo do sincronizador, evitando falsa indicação de que seja o regime geral atual.
6. Chunking passou a preservar uma unidade de artigo mesmo quando o documento contém apenas um artigo.
7. O prompt passou a distinguir explicitamente `historico`, além de `revogado` e `vacatio_legis`.
8. Esquema inicial de jurisprudência criado sem dependência do modelo de IA.
9. Testes adicionados para as novas fontes, artigo único e descoberta de PDF.

## Pontos ainda prioritários

### Temporalidade real

O cache atual privilegia a versão corrente de cada fonte. Para responder com segurança a perguntas históricas, a próxima evolução deve manter snapshots imutáveis por alteração/hash e relacionar norma alteradora com os dispositivos afetados.

### Recuperação por vizinhança jurídica

Para artigos longos, um único chunk pode não conter incisos/parágrafos necessários à interpretação. Uma etapa de expansão por `unit_id` e vizinhança de `chunk_index` pode melhorar a completude sem abandonar o reranker.

### OCR

PDF escaneado deve carregar `text_origin=native|ocr` e confiança da extração por página, evitando que texto OCR de baixa qualidade tenha o mesmo peso de texto nativo.

### Avaliação

Criar um conjunto de perguntas reais de licitação e medir recall@k, MRR/nDCG, cobertura das citações, acerto de jurisdição e acerto temporal antes de trocar embedding/reranker.

## Jurisprudência

A próxima etapa recomendada é o coletor estruturado TCESP + TCU + STJ + STF, conforme `docs/JURISPRUDENCIA_ROADMAP_28082026.md`.
