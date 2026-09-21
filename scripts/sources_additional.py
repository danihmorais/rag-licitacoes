from scripts.sources import SourceSpec, _federal, _sp

ADDITIONAL_SOURCES = [
    _federal("portaria-seges-938", "Portaria SEGES/ME nº 938/2022", "https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/portarias"),
    _federal("portal-compras", "Portal de Compras do Governo Federal", "https://www.gov.br/compras/pt-br", source_role="orientacao_oficial", authority_level=5, follow_links=True),
    _federal("pncp", "Portal Nacional de Contratações Públicas", "https://www.gov.br/pncp/pt-br", source_role="orientacao_oficial", authority_level=5, follow_links=True),
]
