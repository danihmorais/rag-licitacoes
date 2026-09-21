from __future__ import annotations
import json
import re
import warnings
from pathlib import Path
from typing import Any

TRIBUNAL_AUTHORITY = {"STF": 2, "STJ": 3, "TCU": 3, "TCESP": 4, "TJSP": 4}
ALLOWED_ROLES = {"norma", "jurisprudencia", "jurisprudencia_controle", "orientacao_oficial", "doutrina"}

ANO_RE = re.compile(r"\b(20\d{2})\b")
TRIBUNAL_RE = re.compile(r"\b(STF|STJ|TCU|TCESP|TJSP)\b", re.I)
PROCESSO_RE = re.compile(r"\b(?:processo|proc\.?|autos)\s*(?:n[ºo°]?\s*)?([\w./-]+)", re.I)

def _read_sidecar(path: Path) -> dict[str, Any]:
    sidecar = Path(str(path) + ".json")
    if not sidecar.exists():
        return {}
    try:
        value = json.loads(sidecar.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("sidecar precisa ser objeto JSON")
        return value
    except Exception as exc:
        raise ValueError(f"Sidecar inválido: {sidecar}: {exc}") from exc

def _header_year(text: str) -> int | None:
    m = re.search(r"\b(?:lei|decreto|portaria|resolu[cç][aã]o|instru[cç][aã]o normativa)[^\n]{0,180}\b(?:de|em)\s+\d{1,2}\s+de\s+[a-zç]+\s+de\s+(20\d{2})\b", text, re.I)
    return int(m.group(1)) if m else None

def _infer(filename: str, sample: str) -> dict[str, Any]:
    name = filename.lower()
    text = sample[:30000]
    tribunal_match = TRIBUNAL_RE.search(text) or TRIBUNAL_RE.search(filename)
    tribunal = tribunal_match.group(1).upper() if tribunal_match else None
    year = _header_year(text)
    if year is None:
        years = ANO_RE.findall(text)
        year = int(years[0]) if years else None

    if tribunal in TRIBUNAL_AUTHORITY:
        role = "jurisprudencia" if tribunal in {"STF", "STJ"} else "jurisprudencia_controle"
        return {
            "jurisdicao": "federal" if tribunal in {"STF", "STJ", "TCU"} else "estadual_sp",
            "esfera": "federal" if tribunal in {"STF", "STJ", "TCU"} else "estadual",
            "source_role": role,
            "authority_level": TRIBUNAL_AUTHORITY[tribunal],
            "tribunal": tribunal,
            "ano": year,
        }

    if re.search(r"lei\s*14[ ._-]?133|l\.?\s*14[ ._-]?133", name):
        jurisdicao, esfera = "federal", "federal"
    elif re.search(r"(?:^|[_ -])sp(?:[_ -]|$)|s[aã]o[_ -]?paulo", name):
        jurisdicao, esfera = "estadual_sp", "estadual"
    elif any(k in name for k in ("doutrina", "manual", "guia", "cartilha", "orientacao", "orientação")):
        jurisdicao, esfera = "federal", "federal"
    else:
        jurisdicao, esfera = None, None

    role = "orientacao_oficial" if any(k in name for k in ("manual","guia","cartilha","orienta")) else "norma"
    authority = 1 if role == "norma" else 5
    if not jurisdicao:
        warnings.warn(f"Jurisdição não determinada para {filename}; use sidecar JSON.")
    return {
        "jurisdicao": jurisdicao,
        "esfera": esfera,
        "source_role": role,
        "authority_level": authority,
        "tribunal": tribunal,
        "ano": year,
    }

def extract_metadata(path: str | Path, sample: str, explicit: dict[str, Any] | None = None) -> dict[str, Any]:
    p = Path(path)
    sidecar = _read_sidecar(p)
    data: dict[str, Any] = _infer(p.name, sample)
    data.update(sidecar)
    if explicit:
        data.update(explicit)

    tribunal = str(data.get("tribunal") or "").upper() or None
    if tribunal in TRIBUNAL_AUTHORITY:
        data["tribunal"] = tribunal
        data["authority_level"] = TRIBUNAL_AUTHORITY[tribunal]
        if tribunal in {"STF", "STJ", "TCU"}:
            data.setdefault("jurisdicao", "federal")
            data.setdefault("esfera", "federal")
        else:
            data.setdefault("jurisdicao", "estadual_sp")
            data.setdefault("esfera", "estadual")

    if data.get("source_role") not in ALLOWED_ROLES:
        data["source_role"] = "norma"

    data.setdefault("source", p.name)
    data.setdefault("title", p.stem)
    data.setdefault("vigente", True)
    data.setdefault("municipio", None)
    data.setdefault("inicio_vigencia", None)
    data.setdefault("fim_vigencia", None)
    data.setdefault("document_key", p.stem.lower())
    return data
