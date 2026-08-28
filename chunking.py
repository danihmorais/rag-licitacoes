import re
from langchain_text_splitters import RecursiveCharacterTextSplitter

ARTIGO_RE = re.compile(r"^[ \t]*(Art(?:igo)?\.?[ \t]+\d+[ºo°]?(?:-[A-Z])?\.?(?=\s|$))", re.IGNORECASE | re.MULTILINE)
SUMULA_RE = re.compile(r"^[ \t]*(S[uú]mula\s+n?[ºo°.]*\s*\d+|Enunciado\s+n?[ºo°.]*\s*\d+)\b", re.IGNORECASE | re.MULTILINE)


def _find(text, rx, kind):
    matches = list(rx.finditer(text))
    if len(matches) < 2:
        return None
    out = []
    if matches[0].start() > 0 and text[:matches[0].start()].strip():
        out.append({'kind': 'generic', 'ref': None, 'start': 0, 'text': text[:matches[0].start()].strip()})
    for i, match in enumerate(matches):
        start = match.start(); end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[start:end].strip()
        if value:
            out.append({'kind': kind, 'ref': match.group(1).strip(), 'start': start, 'text': value})
    return out


def _units(text):
    article_units = _find(text, ARTIGO_RE, 'artigo')
    if article_units and sum(item['kind'] == 'artigo' for item in article_units) >= 2:
        return article_units
    sumula_units = _find(text, SUMULA_RE, 'sumula')
    if sumula_units and sum(item['kind'] == 'sumula' for item in sumula_units) >= 2:
        return sumula_units
    return [{'kind': 'generic', 'ref': None, 'start': 0, 'text': text}]


def build_structural_chunks(full_text, max_size, overlap):
    splitter = RecursiveCharacterTextSplitter(chunk_size=max_size, chunk_overlap=overlap, separators=['\n\n', '\n', '. ', '; ', ' ', ''])
    output = []
    for unit in _units(full_text):
        full = unit['text']; pieces = [full] if len(full) <= max_size else splitter.split_text(full)
        position = 0; unit_id = f"{unit['kind']}:{unit.get('ref') or unit['start']}"
        for index, piece in enumerate(pieces):
            if not piece.strip(): continue
            found = full.find(piece, max(0, position - overlap)); found = position if found < 0 else found
            output.append({'text': piece, 'full_unit_text': piece if len(full) <= max_size else None,
                           'unit_kind': unit['kind'], 'unit_ref': unit['ref'], 'unit_id': unit_id,
                           'chunk_index': index, 'unit_length': len(full), 'start': unit['start'] + found})
            position = found + max(1, len(piece) - overlap)
    return output
