from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class JurisprudenciaRecord:
    tribunal: str
    numero_processo: str
    orgao_julgador: str | None = None
    relator: str | None = None
    data: str | None = None
    ementa: str | None = None
    assunto: list[str] = field(default_factory=list)
    tese: str | None = None
    inteiro_teor: str | None = None
    url_oficial: str | None = None
    tipo_decisao: str | None = None
    numero_decisao: str | None = None
    origem: str | None = None
    retrieved_at: str | None = None
    sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
