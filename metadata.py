"""Extração heurística e normalização de metadados jurídicos."""
import json
import re

MODALIDADES = [
    "Pregão Eletrônico", "Pregão Presencial", "Concorrência Eletrônica",
    "Concorrência", "Tomada de Preços", "Convite", "Dispensa de Licitação",
    "Dispensa Eletrônica", "Inexigibilidade de Licitação", "Chamamento Público",
    "Credenciamento", "RDC",
]
TIPOS = ["Menor Preço", "Maior Desconto", "Melhor Técnica", "Técnica e Preço", "Maior Lance", "Maior Oferta"]
PROCESSO_RE = re.compile(r"processo\s*(?:administrativo)?\s*n[ºo°.]*\s*[:\-]?\s*([\d./\-]{4,20})", re.IGNORECASE)
ANO_RE = re.compile(r"\b(20\d{2})\b")
MUNICIPIO_RE = re.compile(r"(?:MUNIC[ÍI]PIO\s+DE|PREFEITURA\s+MUNICIPAL\s+DE|PREFEITURA\s+DE)\s+([A-ZÀ-Ú][A-ZÀ-Ú\s']{2,40}?)(?:[\n\r,\.\-]|\s{2,}|$)", re.IGNORECASE)


def _find_first(patterns, text):
    for pattern in patterns:
        if re.search(re.escape(pattern), text, re.IGNORECASE):
            return pattern
    return None


def _infer_source(pdf_path) -> dict:
    name = pdf_path.name.lower()
    result = {"jurisdicao": None, "orgao": None, "tipo_documento": None}
    if "tcesp" in name or "tribunal de contas do estado de são paulo" in name:
        result.update(jurisdicao="estadual_sp", orgao="TCESP", tipo_documento="jurisprudencia")
    elif "tcu" in name or "tribunal de contas da união" in name:
        result.update(jurisdicao="federal", orgao="TCU", tipo_documento="jurisprudencia")
    elif "constituicao" in name:
        result.update(jurisdicao="federal", orgao="Constituição Federal", tipo_documento="constituicao")
    elif re.search(r"l\.?\s*14[ ._\-]?133|lei.?14[ ._\-]?133", name):
        result.update(jurisdicao="federal", orgao="Legislação Federal", tipo_documento="lei")
    elif "decreto" in name:
        result["tipo_documento"] = "decreto"
    return result


def extract_metadata(text: str, pdf_path) -> dict:
    sample = text[:12000]
    metadata = {
        "municipio": None, "modalidade": _find_first(MODALIDADES, sample),
        "ano": None, "processo": None, "tipo": _find_first(TIPOS, sample),
        **_infer_source(pdf_path),
    }
    match = PROCESSO_RE.search(sample)
    if match:
        metadata["processo"] = match.group(1).strip(" .-")
    match = MUNICIPIO_RE.search(sample)
    if match:
        metadata["municipio"] = " ".join(match.group(1).split()).title()
    years = ANO_RE.findall(sample)
    if years:
        metadata["ano"] = int(years[0])
    elif metadata["processo"]:
        match = re.search(r"20\d{2}", metadata["processo"])
        if match:
            metadata["ano"] = int(match.group(0))
    sidecar = pdf_path.with_suffix(".json")
    if sidecar.exists():
        overrides = json.loads(sidecar.read_text(encoding="utf-8"))
        if not isinstance(overrides, dict):
            raise ValueError(f"Sidecar inválido: {sidecar} deve conter um objeto JSON.")
        metadata.update({k: v for k, v in overrides.items() if v not in (None, "")})
    return metadata
