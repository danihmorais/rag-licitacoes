from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any, Iterable
from config import SETTINGS

ARTIGO_RE = re.compile(r"(?im)^(?P<ref>Art\.?\s+\d+[A-Za-zº°-]*)\s*[—–-]?")
SUMULA_RE = re.compile(r"(?im)^(?P<ref>S[úu]mula\s+(?:Vinculante\s+)?\d+[A-Za-zº°-]*)\s*[—–:-]?")
TEMA_RE = re.compile(r"(?im)^(?P<ref>Tema\s+\d+[A-Za-zº°-]*)\s*[—–:-]?")
JUR_RE = re.compile(r"(?im)^(?:TRIBUNAL\s*:\s*(?P<tribunal>[^\n]+)\n)?(?:PROCESSO\s*:\s*(?P<processo>[^\n]+)\n)?")

@dataclass
class TextChunk:
    text: str
    unit_kind: str
    unit_ref: str | None
    unit_id: str
    chunk_index: int
    page: int | None
    page_end: int | None
    start: int
    end: int
    metadata: dict[str, Any]

def _units(text: str) -> list[dict[str, Any]]:
    matches: list[tuple[int, str, str | None]] = []
    for regex, kind in ((ARTIGO_RE, "artigo"), (SUMULA_RE, "sumula"), (TEMA_RE, "tema")):
        for m in regex.finditer(text):
            matches.append((m.start(), kind, m.groupdict().get("ref")))
    matches.sort(key=lambda x: x[0])
    if not matches:
        return [{"start": 0, "end": len(text), "kind": "documento", "ref": None}]
    units = []
    for i, (start, kind, ref) in enumerate(matches):
        end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        units.append({"start": start, "end": end, "kind": kind, "ref": ref})
    return units

def _split(text: str, size: int, overlap: int) -> list[tuple[str, int, int]]:
    if len(text) <= size:
        return [(text, 0, len(text))]
    out = []
    pos = 0
    while pos < len(text):
        end = min(len(text), pos + size)
        if end < len(text):
            cut = max(text.rfind("\n", pos, end), text.rfind(". ", pos, end), text.rfind(" ", pos, end))
            if cut > pos + int(size * 0.55):
                end = cut + 1
        piece = text[pos:end].strip()
        if piece:
            local_start = text.find(piece, pos)
            local_start = local_start if local_start >= 0 else pos
            local_end = local_start + len(piece)
            out.append((piece, local_start, local_end))
        if end >= len(text):
            break
        pos = max(end - overlap, pos + 1)
    return out

def _page_at(pages: Iterable[str], absolute: int) -> int | None:
    acc = 0
    for i, page in enumerate(pages, 1):
        nxt = acc + len(page)
        if absolute < nxt:
            return i
        acc = nxt
    return None

def build_structural_chunks(text: str, pages: list[str] | None = None, metadata: dict[str, Any] | None = None) -> list[TextChunk]:
    metadata = dict(metadata or {})
    pages = pages or [text]
    chunks: list[TextChunk] = []
    for unit_no, unit in enumerate(_units(text)):
        body = text[unit["start"]:unit["end"]]
        ref = unit.get("ref")
        pieces = _split(body, SETTINGS.chunk_size, SETTINGS.chunk_overlap)
        for idx, (piece, local_start, local_end) in enumerate(pieces):
            absolute_start = unit["start"] + local_start
            absolute_end = unit["start"] + local_end
            unit_id = f"{unit['kind']}:{ref or 'pos'}:{unit['start']}"
            chunks.append(TextChunk(
                text=piece,
                unit_kind=unit["kind"],
                unit_ref=ref,
                unit_id=unit_id,
                chunk_index=idx,
                page=_page_at(pages, absolute_start),
                page_end=_page_at(pages, max(absolute_start, absolute_end - 1)),
                start=absolute_start,
                end=absolute_end,
                metadata=metadata,
            ))
    return chunks
