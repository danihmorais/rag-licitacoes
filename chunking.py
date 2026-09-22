import re

import config
from langchain_text_splitters import RecursiveCharacterTextSplitter

ARTIGO_RE = re.compile(
    r"^[ \t]*(Art(?:igo)?\.?[ \t]+\d+[ºo°]?(?:-[A-Z])?\.?)(?=\s|$)",
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
HEADER_RE = re.compile(
    r"^\s*((?:LEI|DECRETO|DECRETO-LEI|PORTARIA|RESOLUÇÃO|RESOLUCAO|INSTRUÇÃO|INSTRUCAO|EMENDA CONSTITUCIONAL|LIVRO|PARTE|TÍTULO|TITULO|CAPÍTULO|CAPITULO|SEÇÃO|SECAO|SUBSEÇÃO|SUBSECAO|ANEXO)\b.*)$",
    re.IGNORECASE,
)
CHILD_RE = re.compile(
    r"(?m)^[ \t]*(§\s*\d+[ºo]?|§\s*[uú]nico|[IVXLCDM]+\s*[.)–—-]|[a-z]\s*[.)–—-]|\d+\s*[.)–—-])[ \t]*",
    re.IGNORECASE,
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


def _headers_before(text, start):
    prefix = text[:start]
    headers = []
    for line in prefix.splitlines():
        normalized = re.sub(r'\s+', ' ', line).strip()
        if HEADER_RE.match(normalized):
            headers.append(normalized)
    return headers[-4:]


def _article_children(article_text):
    matches = list(CHILD_RE.finditer(article_text))
    if not matches:
        return article_text.strip(), []
    caput = article_text[:matches[0].start()].strip()
    children = []
    current_level1 = None
    current_level2 = None
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(article_text)
        value = article_text[match.start():end].strip()
        ref = match.group(1).strip()
        if not value:
            continue

        kind = (
            'paragrafo'
            if ref.startswith('§')
            else 'inciso'
            if re.match(r'^[IVXLCDM]+', ref, re.I)
            else 'alinea'
            if re.match(r'^[a-z]', ref, re.I)
            else 'item'
        )

        if kind in {'paragrafo', 'inciso'}:
            # Parágrafo e inciso são níveis de primeiro grau e reiniciam
            # os descendentes (alíneas e itens) do bloco anterior.
            current_level1 = ref
            current_level2 = None
            path_tail = [ref]
        elif kind == 'alinea':
            # A alínea pertence ao último parágrafo/inciso visto.
            current_level2 = ref
            path_tail = [ref] if current_level1 is None else [current_level1, ref]
        else:
            # O item pertence à última alínea. Se o texto vier sem alínea,
            # preservamos a melhor hierarquia disponível como fallback.
            if current_level2 is not None:
                path_tail = [x for x in (current_level1, current_level2, ref) if x]
            elif current_level1 is not None:
                path_tail = [current_level1, ref]
            else:
                path_tail = [ref]

        children.append((kind, ref, value, match.start(), path_tail))
    return caput, children


def _split_text(text, max_size, overlap):
    if max_size <= 0:
        raise ValueError('max_size deve ser maior que zero')
    if len(text) <= max_size:
        return [text]
    effective_overlap = min(overlap, max(0, max_size - 1))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_size,
        chunk_overlap=effective_overlap,
        separators=['\n\n', '\n', '. ', '; ', ' ', ''],
    )
    return [piece for piece in splitter.split_text(text) if piece.strip()]


def _fit_child_prefix(prefix, child_text, max_size):
    if len(prefix) + len(child_text) + 1 <= max_size:
        return prefix
    header, _, caput = prefix.partition('\n')
    body_budget = min(len(child_text), max(1, max_size // 2))
    prefix_budget = max(1, max_size - body_budget - 1)
    if len(header) > prefix_budget:
        return header[:prefix_budget].rstrip()
    if len(header) + 1 >= prefix_budget:
        return header
    remaining = prefix_budget - len(header) - 1
    original_caput = caput.rstrip()
    if len(original_caput) > remaining:
        caput = original_caput[:max(0, remaining - 1)].rstrip(' .,:;-') + ('…' if remaining > 0 else '')
    else:
        caput = original_caput
    return f'{header}\n{caput}'.strip()

def _split_child(child_text, prefix, max_size, overlap):
    prefix = _fit_child_prefix(prefix, child_text, max_size)
    available = max(1, max_size - len(prefix) - 1)
    if len(child_text) <= available:
        return [child_text]
    return _split_text(child_text, available, overlap)


def _article_units(text):
    matches = list(ARTIGO_RE.finditer(text))
    if not matches:
        return None
    units = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        article_text = text[start:end].strip()
        if not article_text:
            continue
        units.append({
            'kind': 'artigo',
            'ref': match.group(1).strip(),
            'start': start,
            'text': article_text,
            'headers': _headers_before(text, start),
        })
    return units


def _units(text):
    if JURISPRUDENCIA_RE.search(text):
        process_match = re.search(r"^PROCESSO:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        return [{
            'kind': 'jurisprudencia',
            'ref': process_match.group(1).strip() if process_match else None,
            'start': 0,
            'text': text.strip(),
            'headers': [],
        }]
    article_units = _article_units(text)
    if article_units:
        return article_units
    sumula_units = _find(text, SUMULA_RE, 'sumula')
    if sumula_units:
        for unit in sumula_units:
            unit['headers'] = _headers_before(text, unit['start'])
        return sumula_units
    tema_units = _find(text, TEMA_RE, 'tema')
    if tema_units:
        for unit in tema_units:
            unit['headers'] = _headers_before(text, unit['start'])
        return tema_units
    return [{'kind': 'generic', 'ref': None, 'start': 0, 'text': text.strip(), 'headers': []}]



SEMANTIC_SOURCE_ROLES = {
    'jurisprudencia',
    'jurisprudencia_controle',
    'orientacao_oficial',
    'doutrina',
}
SEMANTIC_DOCUMENT_TYPES = {
    'jurisprudencia',
    'acordao',
    'decisao',
    'sumula',
    'tema',
    'materia',
    'artigo',
    'noticia',
    'manual',
    'guia',
    'orientacao',
    'portal_oficial',
    'doutrina',
}
NORMATIVE_DOCUMENT_TYPES = {
    'norma',
    'lei',
    'lei_ordinaria',
    'lei_complementar',
    'decreto',
    'decreto_lei',
    'portaria',
    'resolucao',
    'instrucao_normativa',
    'ato_normativo',
    'emenda_constitucional',
    'constituicao',
    'constituicao_estadual',
}


def _is_normative_document(full_text, metadata=None):
    metadata = metadata or {}
    source_role = str(metadata.get('source_role') or '').strip().casefold()
    tipo_documento = str(metadata.get('tipo_documento') or '').strip().casefold()
    if source_role == 'norma' or tipo_documento in NORMATIVE_DOCUMENT_TYPES:
        return True
    if re.search(
        r'(?im)^\s*(?:LEI\s+(?:COMPLEMENTAR\s+)?n?[ºo°.]*|DECRETO(?:-LEI)?\s+n?[ºo°.]*|'
        r'PORTARIA\s+n?[ºo°.]*|RESOLU(?:ÇÃO|CAO)\s+n?[ºo°.]*|INSTRU(?:ÇÃO|CAO)\s+NORMATIVA\b|'
        r'EMENDA\s+CONSTITUCIONAL\b|CONSTITUI(?:ÇÃO|CAO)\b)',
        full_text[:2000],
    ):
        return True
    return False


def _should_use_ai_semantic(full_text, metadata=None):
    if not config.AI_CHUNKING_ENABLED or len(full_text.strip()) < config.AI_CHUNKING_MIN_CHARS:
        return False
    metadata = metadata or {}
    source_role = str(metadata.get('source_role') or '').strip().casefold()
    tipo_documento = str(metadata.get('tipo_documento') or '').strip().casefold()
    if _is_normative_document(full_text, metadata):
        return False
    if source_role in SEMANTIC_SOURCE_ROLES or tipo_documento in SEMANTIC_DOCUMENT_TYPES:
        return True
    if JURISPRUDENCIA_RE.search(full_text):
        return True
    if re.search(r'(?im)^\s*FONTE:\s*.+\n\s*T[IÍ]TULO:\s*.+\n\s*DATA[_ ]PUBLICACAO\s*:', full_text):
        return True
    return False


def _build_ai_semantic_chunks(full_text, max_size, metadata, semantic_provider=None):
    from llm.semantic_chunker import SemanticChunkingError, build_semantic_chunks

    unit_kind = str(metadata.get('tipo_documento') or '').strip() or (
        'jurisprudencia' if JURISPRUDENCIA_RE.search(full_text) else 'materia'
    )
    unit_ref = (
        str(metadata.get('processo') or '').strip()
        or str(metadata.get('source_id') or '').strip()
        or None
    )
    try:
        return build_semantic_chunks(
            full_text,
            max_size,
            unit_kind=unit_kind,
            unit_ref=unit_ref,
            provider=semantic_provider,
            window_chars=config.AI_CHUNKING_WINDOW_CHARS,
            min_chars=config.AI_CHUNKING_MIN_CHARS,
            attempts=config.AI_CHUNKING_ATTEMPTS,
            prompt_version=config.AI_CHUNKING_PROMPT_VERSION,
        )
    except SemanticChunkingError:
        if config.AI_CHUNKING_REQUIRED:
            raise
        return []


def build_structural_chunks(full_text, max_size, overlap, *, metadata=None, semantic_provider=None):
    if max_size <= 0:
        raise ValueError('max_size deve ser maior que zero')
    if overlap < 0 or overlap >= max_size:
        raise ValueError('overlap deve ser maior ou igual a zero e menor que max_size')
    if _should_use_ai_semantic(full_text, metadata):
        chunks = _build_ai_semantic_chunks(full_text, max_size, metadata or {}, semantic_provider=semantic_provider)
        if chunks:
            return chunks

    output = []
    ref_counts = {}
    units = _units(full_text)
    for unit in units:
        ref = unit.get('ref')
        if ref:
            key = (unit['kind'], ref)
            ref_counts[key] = ref_counts.get(key, 0) + 1

    for unit in units:
        if not unit['text'].strip():
            continue
        ref = unit.get('ref')
        unit_id = f"{unit['kind']}:{ref}" if ref else f"{unit['kind']}:{unit['start']}"
        if ref and ref_counts.get((unit['kind'], ref), 0) > 1:
            unit_id = f"{unit_id}:{unit['start']}"
        headers = list(unit.get('headers') or [])
        if unit['kind'] != 'artigo':
            pieces = _split_text(unit['text'], max_size, overlap)
            position = 0
            for index, piece in enumerate(pieces):
                found = unit['text'].find(piece, max(0, position - overlap))
                uncertain = found < 0
                found = position if uncertain else found
                output.append({
                    'text': piece,
                    'full_unit_text': piece if len(unit['text']) <= max_size else None,
                    'page_content': piece,
                    'unit_kind': unit['kind'],
                    'unit_ref': ref,
                    'unit_id': unit_id,
                    'chunk_index': index,
                    'unit_length': len(unit['text']),
                    'start': unit['start'] + found,
                    'page_uncertain': uncertain,
                    'hierarchy_headers': headers,
                    'hierarchy_path': headers + ([ref] if ref else []),
                    'parent_caput': None,
                    'segment_kind': unit['kind'],
                    'segment_ref': ref,
                })
                position = max(found + len(piece) - overlap, found + 1)
            continue

        caput, children = _article_children(unit['text'])
        article_ref = ref or 'Artigo'
        article_header = [*headers, article_ref]
        if not children:
            pieces = _split_text(unit['text'], max_size, overlap)
            position = 0
            for index, piece in enumerate(pieces):
                found = unit['text'].find(piece, max(0, position - overlap))
                uncertain = found < 0
                found = position if uncertain else found
                output.append({
                    'text': piece,
                    'full_unit_text': piece if len(unit['text']) <= max_size else None,
                    'page_content': piece,
                    'unit_kind': 'artigo',
                    'unit_ref': ref,
                    'unit_id': unit_id,
                    'chunk_index': index,
                    'unit_length': len(unit['text']),
                    'start': unit['start'] + found,
                    'page_uncertain': uncertain,
                    'hierarchy_headers': headers,
                    'hierarchy_path': article_header,
                    'parent_caput': caput,
                    'segment_kind': 'caput',
                    'segment_ref': None,
                })
                position = max(found + len(piece) - overlap, found + 1)
            continue

        caput_chunks = _split_text(caput, max_size, overlap)
        caput_index = 0
        caput_position = 0
        for piece in caput_chunks:
            found = caput.find(piece, max(0, caput_position - overlap))
            uncertain = found < 0
            found = caput_position if uncertain else found
            output.append({
                'text': piece,
                'full_unit_text': caput if len(caput) <= max_size else None,
                'page_content': piece,
                'unit_kind': 'artigo',
                'unit_ref': ref,
                'unit_id': unit_id,
                'chunk_index': caput_index,
                'unit_length': len(unit['text']),
                'start': unit['start'] + found,
                'page_uncertain': uncertain,
                'hierarchy_headers': headers,
                'hierarchy_path': article_header + ['CAPUT'],
                'parent_caput': caput,
                'segment_kind': 'caput',
                'segment_ref': None,
            })
            caput_position = max(found + len(piece) - overlap, found + 1)
            caput_index += 1

        next_index = max(1, caput_index)
        for child_index, (kind, child_ref, child_text, child_start, child_path_tail) in enumerate(children):
            child_path = article_header + child_path_tail
            child_prefix = f"{' > '.join(child_path)}\n{caput}".strip()
            child_prefix = _fit_child_prefix(child_prefix, child_text, max_size)
            pieces = _split_child(child_text, child_prefix, max_size, overlap)
            position = 0
            for local_index, piece in enumerate(pieces):
                relative = child_text.find(piece, max(0, position - overlap))
                uncertain = relative < 0
                relative = position if uncertain else relative
                rendered = f"{child_prefix}\n{piece}".strip()
                output.append({
                    'text': rendered,
                    'full_unit_text': None,
                    'page_content': rendered,
                    'unit_kind': 'artigo',
                    'unit_ref': ref,
                    'unit_id': unit_id,
                    'chunk_index': next_index + local_index,
                    'unit_length': len(unit['text']),
                    'start': unit['start'] + child_start + relative,
                    'page_uncertain': uncertain,
                    'hierarchy_headers': headers,
                    'hierarchy_path': child_path,
                    'parent_caput': caput,
                    'segment_kind': kind,
                    'segment_ref': child_ref,
                    'child_index': child_index,
                })
                position = max(relative + len(piece) - overlap, relative + 1)
            next_index += len(pieces)
    return output
