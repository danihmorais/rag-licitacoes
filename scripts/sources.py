from __future__ import annotations
from dataclasses import dataclass, field

@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    title: str
    url: str
    jurisdiction: str
    sphere: str
    source_role: str = "norma"
    authority_level: int = 1
    tribunal: str | None = None
    follow_links: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)

def _federal(source_id: str, title: str, url: str, **kw) -> SourceSpec:
    return SourceSpec(source_id, title, url, "federal", "federal", **kw)

def _sp(source_id: str, title: str, url: str, **kw) -> SourceSpec:
    return SourceSpec(source_id, title, url, "estadual_sp", "estadual", **kw)

SOURCES = [
    _federal("lei-14133", "Lei nº 14.133/2021", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm", tags=("licitacoes","contratos","lei")),
    _federal("decreto-10024", "Decreto nº 10.024/2019", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2019/decreto/d10024.htm", tags=("pregao","eletronico")),
    _federal("decreto-11246", "Decreto nº 11.246/2022", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/decreto/d11246.htm", tags=("agentes","fiscalizacao")),
    _federal("decreto-11462", "Decreto nº 11.462/2023", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/decreto/d11462.htm", tags=("registro","precos")),
    _federal("tcu", "TCU — Jurisprudência e orientações", "https://pesquisa.apps.tcu.gov.br/#/pesquisa/jurisprudencia", source_role="jurisprudencia_controle", authority_level=3, tribunal="TCU", follow_links=True),
    _federal("tcu-manual", "TCU — orientações sobre licitações", "https://portal.tcu.gov.br/biblioteca-digital", source_role="orientacao_oficial", authority_level=5, tribunal="TCU", follow_links=True),
    _sp("sp-catalogo", "Decreto SP 68.021/2023", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68021-20.06.2023.html", tags=("catalogo","padronizacao")),
    _sp("tcesp", "TCESP — Jurisprudência", "https://www.tce.sp.gov.br/jurisprudencia", source_role="jurisprudencia_controle", authority_level=4, tribunal="TCESP", follow_links=True),
    _sp("tcesp-srp", "TCESP — Sistema de Registro de Preços", "https://www.tce.sp.gov.br/", source_role="jurisprudencia_controle", authority_level=4, tribunal="TCESP"),
    _sp("tjsp", "TJSP — jurisprudência", "https://esaj.tjsp.jus.br/cjsg/consultaCompleta.do", source_role="jurisprudencia", authority_level=4, tribunal="TJSP"),
]
