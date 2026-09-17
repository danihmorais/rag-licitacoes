# Reestruturação e expansão do corpus de Direito Público — 17/09/2026

## Objetivo

O corpus deixa de ser predominantemente orientado a licitações e contratos e passa a ter um núcleo geral de Direito Público brasileiro. O catálogo jurídico foi consolidado em um único módulo (`scripts/sources.py`), reduzindo duplicidade e pontos de manutenção. A ingestão também passou a tratar páginas de índice como fontes de descoberta, e não como evidência jurídica.

## Cobertura jurídica

A nova camada contempla fontes de referência para:

- Direito Constitucional e controle de constitucionalidade;
- Direito Administrativo, processo administrativo, atos administrativos e poder de polícia;
- servidores públicos e processo disciplinar;
- responsabilização pública, improbidade, anticorrupção e abuso de autoridade;
- Direito Processual aplicado ao Poder Público, incluindo mandado de segurança, ação popular, ação civil pública, habeas data e tutelas contra o Poder Público;
- Direito Financeiro e Orçamentário, incluindo LRF, orçamento público e transferências;
- Direito Tributário, incluindo CTN, execução fiscal, ISS, ICMS, repartição de receitas e Reforma Tributária;
- concessões, permissões, PPPs, agências reguladoras e serviços públicos;
- desapropriação, bens públicos e patrimônio público;
- Direito Urbanístico, Estatuto da Cidade, parcelamento e regularização fundiária;
- Direito Ambiental e licenciamento, sanções ambientais, resíduos, águas e unidades de conservação;
- Saúde Pública/SUS;
- Educação Pública/Fundeb e magistério;
- Assistência Social/SUAS/LOAS;
- proteção de crianças, adolescentes, pessoas idosas e pessoas com deficiência no âmbito das políticas públicas;
- transparência, acesso à informação, proteção de dados e governo digital;
- consórcios públicos, federalismo cooperativo e parcerias com o terceiro setor;
- defesa civil;
- legislação eleitoral básica, com a ressalva de que a coleta jurisprudencial eleitoral específica depende de um adaptador próprio para o TSE;
- legislação e controle do Estado de São Paulo, incluindo Constituição Estadual, processo administrativo estadual, regime de servidores e Lei Orgânica do TCESP.

## Atualização contínua

Foram adicionados índices oficiais do Planalto para leis e decretos recentes e um catálogo de descoberta legislativa. Esses índices servem para localizar atos novos e ampliar o corpus conforme a legislação pública evolui.

A legislação recente da Reforma Tributária também foi incorporada ao catálogo, com a LC nº 214/2025 e a LC nº 227/2026.

## Jurisprudência

As consultas-padrão do coletor deixaram de ser somente sobre licitação e contratos e passaram a cobrir também processo administrativo, servidores, responsabilidade civil do Estado, improbidade, controle externo, orçamento, tributação, serviços públicos, desapropriação, urbanismo, ambiental, SUS, educação, assistência social, LAI/LGPD e outros temas de Direito Público.

## Metadados

Os documentos da nova camada recebem o campo `ramo_direito` quando a fonte é cadastrada de forma explícita. O cache também preserva esse campo para facilitar classificação e auditoria do corpus.

## Reindexação

A expansão altera o conjunto de documentos disponível para recuperação. No servidor que executa o RAG, sincronize as fontes e refaça a indexação:

```bash
python scripts/sync_sources.py
python -m jurisprudencia.batch --limit 12
python ingest.py
```

Para uma coleta jurisprudencial mais ampla, o limite por consulta pode ser aumentado conforme a capacidade da máquina e o tempo aceitável de ingestão.

## Limite de escopo

“Todo o Direito Público” não significa que o repositório contenha literalmente toda a produção normativa brasileira. Leis municipais, estatutos locais, códigos tributários municipais, PPA/LDO/LOA, planos diretores, leis de zoneamento, posturas, cargos e salários, decretos municipais e atos normativos internos são altamente dependentes do ente federativo e precisam ser adicionados ao corpus correspondente.

A arquitetura passa a suportar essa expansão sem alterar o mecanismo central de ingestão e recuperação.
