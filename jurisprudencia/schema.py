from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib
from typing import Any

@dataclass
class JurisprudenciaRecord:
    tribunal: str
    numero_processo: str | None
    data_julgamento: str | None
    relator: str | None
    tipo: str | None
    ementa: str
    assunto: str | None = None
    orgao_julgador: str | None = None
    url: str | None = None
    fonte: str | None = None
    metadados: dict[str, Any] | None = None

    @property
    def document_key(self) -> str:
        material = "|".join([
            self.tribunal or "", self.numero_processo or "",
            self.data_julgamento or "", self.url or "", self.ementa[:1000]
        ])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["document_key"] = self.document_key
        return d
