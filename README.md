# RAG de Licitações

RAG híbrido para leis, regulamentos, editais, minutas e jurisprudência de licitações, com busca semântica + lexical, RRF, reranking e LLM intercambiável.

O LLM é desacoplado do índice: trocar Qwen, Gemma, Llama, Gemini ou qualquer endpoint OpenAI-compatible não exige reindexação. Já mudanças em embedding, BM25, reranker, chunking ou esquema do payload exigem reindexação e são detectadas por `db/index_manifest.json`.

## Pipeline

```text
PDF -> extração por página -> metadados -> chunking estrutural -> dense + BM25 -> Qdrant
                                                           -> RRF -> reranker -> diversidade
                                                           -> orçamento de contexto -> LLM
```

### Estrutura jurídica do chunk

Legislação, súmulas e outros documentos estruturados são divididos por unidade jurídica (`artigo`, `sumula`, etc.) antes do split por tamanho. Cada fragmento mantém `unit_id`, `unit_ref`, `chunk_index`, `page` e `page_end`.

Unidades longas **não** repetem o texto integral em todos os vetores. Isso reduz drasticamente o tamanho do payload e impede que a mesma unidade consuma o orçamento de contexto várias vezes.

## Metadados e hierarquia de fontes

Além de `municipio`, `modalidade`, `ano`, `processo` e `tipo`, o índice suporta:

- `jurisdicao`, `esfera`, `orgao`, `tribunal`
- `tipo_documento`, `source_role`, `status`
- `data_versao`, `data_publicacao`, `data_vigencia`
- `revogado`, `norma_alteradora`, `fonte_oficial`, `fonte_host`

Documentos importantes devem ter um sidecar JSON com o mesmo nome do PDF. O sidecar prevalece sobre a heurística automática.

Exemplo:

```json
{
  "jurisdicao": "estadual_sp",
  "esfera": "estadual",
  "orgao": "Estado de São Paulo",
  "tipo_documento": "decreto",
  "source_role": "norma",
  "status": "vigente",
  "data_publicacao": "2023-06-30",
  "data_vigencia": "2023-07-01",
  "fonte_oficial": "https://www.al.sp.gov.br/"
}
```

Filtros continuam no formato:

```text
@municipio=Urânia @ano=2026 qual o prazo de entrega?
@jurisdicao=estadual_sp @tipo_documento=decreto quais regras se aplicam ao ETP?
@status=vigente @source_role=norma qual é a regra aplicável?
```

## Camada de autoridade recomendada

1. **Norma vigente**: Constituição, lei, decreto, resolução, portaria e atos normativos aplicáveis.
2. **Jurisprudência/controle**: STF, STJ, TCESP, TCU etc., sempre identificados como decisões/entendimentos.
3. **Orientação oficial**: AGU, Compras.gov, Compras SP, manuais e guias.
4. **Doutrina**: autores e obras especializadas, sempre como fonte secundária.

O prompt exige marcadores `[F#]` para que a resposta possa apontar para os trechos efetivamente recuperados.

## Conteúdo prioritário para São Paulo

O Portal de Compras SP informa, com estágio atualizado em 08/07/2026, os principais regulamentos estaduais da Lei 14.133/2021, entre eles:

- Decreto 67.608/2023 - transição e implantação;
- Decreto 67.689/2023 - plano de contratações anual;
- Decreto 67.888/2023 - pesquisa/estimativa de valor;
- Decreto 68.017/2023 - estudo técnico preliminar;
- Decreto 68.021/2023 - catálogo eletrônico e padronização;
- Decreto 68.185/2023 - termo de referência;
- Decreto 68.220/2023 - agentes públicos, gestão e fiscalização;
- Decreto 68.304/2024 - contratação direta eletrônica;
- Decreto 68.422/2024 - leilão eletrônico.

Itens ainda em elaboração não devem entrar no acervo como norma vigente.

O acervo também deve cobrir atos recentes da Secretaria de Gestão e Governo Digital, deliberações do TCESP e os modelos padronizados do Compras SP.

## Conteúdo federal complementar

Priorize fontes oficiais para:

- Lei 14.133/2021 e legislação correlata;
- Constituição Federal;
- Guia Nacional de Contratações Sustentáveis - 8ª edição;
- critérios ambientais, acessibilidade, resíduos e logística reversa;
- obras e serviços de engenharia, orçamento, fiscalização, medição e riscos;
- contratação de TIC;
- contratação direta, pregão, concorrência, credenciamento e leilão;
- modelos e instrumentos de padronização da AGU;
- jurisprudência do TCU/STJ e material do TCESP.

## Doutrina

A doutrina de Marçal Justen Filho é relevante para interpretação sistemática da Lei 14.133/2021, mas as obras comerciais protegidas por direitos autorais **não devem ser copiadas integralmente para o repositório** sem licença. Neste acervo foi incluído um mapa temático de uso doutrinário e fontes públicas, não a reprodução do livro.

## Hardware e modelos locais

O pipeline de recuperação é independente do LLM. Em uma RTX 5060 Ti 16 GB, a estratégia recomendada é manter o índice e os modelos de recuperação separados do gerador. O LLM pode rodar via Ollama, llama.cpp/vLLM através de endpoint OpenAI-compatible ou outro adapter.

Para usar CUDA no FastEmbed, instale o backend GPU apropriado e configure:

```text
RAG_FASTEMBED_PROVIDERS=CUDAExecutionProvider
```

Sem essa variável, o backend de recuperação permanece no comportamento padrão.

O embedding atual é `intfloat/multilingual-e5-large`. As consultas usam o prefixo `query:` e os documentos `passage:`, como exigido pelo modelo.

## Instalação

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python ingest.py
```

No Windows PowerShell, use `venv\\Scripts\\activate`.

PDFs escaneados podem produzir pouco texto com `pypdf`; o ingest avisa quando isso acontece. OCR deve ser tratado como etapa própria antes da indexação.

## Reindexação

Ao alterar qualquer componente do índice:

```bash
rm -rf db/qdrant db/index_manifest.json
python ingest.py
```

Trocar somente o LLM não exige reindexação.

## PDFs de apoio adicionados em 26/08/2026

- `SP_Regulamentacao_Lei_14133_26082026.pdf`
- `Contratacoes_Sustentaveis_GNCS_26082026.pdf`
- `Obras_Servicos_Engenharia_Contratacoes_26082026.pdf`
- `Doutrina_Jurisprudencia_Fontes_Publicas_26082026.pdf`

Os quatro são dossiês de apoio produzidos a partir de fontes públicas consultadas. Para uso forense/administrativo, o acervo principal deve continuar priorizando a versão oficial integral e vigente de cada norma ou documento.
