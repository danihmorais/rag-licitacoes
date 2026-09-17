from __future__ import annotations

try:
    from scripts.sources import _federal, _sp
except ModuleNotFoundError:
    from sources import _federal, _sp


PUBLIC_LAW_SOURCES = [
    _federal("pl-camara-federal", "Câmara — Legislação Federal Informatizada", "https://www25.senado.leg.br/web/atividade/legislacao/legislacao-federal", tipo_documento="portal_oficial", source_role="descoberta_legislativa", authority_level=3),
    _federal("pl-lexml", "LexML Brasil — legislação e jurisprudência", "https://www.lexml.gov.br/", tipo_documento="portal_oficial", source_role="descoberta_legislativa", authority_level=4),
    _federal("pl-leis-2026", "Planalto — Leis Ordinárias de 2026", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/lei/_leis2026.htm", tipo_documento="indice_legislacao", source_role="descoberta_legislativa", authority_level=2, follow_links=True, follow_patterns=(r"administra[cç][aã]o|p[uú]blic|tribut|finan|or[cç]ament|licita|contrat|servidor|sa[uú]de|educa[cç][aã]o|assist[eê]ncia|ambient|urban|saneamento|transporte|mobilidade|patrim[oô]nio|corrup[cç][aã]o|transpar[eê]ncia|dados|digital|eleitoral|munic[ií]pi|estado|federa[cç][aã]o|controle|tribunal|seguran[cç]a|defesa civil|ag[eê]ncia|regula[cç][aã]o|energia|concess[aã]o|permiss[aã]o|cons[oó]rcio|conv[eê]nio|educa[cç][aã]o|cultura|turismo|agricultura|meio ambiente",), max_follow=250),
    _federal("pl-leis-2025", "Planalto — Leis Ordinárias de 2025", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/_leis2025.htm", tipo_documento="indice_legislacao", source_role="descoberta_legislativa", authority_level=2, follow_links=True, follow_patterns=(r"administra[cç][aã]o|p[uú]blic|tribut|finan|or[cç]ament|licita|contrat|servidor|sa[uú]de|educa[cç][aã]o|assist[eê]ncia|ambient|urban|saneamento|transporte|mobilidade|patrim[oô]nio|corrup[cç][aã]o|transpar[eê]ncia|dados|digital|eleitoral|munic[ií]pi|estado|federa[cç][aã]o|controle|tribunal|seguran[cç]a|defesa civil|ag[eê]ncia|regula[cç][aã]o|energia|concess[aã]o|permiss[aã]o|cons[oó]rcio|conv[eê]nio|educa[cç][aã]o|cultura|turismo|agricultura|meio ambiente",), max_follow=250),
    _federal("pl-lc-atualizadas", "Planalto — quadro de Leis Complementares", "https://www.planalto.gov.br/ccivil_03/leis/lcp/quadro_lcp.htm", tipo_documento="indice_legislacao", source_role="descoberta_legislativa", authority_level=2, follow_links=True, follow_patterns=(r"tribut|finan|or[cç]ament|administra[cç][aã]o|p[uú]blic|munic[ií]pi|estado|federa[cç][aã]o|sa[uú]de|educa[cç][aã]o|responsabilidade|fiscal|saneamento|cons[oó]rcio|transfer[eê]ncia|previd|eleitoral|ambient|urban",), max_follow=180),
    _federal("pl-decretos-2026", "Planalto — Decretos de 2026", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/decreto/_decretos2026.htm", tipo_documento="indice_regulamentacao", source_role="descoberta_legislativa", authority_level=2, follow_links=True, follow_patterns=(r"administra[cç][aã]o|p[uú]blic|tribut|finan|or[cç]ament|licita|contrat|servidor|sa[uú]de|educa[cç][aã]o|assist[eê]ncia|ambient|urban|saneamento|transporte|mobilidade|patrim[oô]nio|transpar[eê]ncia|dados|digital|munic[ií]pi|estado|federa[cç][aã]o|controle|conv[eê]nio|regula[cç][aã]o|concess[aã]o|defesa civil",), max_follow=220),

    _federal("pl-cp5212", "Código de Processo Civil — Lei nº 13.105/2015", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", ramo_direito="Processual Público"),
    _federal("pl-ms12016", "Lei nº 12.016/2009 — Mandado de Segurança", "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2009/lei/l12016.htm", ramo_direito="Processual Público"),
    _federal("pl-acao-popular4717", "Lei nº 4.717/1965 — Ação Popular", "https://www.planalto.gov.br/ccivil_03/leis/l4717.htm", ramo_direito="Processual Público"),
    _federal("pl-acp7347", "Lei nº 7.347/1985 — Ação Civil Pública", "https://www.planalto.gov.br/ccivil_03/leis/l7347orig.htm", ramo_direito="Processual Público"),
    _federal("pl-habeasdata9507", "Lei nº 9.507/1997 — Habeas Data", "https://www.planalto.gov.br/ccivil_03/leis/l9507.htm", ramo_direito="Processual Público"),
    _federal("pl-tutelas8437", "Lei nº 8.437/1992 — medidas cautelares contra o Poder Público", "https://www.planalto.gov.br/ccivil_03/leis/l8437.htm", ramo_direito="Processual Público"),
    _federal("pl-9494", "Lei nº 9.494/1997 — tutela contra atos do Poder Público", "https://www.planalto.gov.br/ccivil_03/leis/l9494.htm", ramo_direito="Processual Público"),
    _federal("pl-9868", "Lei nº 9.868/1999 — controle concentrado de constitucionalidade", "https://www.planalto.gov.br/ccivil_03/leis/l9868.htm", ramo_direito="Constitucional"),
    _federal("pl-9882", "Lei nº 9.882/1999 — ADPF", "https://www.planalto.gov.br/ccivil_03/leis/l9882.htm", ramo_direito="Constitucional"),
    _federal("pl-13300", "Lei nº 13.300/2016 — Mandado de Injunção", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2016/lei/l13300.htm", ramo_direito="Constitucional"),
    _federal("pl-8625", "Lei nº 8.625/1993 — Lei Orgânica Nacional do Ministério Público", "https://www.planalto.gov.br/ccivil_03/leis/l8625.htm", ramo_direito="Instituições Públicas"),
    _federal("pl-lc75", "Lei Complementar nº 75/1993 — Ministério Público da União", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp75.htm", tipo_documento="lei_complementar", ramo_direito="Instituições Públicas"),
    _federal("pl-lc80", "Lei Complementar nº 80/1994 — Defensoria Pública", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp80.htm", tipo_documento="lei_complementar", ramo_direito="Instituições Públicas"),

    _federal("pl-8112", "Lei nº 8.112/1990 — regime jurídico dos servidores públicos federais", "https://www.planalto.gov.br/ccivil_03/leis/l8112compilado.htm", ramo_direito="Pessoal e Servidores"),
    _federal("pl-8745", "Lei nº 8.745/1993 — contratação temporária de interesse público", "https://www.planalto.gov.br/ccivil_03/leis/l8745cons.htm", ramo_direito="Pessoal e Servidores"),
    _federal("pl-13869", "Lei nº 13.869/2019 — abuso de autoridade", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2019/lei/l13869.htm", ramo_direito="Responsabilização Pública"),
    _federal("pl-1079", "Lei nº 1.079/1950 — crimes de responsabilidade", "https://www.planalto.gov.br/ccivil_03/leis/l1079.htm", ramo_direito="Responsabilização Pública"),
    _federal("pl-dl201", "Decreto-Lei nº 201/1967 — responsabilidade de prefeitos e vereadores", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del0201.htm", tipo_documento="decreto_lei", ramo_direito="Responsabilização Pública"),
    _federal("pl-cp2848", "Decreto-Lei nº 2.848/1940 — Código Penal", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm", tipo_documento="codigo", ramo_direito="Direito Penal Público"),
    _federal("pl-9605", "Lei nº 9.605/1998 — Crimes Ambientais", "https://www.planalto.gov.br/ccivil_03/leis/l9605.htm", ramo_direito="Direito Penal Público"),

    _federal("pl-5172", "Lei nº 5.172/1966 — Código Tributário Nacional", "https://www.planalto.gov.br/ccivil_03/leis/l5172compilado.htm", ramo_direito="Tributário"),
    _federal("pl-6830", "Lei nº 6.830/1980 — Execução Fiscal", "https://www.planalto.gov.br/ccivil_03/leis/l6830.htm", ramo_direito="Tributário"),
    _federal("pl-lcp87", "Lei Complementar nº 87/1996 — ICMS", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp87.htm", tipo_documento="lei_complementar", ramo_direito="Tributário"),
    _federal("pl-lcp116", "Lei Complementar nº 116/2003 — ISS", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp116.htm", tipo_documento="lei_complementar", ramo_direito="Tributário"),
    _federal("pl-lcp63", "Lei Complementar nº 63/1990 — distribuição do ICMS aos Municípios", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp63.htm", tipo_documento="lei_complementar", ramo_direito="Tributário"),
    _federal("pl-lcp214", "Lei Complementar nº 214/2025 — IBS, CBS e Imposto Seletivo", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214compilado.htm", tipo_documento="lei_complementar", ramo_direito="Tributário"),
    _federal("pl-lcp227", "Lei Complementar nº 227/2026 — CGIBS e processo administrativo do IBS", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp227.htm", tipo_documento="lei_complementar", ramo_direito="Tributário"),
    _federal("pl-lcp141", "Lei Complementar nº 141/2012 — financiamento e aplicação mínima em saúde", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp141.htm", tipo_documento="lei_complementar", ramo_direito="Financeiro e Saúde Pública"),

    _federal("pl-12608", "Lei nº 12.608/2012 — Política Nacional de Proteção e Defesa Civil", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12608.htm", ramo_direito="Defesa Civil"),
    _federal("pl-8159", "Lei nº 8.159/1991 — Política Nacional de Arquivos Públicos e Privados", "https://www.planalto.gov.br/ccivil_03/leis/l8159.htm", ramo_direito="Administração Pública"),
    _federal("pl-13726", "Lei nº 13.726/2018 — desburocratização e simplificação", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13726.htm", ramo_direito="Administração Pública"),
    _federal("pl-14063", "Lei nº 14.063/2020 — assinaturas eletrônicas em interações com entes públicos", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2020/lei/l14063.htm", ramo_direito="Governo Digital"),
    _federal("pl-13848", "Lei nº 13.848/2019 — agências reguladoras", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2019/lei/l13848.htm", ramo_direito="Regulação e Serviços Públicos"),
    _federal("pl-12529", "Lei nº 12.529/2011 — Sistema Brasileiro de Defesa da Concorrência", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12529.htm", ramo_direito="Regulação e Direito Econômico"),
    _federal("pl-13874", "Lei nº 13.874/2019 — Declaração de Direitos de Liberdade Econômica", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2019/lei/l13874.htm", ramo_direito="Regulação e Direito Econômico"),
    _federal("pl-11107", "Lei nº 11.107/2005 — consórcios públicos", "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2005/lei/l11107.htm", ramo_direito="Federalismo e Cooperação"),
    _federal("pl-9790", "Lei nº 9.790/1999 — OSCIP", "https://www.planalto.gov.br/ccivil_03/leis/l9790.htm", ramo_direito="Terceiro Setor"),

    _federal("pl-8080", "Lei nº 8.080/1990 — Sistema Único de Saúde", "https://www.planalto.gov.br/ccivil_03/leis/l8080.htm", ramo_direito="Saúde Pública"),
    _federal("pl-8142", "Lei nº 8.142/1990 — participação social e transferências na saúde", "https://www.planalto.gov.br/ccivil_03/leis/l8142.htm", ramo_direito="Saúde Pública"),
    _federal("pl-12401", "Lei nº 12.401/2011 — assistência terapêutica e incorporação de tecnologias no SUS", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12401.htm", ramo_direito="Saúde Pública"),
    _federal("pl-9394", "Lei nº 9.394/1996 — Lei de Diretrizes e Bases da Educação", "https://www.planalto.gov.br/ccivil_03/leis/l9394.htm", ramo_direito="Educação Pública"),
    _federal("pl-14113", "Lei nº 14.113/2020 — Fundeb", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2020/lei/l14113.htm", ramo_direito="Educação Pública"),
    _federal("pl-11738", "Lei nº 11.738/2008 — piso salarial profissional do magistério", "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2008/lei/l11738.htm", ramo_direito="Educação Pública"),
    _federal("pl-8742", "Lei nº 8.742/1993 — Lei Orgânica da Assistência Social", "https://www.planalto.gov.br/ccivil_03/leis/l8742compilado.htm", ramo_direito="Assistência Social"),
    _federal("pl-8069", "Lei nº 8.069/1990 — Estatuto da Criança e do Adolescente", "https://www.planalto.gov.br/ccivil_03/leis/l8069.htm", ramo_direito="Direitos Sociais e Proteção"),
    _federal("pl-10741", "Lei nº 10.741/2003 — Estatuto da Pessoa Idosa", "https://www.planalto.gov.br/ccivil_03/leis/2003/l10.741.htm", ramo_direito="Direitos Sociais e Proteção"),
    _federal("pl-13146", "Lei nº 13.146/2015 — Lei Brasileira de Inclusão", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13146.htm", ramo_direito="Direitos Sociais e Proteção"),
    _federal("pl-10098", "Lei nº 10.098/2000 — acessibilidade", "https://www.planalto.gov.br/ccivil_03/leis/l10098.htm", ramo_direito="Direitos Sociais e Proteção"),

    _federal("pl-6938", "Lei nº 6.938/1981 — Política Nacional do Meio Ambiente", "https://www.planalto.gov.br/ccivil_03/leis/l6938compilada.htm", ramo_direito="Ambiental"),
    _federal("pl-12651", "Lei nº 12.651/2012 — Código Florestal", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12651.htm", ramo_direito="Ambiental"),
    _federal("pl-9433", "Lei nº 9.433/1997 — Política Nacional de Recursos Hídricos", "https://www.planalto.gov.br/ccivil_03/leis/l9433.htm", ramo_direito="Ambiental"),
    _federal("pl-9985", "Lei nº 9.985/2000 — Sistema Nacional de Unidades de Conservação", "https://www.planalto.gov.br/ccivil_03/leis/l9985.htm", ramo_direito="Ambiental"),
    _federal("pl-12305", "Lei nº 12.305/2010 — Política Nacional de Resíduos Sólidos", "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2010/lei/l12305.htm", ramo_direito="Ambiental"),
    _federal("pl-15190", "Lei nº 15.190/2025 — Lei Geral do Licenciamento Ambiental", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/l15190.htm", ramo_direito="Ambiental"),
    _federal("pl-6514", "Decreto nº 6.514/2008 — infrações e sanções administrativas ambientais", "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2008/decreto/d6514.htm", tipo_documento="decreto", ramo_direito="Ambiental"),

    _federal("pl-10257", "Lei nº 10.257/2001 — Estatuto da Cidade", "https://www.planalto.gov.br/ccivil_03/leis/leis_2001/l10257.htm", ramo_direito="Urbanístico"),
    _federal("pl-6766", "Lei nº 6.766/1979 — Parcelamento do Solo Urbano", "https://www.planalto.gov.br/ccivil_03/leis/l6766.htm", ramo_direito="Urbanístico"),
    _federal("pl-13465", "Lei nº 13.465/2017 — regularização fundiária urbana e rural", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2017/lei/l13465.htm", ramo_direito="Urbanístico"),
    _federal("pl-11445", "Lei nº 11.445/2007 — saneamento básico", "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2007/lei/l11445.htm", ramo_direito="Serviços Públicos"),
    _federal("pl-14026", "Lei nº 14.026/2020 — atualização do marco do saneamento", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2020/lei/l14026.htm", ramo_direito="Serviços Públicos"),
    _federal("pl-12587", "Lei nº 12.587/2012 — Política Nacional de Mobilidade Urbana", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12587.htm", ramo_direito="Serviços Públicos e Mobilidade"),
    _federal("pl-15432", "Lei nº 15.432/2026 — marco legal do transporte público coletivo urbano", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/lei/l15432.htm", ramo_direito="Serviços Públicos e Mobilidade"),
    _federal("pl-8987", "Lei nº 8.987/1995 — concessões e permissões de serviços públicos", "https://www.planalto.gov.br/ccivil_03/leis/l8987cons.htm", ramo_direito="Serviços Públicos"),
    _federal("pl-11079", "Lei nº 11.079/2004 — Parcerias Público-Privadas", "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l11079.htm", ramo_direito="Serviços Públicos"),

    _federal("pl-dl3365", "Decreto-Lei nº 3.365/1941 — desapropriação por utilidade pública", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del3365compilado.htm", tipo_documento="decreto_lei", ramo_direito="Patrimônio Público"),
    _federal("pl-dl25", "Decreto-Lei nº 25/1937 — patrimônio histórico e artístico nacional", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del0025.htm", tipo_documento="decreto_lei", ramo_direito="Patrimônio Público"),

    _federal("pl-4737", "Lei nº 4.737/1965 — Código Eleitoral", "https://www.planalto.gov.br/ccivil_03/leis/l4737compilado.htm", tipo_documento="codigo", ramo_direito="Eleitoral"),
    _federal("pl-9504", "Lei nº 9.504/1997 — normas para eleições", "https://www.planalto.gov.br/ccivil_03/leis/l9504.htm", ramo_direito="Eleitoral"),
    _federal("pl-lc64", "Lei Complementar nº 64/1990 — inelegibilidades", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp64.htm", tipo_documento="lei_complementar", ramo_direito="Eleitoral"),
    _federal("pl-lc135", "Lei Complementar nº 135/2010 — Lei da Ficha Limpa", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp135.htm", tipo_documento="lei_complementar", ramo_direito="Eleitoral"),

    _sp("sp-const1989", "Constituição do Estado de São Paulo de 1989", "https://www.al.sp.gov.br/repositorio/legislacao/constituicao/1989/original-constituicao-0-05.10.1989.html", tipo_documento="constituicao", ramo_direito="Constitucional"),
    _sp("sp-10177", "Lei Estadual nº 10.177/1998 — processo administrativo paulista", "https://www.al.sp.gov.br/repositorio/legislacao/lei/1998/lei-10177-30.12.1998.html", ramo_direito="Administrativo"),
    _sp("sp-10261", "Lei Estadual nº 10.261/1968 — Estatuto dos Funcionários Públicos Civis do Estado", "https://www.al.sp.gov.br/repositorio/legislacao/lei/1968/original-lei-10261-28.10.1968.html", ramo_direito="Pessoal e Servidores"),
    _sp("sp-lc709", "Lei Complementar Estadual nº 709/1993 — Lei Orgânica do TCESP", "https://www.al.sp.gov.br/repositorio/legislacao/lei.complementar/1993/lei.complementar-709-14.01.1993.html", tipo_documento="lei_complementar", ramo_direito="Controle Externo"),
    _sp("sp-tcesp-legislacao", "TCESP — legislação estadual e atos de controle", "https://www.tce.sp.gov.br/legislacao-estadual", tipo_documento="portal_oficial", source_role="controle_estadual", authority_level=3, follow_links=True, follow_patterns=(r"^https?://www\.al\.sp\.gov\.br/", r"\\.pdf(?:$|\\?)"), max_follow=80),
] 
