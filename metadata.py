"""
Extração heurística de metadados a partir do texto do edital.

Editais não seguem um padrão único entre municípios/sistemas, então isso é
"melhor esforço": tenta pegar modalidade, ano, número de processo, município
e tipo via regex nas primeiras páginas. Sempre confira os resultados.

Se a extração automática errar ou deixar campo em branco, crie um arquivo
JSON com o mesmo nome do PDF ao lado dele, ex:

    pdfs/edital_001_2026.pdf
    pdfs/edital_001_2026.json

com o conteúdo:

    {"municipio": "Urânia", "modalidade": "Pregão Eletrônico", "ano": 2026,
     "processo": "001/2026", "tipo": "Menor Preço"}

Os campos do JSON sempre têm prioridade sobre o que a regex encontrar.
"""
import json
import re

MODALIDADES = [
    "Pregão Eletrônico",
    "Pregão Presencial",
    "Concorrência Eletrônica",
    "Concorrência",
    "Tomada de Preços",
    "Convite",
    "Dispensa de Licitação",
    "Dispensa Eletrônica",
    "Inexigibilidade de Licitação",
    "Chamamento Público",
    "Credenciamento",
    "RDC",
]

TIPOS = [
    "Menor Preço",
    "Maior Desconto",
    "Melhor Técnica",
    "Técnica e Preço",
    "Maior Lance",
    "Maior Oferta",
]

PROCESSO_RE = re.compile(
    r"processo\s*(?:administrativo)?\s*n[ºo°.]*\s*[:\-]?\s*([\d./\-]{4,20})",
    re.IGNORECASE,
)
ANO_RE = re.compile(r"\b(20\d{2})\b")
MUNICIPIO_RE = re.compile(
    r"(?:MUNIC[ÍI]PIO\s+DE|PREFEITURA\s+MUNICIPAL\s+DE|PREFEITURA\s+DE)\s+([A-ZÀ-Ú][A-ZÀ-Ú\s']{2,40}?)(?:[\n\r,\.\-]|\s{2,}|$)",
    re.IGNORECASE,
)


def _find_first(patterns, text):
    for p in patterns:
        if re.search(re.escape(p), text, re.IGNORECASE):
            return p
    return None


def extract_metadata(text: str, pdf_path) -> dict:
    sample = text[:8000]  # primeiras páginas costumam ter os dados de cabeçalho

    metadata = {
        "municipio": None,
        "modalidade": _find_first(MODALIDADES, sample),
        "ano": None,
        "processo": None,
        "tipo": _find_first(TIPOS, sample),
    }

    match = PROCESSO_RE.search(sample)
    if match:
        metadata["processo"] = match.group(1).strip(" .-")

    match = MUNICIPIO_RE.search(sample)
    if match:
        metadata["municipio"] = " ".join(match.group(1).split()).title()

    anos = ANO_RE.findall(sample)
    if anos:
        metadata["ano"] = int(anos[0])
    elif metadata["processo"]:
        # tenta pegar o ano do próprio número do processo, ex: "001/2026"
        m = re.search(r"20\d{2}", metadata["processo"])
        if m:
            metadata["ano"] = int(m.group(0))

    sidecar = pdf_path.with_suffix(".json")
    if sidecar.exists():
        overrides = json.loads(sidecar.read_text(encoding="utf-8"))
        metadata.update({k: v for k, v in overrides.items() if v not in (None, "")})

    return metadata
