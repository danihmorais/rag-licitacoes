from __future__ import annotations

"""Catálogo de fontes oficiais priorizadas pelo RAG.

As fontes são deliberadamente compostas por legislação primária e por materiais
officiais de controle/orientação. Status e vigência são explícitos para permitir
consultas históricas sem contaminar a resposta sobre a regra atual.
"""


BASE = {
    "esfera": "federal",
    "jurisdicao": "federal",
    "orgao": "Legislação Federal",
    "source_role": "norma",
    "authority_level": 1,
    "status": "vigente",
}


def _federal(id_: str, title: str, url: str, *, tipo_documento: str = "lei", required: bool = False,
             follow_links: bool = False, follow_patterns: tuple[str, ...] = (), max_follow: int = 12,
             **extra):
    item = {**BASE, "id": id_, "title": title, "urls": [url], "tipo_documento": tipo_documento}
    if required:
        item["required"] = True
    if follow_links:
        item.update(follow_links=True, follow_patterns=list(follow_patterns), max_follow=max_follow)
    item.update(extra)
    return item


def _sp(id_: str, title: str, url: str, *, tipo_documento: str = "decreto", required: bool = False,
        source_role: str = "norma", authority_level: int = 1, follow_links: bool = False,
        follow_patterns: tuple[str, ...] = (), max_follow: int = 12, **extra):
    item = {
        "id": id_,
        "title": title,
        "urls": [url],
        "jurisdicao": "estadual_sp",
        "esfera": "estadual",
        "orgao": extra.pop("orgao", "Estado de São Paulo"),
        "tipo_documento": tipo_documento,
        "source_role": source_role,
        "authority_level": authority_level,
        "status": "vigente",
    }
    if required:
        item["required"] = True
    if follow_links:
        item.update(follow_links=True, follow_patterns=list(follow_patterns), max_follow=max_follow)
    item.update(extra)
    return item


SOURCES = [
    _federal("cf1988", "Constituição Federal de 1988", "https://www2.camara.leg.br/legin/fed/consti/1988/constituicao-1988-5-outubro-1988-322142-normaatualizada-pl.html", tipo_documento="constituicao", required=True),
    _federal("lei14133", "Lei nº 14.133/2021 — Licitações e Contratos Administrativos", "https://www2.camara.leg.br/legin/fed/lei/2021/lei-14133-1-abril-2021-791222-normaatualizada-pl.html", required=True),
    _federal("decreto12807", "Decreto nº 12.807/2025 — valores da Lei nº 14.133/2021", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/d12807.htm", tipo_documento="decreto", required=True),
    _federal("lindb", "Decreto-Lei nº 4.657/1942 — LINDB", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del4657compilado.htm", tipo_documento="decreto_lei", required=True),
    _federal("del200", "Decreto-Lei nº 200/1967 — Organização da Administração Federal", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del0200.htm", tipo_documento="decreto_lei"),
    _federal("lei9784", "Lei nº 9.784/1999 — Processo Administrativo Federal", "https://www2.camara.leg.br/legin/fed/lei/1999/lei-9784-29-janeiro-1999-322239-normaatualizada-pl.html", required=True),
    _federal("lei8429", "Lei nº 8.429/1992 — Improbidade Administrativa", "https://www2.camara.leg.br/legin/fed/lei/1992/lei-8429-2-junho-1992-357452-normaatualizada-pl.html"),
    _federal("lei12846", "Lei nº 12.846/2013 — Lei Anticorrupção", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12846.htm"),
    _federal("decreto11129", "Decreto nº 11.129/2022 — regulamento da Lei Anticorrupção", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/decreto/d11129.htm", tipo_documento="decreto"),
    _federal("lei12527", "Lei nº 12.527/2011 — Lei de Acesso à Informação", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm"),
    _federal("lei13709", "Lei nº 13.709/2018 — LGPD", "https://www2.camara.leg.br/legin/fed/lei/2018/lei-13709-14-agosto-2018-787077-normaatualizada-pl.html"),
    _federal("lei13303", "Lei nº 13.303/2016 — Empresas Estatais", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2016/lei/l13303.htm"),
    _federal("lei8987", "Lei nº 8.987/1995 — Concessões e Permissões", "https://www.planalto.gov.br/ccivil_03/leis/l8987cons.htm"),
    _federal("lei11079", "Lei nº 11.079/2004 — Parcerias Público-Privadas", "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l11079.htm"),
    _federal("lrf", "Lei Complementar nº 101/2000 — Responsabilidade Fiscal", "https://www2.camara.leg.br/legin/fed/leicom/2000/leicomplementar-101-4-maio-2000-351480-normaatualizada-pl.html", tipo_documento="lei_complementar"),
    _federal("lei4320", "Lei nº 4.320/1964 — Direito Financeiro", "https://www.planalto.gov.br/ccivil_03/leis/l4320compilado.htm"),
    _federal("lc123", "Lei Complementar nº 123/2006 — tratamento favorecido para ME/EPP", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm", tipo_documento="lei_complementar", required=True),
    _federal("lei13019", "Lei nº 13.019/2014 — parcerias com organizações da sociedade civil", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l13019compilado.htm"),
    _federal("lei13460", "Lei nº 13.460/2017 — direitos do usuário de serviço público", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2017/lei/l13460.htm"),
    _federal("lei14129", "Lei nº 14.129/2021 — Governo Digital", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14129.htm"),
    _federal("decreto10947", "Decreto nº 10.947/2022 — Plano de Contratações Anual e PGC", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/decreto/d10947.htm", tipo_documento="decreto", required=True),
    _federal("decreto11246", "Decreto nº 11.246/2022 — agente de contratação, gestores e fiscais", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/decreto/d11246.htm", tipo_documento="decreto", required=True),
    _federal("decreto11462", "Decreto nº 11.462/2023 — Sistema de Registro de Preços", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/decreto/d11462.htm", tipo_documento="decreto", required=True),
    _federal("decreto11878", "Decreto nº 11.878/2024 — credenciamento", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2024/decreto/d11878.htm", tipo_documento="decreto", required=True),
    _federal("in67", "IN SEGES/ME nº 67/2021 — dispensa eletrônica", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-me-no-67-de-8-de-julho-de-2021", tipo_documento="instrucao_normativa"),
    _federal("in65", "IN SEGES/ME nº 65/2021 — pesquisa de preços", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-me-no-65-de-7-de-julho-de-2021", tipo_documento="instrucao_normativa", required=True),
    _federal("in58", "IN SEGES nº 58/2022 — Estudo Técnico Preliminar", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-me-no-58-de-8-de-agosto-de-2022", tipo_documento="instrucao_normativa", required=True),
    _federal("in81", "IN SEGES/ME nº 81/2022 — Termo de Referência", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-me-no-81-de-25-de-novembro-de-2022", tipo_documento="instrucao_normativa", required=True),
    _federal("in73", "IN SEGES/ME nº 73/2022 — critérios eletrônicos de julgamento", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-me-no-73-de-30-de-setembro-de-2022", tipo_documento="instrucao_normativa"),
    _federal("in512", "IN SEGES/MGI nº 512/2025 — diálogo competitivo (texto atualizado)", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-mgi-no-512-de-3-de-dezembro-de-2025", tipo_documento="instrucao_normativa", status="vacatio_legis", effective_from="2026-11-30"),
    _federal("in129", "IN SEGES/MGI nº 129/2026 — posterga a vigência da IN 512/2025", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-mgi-no-129-de-30-de-marco-de-2026", tipo_documento="instrucao_normativa", required=True),
    _federal("lei6938", "Lei nº 6.938/1981 — Política Nacional do Meio Ambiente", "https://www.planalto.gov.br/ccivil_03/leis/l6938compilada.htm"),
    _federal("lei12305", "Lei nº 12.305/2010 — Política Nacional de Resíduos Sólidos", "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2010/lei/l12305.htm"),
    _federal("lei9605", "Lei nº 9.605/1998 — Crimes Ambientais", "https://www.planalto.gov.br/ccivil_03/leis/l9605.htm"),
    _federal("lei13146", "Lei nº 13.146/2015 — Estatuto da Pessoa com Deficiência", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13146.htm"),
    _federal("lei8666", "Lei nº 8.666/1993 — regime histórico de licitações", "https://www.planalto.gov.br/ccivil_03/leis/l8666cons.htm", status="revogado", revogado=True, effective_to="2023-12-30"),
    _federal("lei10520", "Lei nº 10.520/2002 — pregão (regime histórico)", "https://www.planalto.gov.br/ccivil_03/leis/2002/l10520.htm", status="revogado", revogado=True, effective_to="2023-12-30"),
    _federal("lei12462", "Lei nº 12.462/2011 — RDC (regime histórico)", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12462.htm", status="revogado", revogado=True, effective_to="2023-12-30"),
    _federal("pncp", "PNCP — legislação e atos oficiais", "https://www.gov.br/pncp/pt-br/pncp/legislacao/leis", tipo_documento="portal_oficial", source_role="orientacao_oficial", authority_level=3, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=20),
    _federal("compras", "Compras.gov.br — legislação de contratações públicas", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao", tipo_documento="portal_oficial", source_role="orientacao_oficial", authority_level=3, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=30),
    _federal("compras-in", "Compras.gov.br — Instruções Normativas", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas", tipo_documento="instrucao_normativa", source_role="norma", authority_level=1, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=60),
    _federal("agu", "AGU — modelos de Licitações e Contratos da Lei nº 14.133/2021", "https://www.gov.br/agu/pt-br/composicao/cgu/cgu/modelos/licitacoesecontratos/14133", tipo_documento="modelo_orientacao", source_role="orientacao_oficial", authority_level=3, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=50),
    _federal("tcu", "TCU — Licitações e Contratos: orientações e jurisprudência", "https://portal.tcu.gov.br/publicacoes-institucionais/cartilha-manual-ou-tutorial/licitacoes-e", tipo_documento="manual", source_role="jurisprudencia_controle", authority_level=2, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=20),
    _sp("tcesp", "TCESP — Súmulas e Boletim de Jurisprudência", "https://www.tce.sp.gov.br/boletim-de-jurisprudencia/sumulas", tipo_documento="sumula", source_role="jurisprudencia_controle", authority_level=2, required=True, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=20),
    _sp("tcesp-srp", "TCESP — Deliberação 2026 sobre Sistema de Registro de Preços e adesão", "https://tce.sp.gov.br/legislacao/deliberacao/dispoe-sobre-diretrizes-e-procedimentos-serem-observados-pelos-orgaos-e", tipo_documento="deliberacao", source_role="jurisprudencia_controle", authority_level=2, required=True),
    _sp("sp-const", "Constituição do Estado de São Paulo — texto atualizado", "https://www.al.sp.gov.br/repositorio/legislacao/constituicao/1989/compilacao-constituicao-0-05.10.1989.html", tipo_documento="constituicao_estadual", required=True),
    _sp("sp-lei10177", "Lei SP nº 10.177/1998 — Processo Administrativo", "https://www.al.sp.gov.br/repositorio/legislacao/lei/1998/compilacao-lei-10177-30.12.1998.html", tipo_documento="lei", required=True),
    _sp("sp-lc709", "LC SP nº 709/1993 — Lei Orgânica do TCESP", "https://www.al.sp.gov.br/norma/?id=16279", tipo_documento="lei_complementar", required=True, orgao="ALESP/TCESP"),
    _sp("sp-lei6544", "Lei SP nº 6.544/1989 — licitações e contratos", "https://www.al.sp.gov.br/repositorio/legislacao/lei/1989/compilacao-lei-6544-22.11.1989.html", tipo_documento="lei"),
    _sp("sp-transicao", "Decreto SP nº 67.608/2023 — transição para a Lei nº 14.133", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67608-27.03.2023.html"),
    _sp("sp-pca", "Decreto SP nº 67.689/2023 — Plano de Contratações Anual", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67689-03.05.2023.html", required=True),
    _sp("sp-transicao-67885", "Decreto SP nº 67.885/2023 — regime de transição", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67885-15.08.2023.html"),
    _sp("sp-precos", "Decreto SP nº 67.888/2023 — pesquisa de preços", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67888-17.08.2023.html", required=True),
    _sp("sp-luxo", "Decreto SP nº 67.985/2023 — bens e serviços de luxo", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67985-27.09.2023.html"),
    _sp("sp-etp", "Decreto SP nº 68.017/2023 — Estudo Técnico Preliminar", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68017-11.10.2023.html", required=True),
    _sp("sp-catalogo", "Decreto SP nº 68.021/2023 — catálogo eletrônico de padronização", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68021-11.10.2023.html"),
    _sp("sp-tr", "Decreto SP nº 68.185/2023 — Termo de Referência", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68185-11.12.2023.html", required=True),
    _sp("sp-agentes", "Decreto SP nº 68.220/2023 — agentes, gestores e fiscais", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68220-15.12.2023.html", required=True),
    _sp("sp-direta", "Decreto SP nº 68.304/2024 — contratação direta eletrônica", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2024/decreto-68304-09.01.2024.html", required=True),
    _sp("sp-leilao", "Decreto SP nº 68.422/2024 — leilão eletrônico", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2024/decreto-68422-02.04.2024.html", required=True),
    _sp("sp-audesp", "Decreto SP nº 69.233/2024 — compartilhamento de dados de licitações com o AUDESP", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2024/decreto-69233-23.12.2024.html", required=True),
    _sp("sp-par", "Decreto SP nº 69.588/2025 — responsabilização de pessoas jurídicas", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2025/decreto-69588-09.06.2025.html"),
    _sp("sp-integridade", "Decreto SP nº 69.861/2025 — programas de integridade", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2025/decreto-69861-11.09.2025.html"),
    _sp("sp-marketplace", "Resolução SGGD nº 34/2026 — Marketplace.SP e credenciamento", "https://compras.sp.gov.br/resolucao-sggd-no-34-de-29-de-julho-de-2026/", tipo_documento="resolucao", required=True),
    _sp("sp-res29", "Resolução SGGD nº 29/2026 — tabela de preços de insumos de informática PRODESP", "https://compras.sp.gov.br/resolucao-sggd-no-29-de-19-de-junho-de-2026/", tipo_documento="resolucao"),
    _sp("sp-res28", "Resolução SGGD nº 28/2026 — competência da Central de Compras para TAG", "https://compras.sp.gov.br/resolucao-sggd-no-28-de-16-de-junho-de-2026/", tipo_documento="resolucao"),
    _sp("sp-compras", "Compras SP — legislação e regulamentação", "https://compras.sp.gov.br/legislacao/", tipo_documento="portal_oficial", source_role="orientacao_oficial", authority_level=3, required=True, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=60),
]

SOURCE_BY_ID = {item["id"]: item for item in SOURCES}
