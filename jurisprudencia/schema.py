from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


TRIBUNAL_ALIASES = {
    "TCU": "TCU",
    "TRIBUNAL DE CONTAS DA UNIÃO": "TCU",
    "TRIBUNAL DE CONTAS DA UNIAO": "TCU",
    "TCESP": "TCESP",
    "TCE-SP": "TCESP",
    "TCE SP": "TCESP",
    "TRIBUNAL DE CONTAS DO ESTADO DE SÃO PAULO": "TCESP",
    "TRIBUNAL DE CONTAS DO ESTADO DE SAO PAULO": "TCESP",
    "STJ": "STJ",
    "SUPERIOR TRIBUNAL DE JUSTIÇA": "STJ",
    "SUPERIOR TRIBUNAL DE JUSTICA": "STJ",
    "STF": "STF",
    "SUPREMO TRIBUNAL FEDERAL": "STF",
    "TJSP": "TJSP",
    "TJ-SP": "TJSP",
    "TRIBUNAL DE JUSTIÇA DE SÃO PAULO": "TJSP",
    "TRIBUNAL DE JUSTICA DE SAO PAULO": "TJSP",
}


def _fold(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in raw if not unicodedata.combining(ch)).strip().upper()


def _coalesce(data: dict[str, Any], target: str, *aliases: str) -> None:
    if data.get(target) not in (None, ""):
        return
    for alias in aliases:
        if data.get(alias) not in (None, ""):
            data[target] = data[alias]
            return


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [str(item).strip() for item in value.values() if str(item).strip()]
    return [part.strip() for part in re.split(r"[;\n|]+", str(value)) if part.strip()]


class JurisprudenciaRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True, validate_assignment=True)

    tribunal: str = ""
    tipo_documento: str | None = None
    numero_processo: str = ""
    numero_sumula: str | None = None
    orgao_julgador: str | None = None
    relator: str | None = None
    data: str | None = None
    data_publicacao: str | None = None
    assunto: list[str] = []
    ementa: str | None = None
    tese: str | None = None
    decisao: str | None = None
    inteiro_teor: str | None = None
    url_oficial: str | None = None
    tipo_decisao: str | None = None
    numero_decisao: str | None = None
    origem: str | None = None
    data_autuacao: str | None = None
    partes: list[str] = []
    situacao: str | None = None
    retrieved_at: str | None = None
    sha256: str | None = None
    version_sha256: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, raw: Any) -> Any:
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, dict):
            return raw
        data = dict(raw)
        _coalesce(data, "tribunal", "TRIBUNAL", "siglaTribunal", "tribunal_sigla", "orgaoTribunal")
        _coalesce(data, "tipo_documento", "TIPO_DOCUMENTO", "tipoDocumento", "document_type")
        _coalesce(
            data,
            "numero_processo",
            "NUMPROCESSO",
            "NUMPROCESSO_FORMATADO",
            "numeroProcesso",
            "processo",
            "processo_numero",
            "numeroProcessoFormatado",
            "KEY",
            "key",
            "id",
        )
        _coalesce(data, "numero_sumula", "NUMSUMULA", "numeroSumula", "sumula_numero")
        _coalesce(data, "numero_decisao", "NUMACORDAO", "numeroAcordao", "NUMACORDAOINT", "numeroDecisao", "acordao_numero")
        _coalesce(data, "orgao_julgador", "COLEGIADO", "colegiado", "CODCOLEGIADO", "orgaoJulgador", "nomeOrgaoJulgador")
        _coalesce(data, "relator", "RELATOR", "relator_nome", "ministroRelator", "relator_processo_nome", "relator_acordao_nome")
        _coalesce(data, "data", "DATASESSAO", "DTSESSAO", "dataSessao", "dataSessaoFormatada", "dataJulgamento", "julgamento_data")
        _coalesce(data, "data_publicacao", "DATAPUBLICACAO", "dataPublicacao", "publicacao_data")
        _coalesce(data, "data_autuacao", "dataAutuacao", "DATAAUTUACAO")
        _coalesce(data, "ementa", "SUMARIO", "sumario", "EMENTA", "titulo", "TITULO", "ementa_texto")
        _coalesce(data, "tese", "TESE", "teseJuridica", "documental_tese_texto")
        _coalesce(data, "decisao", "ACORDAO", "acordao", "decisao_texto")
        _coalesce(data, "inteiro_teor", "inteiroTeor", "inteiro_teor_texto")
        _coalesce(data, "url_oficial", "URLACORDAO", "urlAcordao", "URL", "url", "inteiro_teor_url")
        _coalesce(data, "tipo_decisao", "TIPO", "tipo", "tipoDeDecisao")
        _coalesce(data, "assunto", "AREA", "area", "TEMA", "tema", "SUBTEMA", "subtema", "assuntos")
        _coalesce(data, "partes", "PARTES", "partes_lista_texto", "partesLista")
        tribunal = TRIBUNAL_ALIASES.get(_fold(data.get("tribunal")), str(data.get("tribunal") or "").strip().upper())
        if tribunal:
            data["tribunal"] = tribunal
        data["assunto"] = _as_list(data.get("assunto"))
        data["partes"] = _as_list(data.get("partes"))
        return data

    def validate(self) -> None:
        errors = []
        tribunal = str(self.tribunal or "").strip().upper()
        process = str(self.numero_processo or "").strip()
        if tribunal not in {"TCU", "TCESP", "STJ", "STF", "TJSP"}:
            errors.append(f"tribunal inválido: {self.tribunal!r}")
        if not process and str(self.tipo_documento or '').casefold() != 'sumula':
            errors.append("numero_processo é obrigatório")
        if str(self.tipo_documento or '').casefold() == 'sumula' and not str(self.numero_sumula or '').strip():
            errors.append("numero_sumula é obrigatório para súmula")
        if not isinstance(self.assunto, list):
            errors.append("assunto deve ser lista")
        if not isinstance(self.partes, list):
            errors.append("partes deve ser lista")
        if self.url_oficial and not re.match(r"^https?://", str(self.url_oficial), re.I):
            errors.append("url_oficial deve ser HTTP(S)")
        if errors:
            raise ValueError("Registro de jurisprudência inválido: " + "; ".join(errors))

    @property
    def document_key(self) -> str:
        self.validate()
        parts = [
            self.tribunal or "",
            self.tipo_documento or "",
            self.numero_processo or "",
            self.numero_sumula or "",
            self.numero_decisao or "",
            self.tipo_decisao or "",
        ]
        if not self.numero_decisao:
            parts.append(re.sub(r"\s+", " ", self.ementa or "").strip()[:800])
        if not self.numero_processo:
            parts.append(self.url_oficial or "")
        base = "|".join(parts)
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]

    def canonical_payload(self) -> dict[str, Any]:
        self.validate()
        payload = self.to_dict()
        payload.pop("retrieved_at", None)
        payload.pop("sha256", None)
        payload.pop("version_sha256", None)
        if payload.get("url_oficial"):
            payload["url_oficial"] = re.sub(
                r";jsessionid=[^?/#]+", "", str(payload["url_oficial"]), flags=re.I
            )
        return payload

    def calculate_version_sha256(self) -> str:
        raw = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def to_index_text(self) -> str:
        self.validate()
        lines = [f"TRIBUNAL: {self.tribunal}"]
        if self.tipo_documento:
            lines.append(f"TIPO DOCUMENTO: {self.tipo_documento}")
        if self.numero_sumula:
            lines.append(f"SÚMULA: {self.numero_sumula}")
        if self.numero_processo:
            lines.append(f"PROCESSO: {self.numero_processo}")
        if self.numero_decisao:
            lines.append(f"DECISÃO/ACÓRDÃO: {self.numero_decisao}")
        if self.tipo_decisao:
            lines.append(f"TIPO: {self.tipo_decisao}")
        if self.orgao_julgador:
            lines.append(f"ÓRGÃO JULGADOR/COLEGIADO: {self.orgao_julgador}")
        if self.relator:
            lines.append(f"RELATOR: {self.relator}")
        if self.data:
            lines.append(f"DATA DO JULGAMENTO/SESSÃO: {self.data}")
        if self.data_publicacao:
            lines.append(f"DATA DA PUBLICAÇÃO: {self.data_publicacao}")
        if self.data_autuacao:
            lines.append(f"DATA DA AUTUAÇÃO: {self.data_autuacao}")
        if self.situacao:
            lines.append(f"SITUAÇÃO: {self.situacao}")
        if self.assunto:
            lines.append("ASSUNTOS: " + "; ".join(self.assunto))
        if self.partes:
            lines.append("PARTES: " + " | ".join(self.partes))
        if self.ementa:
            lines.extend(["", "EMENTA:", self.ementa])
        if self.tese:
            lines.extend(["", "TESE/ENTENDIMENTO:", self.tese])
        if self.decisao:
            lines.extend(["", "DECISÃO:", self.decisao])
        if self.inteiro_teor:
            lines.extend(["", "INTEIRO TEOR:", self.inteiro_teor])
        if self.url_oficial:
            lines.extend(["", f"FONTE OFICIAL: {self.url_oficial}"])
        return "\n".join(lines).strip() + "\n"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
