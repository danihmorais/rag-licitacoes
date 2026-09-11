from __future__ import annotations

DEFAULT_QUERIES = (
    "Lei 14.133 licitação contrato administrativo",
    "contratação direta dispensa inexigibilidade",
    "edital habilitação qualificação técnica",
    "pesquisa de preços estudo técnico preliminar termo de referência",
    "registro de preços adesão ata",
    "sanção impedimento inidoneidade licitação",
    "reequilíbrio reajuste repactuação aditivo contrato",
    "fiscalização execução responsabilidade agente público licitação",
)


def parse_queries(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_QUERIES
    queries = tuple(item.strip() for item in value.split("|") if item.strip())
    return queries or DEFAULT_QUERIES
