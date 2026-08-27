"""Chunking estrutural para legislação, jurisprudência e editais."""
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

ARTIGO_RE = re.compile(
    r"(?m)^\s*(Art(?:igo)?\.?\s*\d+[ºo°]?-?[A-Z]?\.?)\s"
)
SUMULA_RE = re.compile(
    r"(?m)^\s*(S[uú]mula\s*n?[ºo°.]*\s*\d+|Enunciado\s*n?[ºo°.]*\s*\d+)\b",
    re.IGNORECASE,
)

_MARKERS = ((ARTIGO_RE, "artigo"), (SUMULA_RE, "sumula"))


def _find_units(text: str, marker_re: re.Pattern, kind: str):
    matches = list(marker_re.finditer(text))
    if len(matches) < 2:
        return None

    units = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()]
        if preamble.strip():
            units.append({"kind": "generic", "ref": None, "start": 0, "text": preamble.strip()})

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk_text = text[start:end].strip()
        if chunk_text:
            units.append({
                "kind": kind,
                "ref": match.group(1).strip(),
                "start": start,
                "text": chunk_text,
            })
    return units


def _detect_units(full_text: str):
    """Detecta estrutura jurídica apenas quando ela parece dominar o documento."""
    candidates = []
    for marker_re, kind in _MARKERS:
        units = _find_units(full_text, marker_re, kind)
        if units:
            structured_count = sum(1 for unit in units if unit["kind"] == kind)
            candidates.append((structured_count, kind, units))

    if candidates:
        structured_count, _kind, units = max(candidates, key=lambda item: item[0])
        # Evita interpretar referências isoladas a artigos dentro de um edital/boletim
        # como se fossem a estrutura principal do documento.
        if structured_count >= 4:
            return units

    return [{"kind": "generic", "ref": None, "start": 0, "text": full_text}]


def build_structural_chunks(full_text: str, max_size: int, overlap: int):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    for unit in _detect_units(full_text):
        full_unit_text = unit["text"]
        if len(full_unit_text) <= max_size:
            chunks.append({
                "text": full_unit_text,
                "full_unit_text": full_unit_text,
                "unit_kind": unit["kind"],
                "unit_ref": unit["ref"],
                "start": unit["start"],
            })
            continue

        for piece in splitter.split_text(full_unit_text):
            # Em documento genérico não existe uma unidade pai recuperável;
            # o próprio fragmento é o contexto. Para artigo/súmula, mantemos
            # a unidade completa para recomposição posterior.
            context_text = full_unit_text if unit["kind"] in {"artigo", "sumula"} else piece
            chunks.append({
                "text": piece,
                "full_unit_text": context_text,
                "unit_kind": unit["kind"],
                "unit_ref": unit["ref"],
                "start": unit["start"],
            })

    return chunks
