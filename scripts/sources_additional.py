from __future__ import annotations

try:
    from scripts.sources import _federal
except ModuleNotFoundError:
    from sources import _federal

EXTRA_SOURCES = [
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
    {"id":"tcu-dados-jurisprudencia","title":"TCU — Dados abertos de jurisprudência","urls":["https://sites.tcu.gov.br/dados-abertos/jurisprudencia/"],"jurisdicao":"federal","esfera":"federal","orgao":"TCU","tribunal":"TCU","tipo_documento":"dados_abertos","source_role":"jurisprudencia_controle","authority_level":2,"status":"vigente"},
    {"id":"stj-jurisprudencia","title":"STJ — Pesquisa de Jurisprudência","urls":["https://scon.stj.jus.br/SCON/"],"jurisdicao":"federal","esfera":"federal","orgao":"STJ","tribunal":"STJ","tipo_documento":"jurisprudencia","source_role":"jurisprudencia","authority_level":2,"status":"vigente"},
    {"id":"stf-jurisprudencia","title":"STF — Pesquisa de jurisprudência e inteiro teor","urls":["https://portal.stf.jus.br/jurisprudencia/"],"jurisdicao":"federal","esfera":"federal","orgao":"STF","tribunal":"STF","tipo_documento":"jurisprudencia","source_role":"jurisprudencia","authority_level":2,"status":"vigente"},
]
