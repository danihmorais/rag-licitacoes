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


def _normative_rank(source_role: str, tipo_documento: str | None) -> int | None:
    if source_role != "norma":
        return None
    tipo = (tipo_documento or "").casefold()
    if "constituicao" in tipo:
        return 1
    if tipo in {"lei", "lei_complementar", "lei_ordinaria", "decreto_lei", "emenda_constitucional"} or tipo.startswith("lei_"):
        return 2
    if tipo == "decreto" or tipo.startswith("decreto_"):
        return 3
    if tipo in {"instrucao_normativa", "portaria", "resolucao", "deliberacao", "ato_normativo"}:
        return 4
    return 4


def _federal(id_: str, title: str, url: str, *, tipo_documento: str = "lei", required: bool = False,
             follow_links: bool = False, follow_patterns: tuple[str, ...] = (), max_follow: int = 12,
             **extra):
    item = {**BASE, "id": id_, "title": title, "urls": [url], "tipo_documento": tipo_documento}
    if required:
        item["required"] = True
    if follow_links:
        item.update(follow_links=True, follow_patterns=list(follow_patterns), max_follow=max_follow)
    item.update(extra)
    if "normative_rank" not in item:
        item["normative_rank"] = _normative_rank(item.get("source_role"), item.get("tipo_documento"))
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
    if "normative_rank" not in item:
        item["normative_rank"] = _normative_rank(item.get("source_role"), item.get("tipo_documento"))
    return item


def _municipal_sp(id_: str, title: str, url: str, *, tipo_documento: str = "decreto", required: bool = False,
                  source_role: str = "norma", authority_level: int = 1, follow_links: bool = False,
                  follow_patterns: tuple[str, ...] = (), max_follow: int = 12, **extra):
    item = {
        "id": id_,
        "title": title,
        "urls": [url],
        "jurisdicao": "municipal_sp",
        "esfera": "municipal",
        "orgao": extra.pop("orgao", "Município de São Paulo"),
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
    if "normative_rank" not in item:
        item["normative_rank"] = _normative_rank(item.get("source_role"), item.get("tipo_documento"))
    return item


SOURCES = [
    _federal("cf1988", "Constituição Federal de 1988", "https://www2.camara.leg.br/legin/fed/consti/1988/constituicao-1988-5-outubro-1988-322142-normaatualizada-pl.html", tipo_documento="constituicao", required=True, ramo_direito="Constitucional"),
    _federal("lei14133", "Lei nº 14.133/2021 — Licitações e Contratos Administrativos", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm", required=True, ramo_direito="Administrativo", fallback_urls=("https://www2.camara.leg.br/legin/fed/lei/2021/lei-14133-1-abril-2021-791222-normaatualizada-pl.html",)),
    _federal("decreto12807", "Decreto nº 12.807/2025 — valores da Lei nº 14.133/2021", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/d12807.htm", tipo_documento="decreto", required=True, fallback_urls=("https://www2.camara.leg.br/legin/fed/decret/2025/decreto-12807-29-dezembro-2025-798615-publicacaooriginal-177646-pe.html",)),
    _federal("lindb", "Decreto-Lei nº 4.657/1942 — LINDB", "https://www2.camara.leg.br/legin/fed/declei/1940-1949/decreto-lei-4657-4-setembro-1942-414605-normaatualizada-pe.html", tipo_documento="decreto_lei", required=True, fallback_urls=("https://www.planalto.gov.br/ccivil_03/decreto-lei/del4657compilado.htm",)),
    _federal("del200", "Decreto-Lei nº 200/1967 — Organização da Administração Federal", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del0200.htm", tipo_documento="decreto_lei"),
    _federal("lei9784", "Lei nº 9.784/1999 — Processo Administrativo Federal", "https://www2.camara.leg.br/legin/fed/lei/1999/lei-9784-29-janeiro-1999-322239-normaatualizada-pl.html", required=True),
    _federal("lei8429", "Lei nº 8.429/1992 — Improbidade Administrativa", "https://www2.camara.leg.br/legin/fed/lei/1992/lei-8429-2-junho-1992-357452-normaatualizada-pl.html"),
    _federal("lei12846", "Lei nº 12.846/2013 — Lei Anticorrupção", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12846.htm"),
    _federal("decreto11129", "Decreto nº 11.129/2022 — regulamento da Lei Anticorrupção", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/decreto/d11129.htm", tipo_documento="decreto"),
    _federal("lei12527", "Lei nº 12.527/2011 — Lei de Acesso à Informação", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm"),
    _federal("lei13709", "Lei nº 13.709/2018 — LGPD", "https://www2.camara.leg.br/legin/fed/lei/2018/lei-13709-14-agosto-2018-787077-normaatualizada-pl.html"),
    _federal("lei13303", "Lei nº 13.303/2016 — Empresas Estatais", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2016/lei/l13303.htm"),
    _federal("lei8987", "Lei nº 8.987/1995 — Concessões e Permissões", "https://www.planalto.gov.br/ccivil_03/leis/l8987cons.htm", ramo_direito="Serviços Públicos"),
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
    _federal("portaria938", "Portaria SEGES/ME nº 938/2022 — catálogo eletrônico de padronização", "https://www.gov.br/pncp/pt-br/catalogo-eletronico-de-padronizacao/legislacao/portaria-seges-me-no-938-de-2-de-fevereiro-de-2022", tipo_documento="portaria", required=True),
    _federal("lei6938", "Lei nº 6.938/1981 — Política Nacional do Meio Ambiente", "https://www.planalto.gov.br/ccivil_03/leis/l6938compilada.htm", ramo_direito="Ambiental"),
    _federal("lei12305", "Lei nº 12.305/2010 — Política Nacional de Resíduos Sólidos", "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2010/lei/l12305.htm"),
    _federal("lei9605", "Lei nº 9.605/1998 — Crimes Ambientais", "https://www.planalto.gov.br/ccivil_03/leis/l9605.htm"),
    _federal("lei13146", "Lei nº 13.146/2015 — Estatuto da Pessoa com Deficiência", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13146.htm"),
    _federal("lei8666", "Lei nº 8.666/1993 — regime histórico de licitações", "https://www.planalto.gov.br/ccivil_03/leis/l8666cons.htm", status="revogado", revogado=True, effective_to="2023-12-30"),
    _federal("lei10520", "Lei nº 10.520/2002 — pregão (regime histórico)", "https://www.planalto.gov.br/ccivil_03/leis/2002/l10520.htm", status="revogado", revogado=True, effective_to="2023-12-30"),
    _federal("lei12462", "Lei nº 12.462/2011 — RDC (regime histórico)", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12462.htm", status="revogado", revogado=True, effective_to="2023-12-30"),
    _federal("pncp", "PNCP — legislação e atos oficiais", "https://www.gov.br/pncp/pt-br/pncp/legislacao/leis", tipo_documento="portal_oficial", source_role="orientacao_oficial", authority_level=3, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=20, index_only=True),
    _federal("compras", "Compras.gov.br — legislação de contratações públicas", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao", tipo_documento="portal_oficial", source_role="orientacao_oficial", authority_level=3, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=30, index_only=True),
    _federal("compras-in", "Compras.gov.br — Instruções Normativas", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas", tipo_documento="instrucao_normativa", source_role="norma", authority_level=1, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=60, index_only=True),
    _sp("tcesp-srp", "TCESP — Deliberação 2026 sobre Sistema de Registro de Preços e adesão", "https://tce.sp.gov.br/legislacao/deliberacao/dispoe-sobre-diretrizes-e-procedimentos-serem-observados-pelos-orgaos-e", tipo_documento="deliberacao", source_role="jurisprudencia_controle", authority_level=2, tribunal="TCESP", required=True),
    _sp("sp-const", "Constituição do Estado de São Paulo — texto atualizado", "https://www.al.sp.gov.br/repositorio/legislacao/constituicao/1989/compilacao-constituicao-0-05.10.1989.html", tipo_documento="constituicao_estadual", required=True),
    _sp("sp-lei10177", "Lei SP nº 10.177/1998 — Processo Administrativo", "https://www.al.sp.gov.br/repositorio/legislacao/lei/1998/compilacao-lei-10177-30.12.1998.html", tipo_documento="lei", required=True),
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
    _sp("sp-compras", "Compras SP — legislação e regulamentação", "https://compras.sp.gov.br/legislacao/", tipo_documento="portal_oficial", source_role="orientacao_oficial", authority_level=3, required=True, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=60, index_only=True),
    _federal("lei13655", "Lei nº 13.655/2018 — alterações na LINDB sobre decisão e controle público", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13655.htm", tipo_documento="lei"),
    _federal("decreto9830", "Decreto nº 9.830/2019 — regulamenta a LINDB para decisão pública", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2019/decreto/d9830.htm", tipo_documento="decreto"),
    _federal("lei12813", "Lei nº 12.813/2013 — conflito de interesses", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12813.htm", tipo_documento="lei"),
    _federal("lei14770", "Lei nº 14.770/2023 — altera a Lei nº 14.133/2021", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/lei/l14770.htm", tipo_documento="lei"),
    _federal("lei14981", "Lei nº 14.981/2024 — contratações em situação de calamidade pública", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2024/lei/l14981.htm", tipo_documento="lei"),
    _federal("decreto12174", "Decreto nº 12.174/2024 — garantias trabalhistas em contratos administrativos", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2024/decreto/d12174.htm", tipo_documento="decreto"),
    _federal("decreto12304", "Decreto nº 12.304/2024 — programas de integridade nas contratações federais", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2024/decreto/d12304.htm", tipo_documento="decreto"),
    _federal("decreto12771", "Decreto nº 12.771/2025 — contratações para desenvolvimento sustentável", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/d12771.htm", tipo_documento="decreto"),
    _federal("lei15210", "Lei nº 15.210/2025 — equipamentos diagnósticos ou terapêuticos no SUS", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/l15210.htm", tipo_documento="lei"),
    _federal("lei15266", "Lei nº 15.266/2025 — Sistema de Compras Expressas (Sicx)", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/l15266.htm", tipo_documento="lei"),
    _federal("lei15190", "Lei nº 15.190/2025 — Lei Geral do Licenciamento Ambiental", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/l15190.htm", tipo_documento="lei"),
    _federal("decreto12926", "Decreto nº 12.926/2026 — atualização de garantias trabalhistas em contratos administrativos", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/decreto/d12926.htm", tipo_documento="decreto"),
    _federal("decreto13031", "Decreto nº 13.031/2026 — Contratos.gov.br", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/decreto/d13031.htm", tipo_documento="decreto"),
    _federal("lei15471", "Lei nº 15.471/2026 — alteração legislativa com impacto no regime de contratações", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/lei/l15471.htm", tipo_documento="lei"),
    _federal("decreto13106", "Decreto nº 13.106/2026 — Sistema de Compras Expressas (Sicx)", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/decreto/d13106.htm", tipo_documento="decreto"),
    _federal("decreto11430", "Decreto nº 11.430/2023 — equidade de gênero nas contratações públicas", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/decreto/d11430.htm", tipo_documento="decreto"),
    _federal("decreto11461", "Decreto nº 11.461/2023 — leilão eletrônico no âmbito federal", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/decreto/d11461.htm", tipo_documento="decreto"),
    _federal("decreto11531", "Decreto nº 11.531/2023 — convênios e contratos de repasse", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/decreto/d11531.htm", tipo_documento="decreto"),
    _federal("portaria8678", "Portaria SEGES/ME nº 8.678/2021 — governança das contratações públicas", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/portarias/portaria-seges-me-no-8-678-de-19-de-julho-de-2021", tipo_documento="portaria"),
    _federal("portaria1769", "Portaria SEGES/MGI nº 1.769/2023 — regime de transição da Lei nº 14.133", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/portarias/portaria-seges-mgi-no-1-769-de-25-de-abril-de-2023", tipo_documento="portaria", source_role="norma", authority_level=1),
    _federal("in147", "IN SEGES/MGI nº 147/2026 — reembolso-creche em contratos com dedicação exclusiva", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-mgi-no-147-de-13-de-abril-de-2026", tipo_documento="instrucao_normativa"),
    _federal("in148", "IN SEGES/MGI nº 148/2026 — jornada de 40 horas em contratos com dedicação exclusiva", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-mgi-no-148-de-13-de-abril-de-2026", tipo_documento="instrucao_normativa"),
    _federal("in176", "IN SEGES/MGI nº 176/2024 — custos mínimos e garantias trabalhistas", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-mgi-no-176-de-25-de-novembro-de-2024", tipo_documento="instrucao_normativa"),
    _federal("in190", "IN SEGES/MGI nº 190/2024 — serviços com dedicação exclusiva e redução de jornada", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-mgi-no-190-de-5-de-dezembro-de-2024", tipo_documento="instrucao_normativa"),
    _federal("in381", "IN SEGES/MGI nº 381/2025 — atualização de serviços para jornada de 40 horas", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-mgi-no-381-de-17-de-setembro-de-2025", tipo_documento="instrucao_normativa"),
    _federal("in382", "IN SEGES/MGI nº 382/2025 — equidade entre mulheres e homens para desempate", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas/instrucao-normativa-seges-mgi-no-382-de-17-de-setembro-de-2025", tipo_documento="instrucao_normativa"),
    _federal("in213", "IN SEGES/MGI nº 213/2025 — férias de terceirizados em dedicação exclusiva", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas", tipo_documento="instrucao_normativa", follow_links=True, follow_patterns=(r"213",), max_follow=4, index_only=True),
    _federal("compras-temas-14133", "Portal Compras.gov.br — Lei nº 14.133 por temas", "https://www.gov.br/compras/pt-br/nllc/legislacao-14-133-por-tema/", tipo_documento="portal_oficial", source_role="orientacao_oficial", authority_level=3),
    _federal("transferegov-pc33", "Portaria Conjunta MGI/MF/CGU nº 33/2023 — convênios e contratos de repasse", "https://www.gov.br/transferegov/pt-br/legislacao/portarias/portaria-conjunta-mgi-mf-cgu-no-33-de-30-de-agosto-de-2023", tipo_documento="portaria_conjunta", source_role="norma", authority_level=1),
    _federal("transferegov-pc25-2025", "Portaria Conjunta MGI/MF/CGU nº 25/2025 — alteração da PC nº 33/2023", "https://www.gov.br/transferegov/pt-br/legislacao/portarias/portaria-conjunta-mgi-mf-cgu-no-25-de-9-de-maio-de-2025", tipo_documento="portaria_conjunta", source_role="norma", authority_level=1),
    _federal("agu-on", "AGU — Orientações Normativas", "https://www.gov.br/agu/pt-br/composicao/cgu/cgu/onsagu", tipo_documento="orientacao_normativa", source_role="orientacao_oficial", authority_level=3),
    _federal("agu-pareceres-referenciais", "AGU — Pareceres Referenciais em Licitações e Contratos", "https://www.gov.br/agu/pt-br/composicao/procuradoria-geral-federal-1/subprocuradoria-federal-de-consultoria-juridica/equipe-de-licitacoes-e-contratos-elic-1/modelos-minutas-e-pareceres-1/pareceres-referenciais", tipo_documento="parecer_referencial", source_role="orientacao_oficial", authority_level=3, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=80),
    _federal("agu-modelos-14133", "AGU — modelos da Lei nº 14.133/2021", "https://www.gov.br/agu/pt-br/composicao/cgu/cgu/modelos/licitacoesecontratos/14133", tipo_documento="modelo_orientacao", source_role="orientacao_oficial", authority_level=3, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=100),
    _federal("agu-contratacao-direta", "AGU — modelos de contratação direta da Lei nº 14.133/2021", "https://www.gov.br/agu/pt-br/composicao/cgu/cgu/modelos/licitacoesecontratos/14133/contratacao-direta", tipo_documento="modelo_orientacao", source_role="orientacao_oficial", authority_level=3, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=80),
    _federal("agu-pregao-concorrencia", "AGU — modelos de pregão e concorrência da Lei nº 14.133/2021", "https://www.gov.br/agu/pt-br/composicao/cgu/cgu/modelos/licitacoesecontratos/14133/pregao-e-concorrencia", tipo_documento="modelo_orientacao", source_role="orientacao_oficial", authority_level=3, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=100),
    _federal("agu-tic", "AGU — modelos de bens e serviços de TIC da Lei nº 14.133/2021", "https://www.gov.br/agu/pt-br/composicao/cgu/cgu/modelos/licitacoesecontratos/14133/bens-e-servicos-de-tic", tipo_documento="modelo_orientacao", source_role="orientacao_oficial", authority_level=3, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=80),

    _federal("pl-14230", "Lei nº 14.230/2021 — alterações na Lei de Improbidade Administrativa", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14230.htm", ramo_direito="Responsabilização Pública"),
    _federal("pl-6017", "Decreto nº 6.017/2007 — regulamentação dos consórcios públicos", "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2007/decreto/d6017.htm", tipo_documento="decreto", ramo_direito="Federalismo e Cooperação"),
    _federal("pl-lc173", "Lei Complementar nº 173/2020 — regras fiscais do Programa Federativo", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp173.htm", tipo_documento="lei_complementar", ramo_direito="Financeiro e Orçamentário"),
    _federal("pl-12232", "Lei nº 12.232/2010 — serviços de publicidade prestados por agências", "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2010/lei/l12232.htm", ramo_direito="Contratações Públicas"),
    _federal("pl-13243", "Lei nº 13.243/2016 — ciência, tecnologia e inovação", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2016/lei/l13243.htm", ramo_direito="Regulação e Direito Econômico"),
    _federal("pl-10973", "Lei nº 10.973/2004 — inovação e pesquisa científica e tecnológica", "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l10973.htm", ramo_direito="Regulação e Direito Econômico"),
    _federal("lei4717", "Lei nº 4.717/1965 — Ação Popular", "https://www.planalto.gov.br/ccivil_03/leis/l4717.htm", ramo_direito="Controle e Responsabilização"),
    _federal("lei7347", "Lei nº 7.347/1985 — Ação Civil Pública", "https://www.planalto.gov.br/ccivil_03/leis/l7347compilada.htm", ramo_direito="Controle e Responsabilização"),
    _federal("lc131", "Lei Complementar nº 131/2009 — Lei da Transparência", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp131.htm", tipo_documento="lei_complementar", ramo_direito="Transparência e Controle"),
    _federal("decreto7724", "Decreto nº 7.724/2012 — regulamenta a Lei de Acesso à Informação", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/decreto/d7724.htm", tipo_documento="decreto", ramo_direito="Transparência e Controle"),
    _federal("lei6019", "Lei nº 6.019/1974 — trabalho temporário e terceirização", "https://www.planalto.gov.br/ccivil_03/leis/l6019.htm", ramo_direito="Trabalhista e Terceirização"),
    _federal("lei12016", "Lei nº 12.016/2009 — Mandado de Segurança", "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2009/lei/l12016.htm", ramo_direito="Processual Público"),
    _federal("lc182", "Lei Complementar nº 182/2021 — Marco Legal das Startups e Contrato Público para Solução Inovadora", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp182.htm", tipo_documento="lei_complementar", ramo_direito="Ciência, Tecnologia e Inovação"),
    _sp("sp-lai", "Decreto SP nº 68.155/2023 — regulamenta a Lei de Acesso à Informação no Estado de São Paulo", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68155-09.12.2023.html", tipo_documento="decreto", required=True, ramo_direito="Transparência e Controle"),
    _municipal_sp("spm-decreto62100", "Decreto Municipal SP nº 62.100/2022 — licitações e contratos administrativos", "https://legislacao.prefeitura.sp.gov.br/decreto-62100-de-27-de-dezembro-de-2022/detalhe", tipo_documento="decreto", required=True, ramo_direito="Contratações Públicas"),
    _municipal_sp("spm-decreto62436", "Decreto Municipal SP nº 62.436/2023 — regime de transição para a Lei nº 14.133/2021", "https://legislacao.prefeitura.sp.gov.br/decreto-62436-de-26-de-maio-de-2023", tipo_documento="decreto", required=True, ramo_direito="Contratações Públicas"),
    _municipal_sp("spm-decreto64863", "Decreto Municipal SP nº 64.863/2025 — alterações no Decreto nº 62.100/2022", "https://legislacao.prefeitura.sp.gov.br/decreto-64863-de-22-de-dezembro-de-2025", tipo_documento="decreto", required=True, ramo_direito="Contratações Públicas"),
    _municipal_sp("spm-in-seges6-2023", "IN SEGES nº 6/2023 — pesquisa de preços no Município de São Paulo", "https://legislacao.prefeitura.sp.gov.br/instrucao-normativa-secretaria-municipal-de-gestao-seges-6-de-10-de-novembro-de-2023/consolidado", tipo_documento="instrucao_normativa", ramo_direito="Contratações Públicas"),
    _municipal_sp("spm-pgm38-2025", "Portaria PGM nº 38/2025 — Comissão de Padronização de Editais de Licitação", "https://legislacao.prefeitura.sp.gov.br/portaria-procuradoria-geral-do-municipio-pgm-38-de-2-de-abril-de-2025/consolidado", tipo_documento="portaria", source_role="orientacao_oficial", authority_level=3, ramo_direito="Contratações Públicas"),
    _sp("sp-pge-pareceres", "PGE-SP — pareceres e orientações jurídicas", "https://revistas.pge.sp.gov.br/boletins", tipo_documento="pareceres_e_orientacoes", source_role="orientacao_oficial", authority_level=3, required=True, follow_links=True, follow_patterns=(r"\\.pdf(?:$|\\?)",), max_follow=80, index_only=True, ramo_direito="Advocacia Pública e Orientação"),
    _federal("lei5172", "Lei nº 5.172/1966 — Código Tributário Nacional", "https://www.planalto.gov.br/ccivil_03/leis/l5172compilado.htm", ramo_direito="Tributário"),
    _federal("lei8662", "Lei nº 8.662/1993 — regulamenta a profissão de assistente social", "https://www.planalto.gov.br/ccivil_03/leis/l8662.htm", ramo_direito="Assistência Social"),
    _federal("lei8742", "Lei nº 8.742/1993 — Lei Orgânica da Assistência Social", "https://www.planalto.gov.br/ccivil_03/leis/l8742compilado.htm", ramo_direito="Assistência Social"),
    _federal("lei8080", "Lei nº 8.080/1990 — Sistema Único de Saúde", "https://www.planalto.gov.br/ccivil_03/leis/l8080.htm", ramo_direito="Saúde Pública"),
    _federal("lei9394", "Lei nº 9.394/1996 — Lei de Diretrizes e Bases da Educação Nacional", "https://www.planalto.gov.br/ccivil_03/leis/l9394.htm", ramo_direito="Educação Pública"),
    _federal("lei8112", "Lei nº 8.112/1990 — regime jurídico dos servidores públicos federais", "https://www.planalto.gov.br/ccivil_03/leis/l8112cons.htm", ramo_direito="Pessoal e Servidores"),
    _federal("lei10257", "Lei nº 10.257/2001 — Estatuto da Cidade", "https://www.planalto.gov.br/ccivil_03/leis/leis_2001/l10257.htm", ramo_direito="Urbanístico"),
    _federal("pl-discovery-camara", "Câmara dos Deputados — legislação federal para descoberta", "https://www.camara.leg.br/atividade-legislativa/legislacao", tipo_documento="portal_oficial", source_role="descoberta_legislativa", authority_level=3, index_only=True),
    _federal("pl-discovery-lexml", "LexML — legislação brasileira para descoberta", "https://www.lexml.gov.br/", tipo_documento="portal_oficial", source_role="descoberta_legislativa", authority_level=3, index_only=True),
    _federal("pl-discovery-leis-2026", "Legislação federal — leis de 2026 para descoberta", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/lei/_lei2026.htm", tipo_documento="portal_oficial", source_role="descoberta_legislativa", authority_level=3, index_only=True),
    _federal("pl-discovery-leis-2025", "Legislação federal — leis de 2025 para descoberta", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/_leis2025.htm", tipo_documento="portal_oficial", source_role="descoberta_legislativa", authority_level=3, index_only=True),
    _federal("pl-discovery-lc-atualizadas", "Planalto — leis complementares para descoberta", "https://www.planalto.gov.br/ccivil_03/leis/lcp/", tipo_documento="portal_oficial", source_role="descoberta_legislativa", authority_level=3, index_only=True),
    _federal("pl-discovery-decretos-2026", "Planalto — decretos de 2026 para descoberta", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/decreto/_decretos2026.htm", tipo_documento="portal_oficial", source_role="descoberta_legislativa", authority_level=3, index_only=True),
]

SOURCE_BY_ID = {item["id"]: item for item in SOURCES}


def _validate_catalog():
    ids = [item["id"] for item in SOURCES]
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if duplicates:
        raise ValueError("Catálogo de fontes com IDs duplicados: " + ", ".join(duplicates))
    required_keys = {"id", "title", "urls", "jurisdicao", "esfera", "orgao", "tipo_documento", "source_role", "authority_level", "status"}
    invalid = [item["id"] for item in SOURCES if not required_keys <= set(item)]
    if invalid:
        raise ValueError("Fontes sem metadados obrigatórios: " + ", ".join(invalid))
    expected_levels = {
        "norma": 1,
        "jurisprudencia": 2,
        "jurisprudencia_controle": 2,
        "orientacao_oficial": 3,
        "doutrina": 4,
        "taxonomia": 3,
        "descoberta_legislativa": 3,
        "controle_estadual": 2,
    }
    inconsistent = [
        item["id"] for item in SOURCES
        if item.get("source_role") in expected_levels and item.get("authority_level") != expected_levels[item["source_role"]]
    ]
    if inconsistent:
        raise ValueError("Nível de autoridade incompatível com o papel da fonte: " + ", ".join(inconsistent))


_validate_catalog()
