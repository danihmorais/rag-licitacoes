import re
from langchain_text_splitters import RecursiveCharacterTextSplitter

ARTIGO_RE = re.compile(r'(?m)^\s*(Art(?:igo)?\.?\s*\d+[ºo°]?(?:-[A-Z])?\.?)\s')
SUMULA_RE = re.compile(r'(?m)^\s*(S[uú]mula\s+n?[ºo°.]*\s*\d+|Enunciado\s+n?[ºo°.]*\s*\d+)\b', re.I)
PARAGRAFO_RE = re.compile(r'(?m)^\s*(Parágrafo\s+(?:único|\d+[ºo°]?)\.?|§\s*\d+[ºo°]?)\s')
INCISO_RE = re.compile(r'(?m)^\s*([IVXLCDM]+)\s*[-–—]\s+')


def _find(text, rx, kind):
    matches = list(rx.finditer(text))
    if len(matches) < 2:
        return None
    out = []
    if matches[0].start() > 0 and text[:matches[0].start()].strip():
        out.append({'kind': 'generic', 'ref': None, 'start': 0, 'text': text[:matches[0].start()].strip()})
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[start:end].strip()
        if value:
            out.append({'kind': kind, 'ref': match.group(1).strip(), 'start': start, 'text': value})
    return out


def _units(text):
    candidates = []
    for rx, kind in ((ARTIGO_RE, 'artigo'), (SUMULA_RE, 'sumula')):
        units = _find(text, rx, kind)
        if units:
            candidates.append((sum(x['kind'] == kind for x in units), units))
    if candidates:
        _, units = max(candidates, key=lambda x: x[0])
        if len(units) >= 4:
            return units
    return [{'kind': 'generic', 'ref': None, 'start': 0, 'text': text}]


def _annotate_substructure(text):
    # Preserva marcadores estruturais no texto sem separar parágrafos/incisos
    # de seu artigo: isso melhora recuperação lexical e evita contexto jurídico órfão.
    return text


def build_structural_chunks(full_text, max_size, overlap):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_size,
        chunk_overlap=overlap,
        separators=['\n\n', '\n', '. ', '; ', ' ', ''],
    )
    output = []
    for unit in _units(full_text):
        full = _annotate_substructure(unit['text'])
        pieces = [full] if len(full) <= max_size else splitter.split_text(full)
        position = 0
        unit_id = f"{unit['kind']}:{unit.get('ref') or unit['start']}"
        for index, piece in enumerate(pieces):
            if not piece.strip():
                continue
            found = full.find(piece, max(0, position - overlap))
            found = position if found < 0 else found
            output.append({
                'text': piece,
                'full_unit_text': piece if len(full) <= max_size else None,
                'unit_kind': unit['kind'],
                'unit_ref': unit['ref'],
                'unit_id': unit_id,
                'chunk_index': index,
                'unit_length': len(full),
                'start': unit['start'] + found,
            })
            position = found + max(1, len(piece) - overlap)
    return output
