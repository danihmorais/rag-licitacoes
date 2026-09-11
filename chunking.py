import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

ARTIGO_RE = re.compile(
    r"^[ \t]*(Art(?:igo)?\.?[ \t]+\d+[ºo°]?(?:-[A-Z])?\.?(?=\s|$))",
    re.IGNORECASE | re.MULTILINE,
)
SUMULA_RE = re.compile(
    r"^[ \t]*(S[uú]mula(?:\s+Vinculante)?\s+n?[ºo°.]*\s*\d+|Enunciado\s+n?[ºo°.]*\s*\d+)\b",
    re.IGNORECASE | re.MULTILINE,
)
JURISPRUDENCIA_RE = re.compile(
    r"^\s*TRIBUNAL:\s*.+\nPROCESSO:\s*.+$",
    re.IGNORECASE | re.MULTILINE,
)
TEMA_RE = re.compile(
    r"^[ \t]*(Tema\s+n?[ºo°.]*\s*\d+)\b",
    re.IGNORECASE | re.MULTILINE,
)


def _find(text, rx, kind):
    matches = list(rx.finditer(text))
    if not matches:
        return None
    out = []
    if matches[0].start() > 0 and text[:matches[0].start()].strip():
        out.append({'kind': 'generic', 'ref': None, 'start': 0, 'text': text[:matches[0].start()].strip()})
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = text[start:end].strip()
        if value:
            out.append({'kind': kind, 'ref': match.group(1).strip(), 'start': start, 'text': value})
    return out


def _units(text):
    if JURISPRUDENCIA_RE.search(text):
        process_match = re.search(r"^PROCESSO:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        return [{
            'kind': 'jurisprudencia',
            'ref': process_match.group(1).strip() if process_match else None,
            'start': 0,
            'text': text,
        }]
    article_units = _find(text, ARTIGO_RE, 'artigo')
    if article_units:
        return article_units
    sumula_units = _find(text, SUMULA_RE, 'sumula')
    if sumula_units:
        return sumula_units
    tema_units = _find(text, TEMA_RE, 'tema')
    if tema_units:
        return tema_units
    return [{'kind': 'generic', 'ref': None, 'start': 0, 'text': text}]


def build_structural_chunks(full_text, max_size, overlap):
    if max_size <= 0:
        raise ValueError('max_size deve ser maior que zero')
    if overlap < 0 or overlap >= max_size:
        raise ValueError('overlap deve ser maior ou igual a zero e menor que max_size')

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_size,
        chunk_overlap=overlap,
        separators=['\n\n', '\n', '. ', '; ', ' ', ''],
    )
    output = []
    for unit in _units(full_text):
        full = unit['text']
        pieces = [full] if len(full) <= max_size else splitter.split_text(full)
        position = 0
        unit_id = f"{unit['kind']}:{unit.get('ref') or unit['start']}"
        for index, piece in enumerate(pieces):
            if not piece.strip():
                continue
            found = full.find(piece, position)
            if found < 0 and overlap:
                found = full.find(piece, max(0, position - overlap))
            if found < 0:
                found = position
            output.append(
                {
                    'text': piece,
                    'full_unit_text': piece if len(full) <= max_size else None,
                    'unit_kind': unit['kind'],
                    'unit_ref': unit['ref'],
                    'unit_id': unit_id,
                    'chunk_index': index,
                    'unit_length': len(full),
                    'start': unit['start'] + found,
                }
            )
            position = found + max(1, len(piece) - overlap)
    return output
