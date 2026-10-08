import bisect
import re
import unicodedata
from functools import lru_cache
from dataclasses import dataclass, field
from typing import Any, Callable

import config
from langchain_text_splitters import RecursiveCharacterTextSplitter


# Número de artigo: 5, 5º, 5-A, 337-AB, 1.045 (milhar). O ponto final faz parte da referência.
_ART_NUMBER = r"(?:\d{1,3}(?:\.\d{3})+|\d+)[ºo°]?(?:-[A-Za-z]{1,3})?\.?"
ARTIGO_RE = re.compile(
    rf"^[ \t]*(Art(?:igo)?\.?[ \t]*{_ART_NUMBER})(?=\s|$)",
    re.IGNORECASE | re.MULTILINE,
)
ARTIGO_INLINE_RE = re.compile(
    rf"(?<![\w])(Art(?:igo)?\.?[ \t]+{_ART_NUMBER})(?=\s|$)",
    re.IGNORECASE,
)

STRUCT_HEADING_RE = re.compile(
    r"^[ \t]*(?:LIVRO|PARTE|T[IÍ]TULO|CAP[IÍ]TULO|SE[CÇ][AÃ]O|SUBSE[CÇ][AÃ]O|ANEXO)\b[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)

# A visão usada apenas para detectar estrutura jamais altera o comprimento do documento.
# Assim os offsets calculados no texto normalizado continuam válidos em full_text.
OCR_STRUCTURE_REPLACEMENTS = (
    (re.compile(r"\bArtig0\b", re.I), "Artigo"),
    (re.compile(r"\bArt1go\b", re.I), "Artigo"),
    (re.compile(r"\bArt1g0\b", re.I), "Artigo"),
    (re.compile(r"\bParagraf0\b", re.I), "Paragrafo"),
    (re.compile(r"\bunic0\b", re.I), "unico"),
    (re.compile(r"\bCAP[IÍ]TUL0\b", re.I), "CAPITULO"),
    (re.compile(r"\bT[IÍ]TUL0\b", re.I), "TITULO"),
)

def _ocr_structure_view(text):
    def replace_if_same_length(match, replacement):
        return replacement if len(replacement) == len(match.group(0)) else match.group(0)

    for pattern, replacement in OCR_STRUCTURE_REPLACEMENTS:
        text = pattern.sub(lambda match: replace_if_same_length(match, replacement), text)
    return text


ARTICLE_CITATION_TAIL_RE = re.compile(
    r"^[ \t]+(?:da|do|das|dos|de)[ \t]+(?:CF|C\.F\.?|Constitui(?:ção|cao)|Lei|C[oó]digo|CPC|CC|CLT|STF|STJ|TCU|TCESP|TJSP)\b",
    re.I,
)
ARTICLE_CITATION_PREFIX_RE = re.compile(
    r"(?:\b(?:o|a|os|as|no|na|nos|nas|do|da|dos|das|em|ao|à|conforme|segundo|previsto|disposto|artigo|arts?)\s*)$",
    re.I,
)
AMENDMENT_CONTEXT_RE = re.compile(
    r"(?i)(?:passa\s+a\s+vigorar|fica\s+(?:acrescido|acrescida|acrescentado|acrescentada|inserido|inserida|incluido|incluida)|acrescenta(?:-se)?|inclui(?:-se)?|reda[cç][aã]o|passa\s+a\s+vigorar\s+com\s+a\s+seguinte\s+reda[cç][aã]o)"
)
SUMULA_RE = re.compile(
    r"^[ \t]*(S[uú]mula(?:\s+Vinculante)?\s+n?[ºo°.]*\s*\d+|Enunciado\s+n?[ºo°.]*\s*\d+)\b",
    re.I | re.M,
)
JURISPRUDENCIA_RE = re.compile(r"^[ \t]*TRIBUNAL:\s*.+$", re.I | re.M)
TEMA_RE = re.compile(r"^[ \t]*(Tema\s+n?[ºo°.]*\s*\d+)\b", re.I | re.M)
HEADER_RE = re.compile(
    r"^\s*((?:LEI|DECRETO-LEI|DECRETO|PORTARIA|RESOLUÇÃO|RESOLUCAO|INSTRUÇÃO|INSTRUCAO|EMENDA CONSTITUCIONAL|LIVRO|PARTE|TÍTULO|TITULO|CAPÍTULO|CAPITULO|SEÇÃO|SECAO|SUBSEÇÃO|SUBSECAO|ANEXO)\b.*)$",
    re.I,
)

PARAGRAFO_RE = (
    r"(?:§\s*\d+[ºo°]?(?:-[A-Za-z])?|§\s*[uú]nico"
    r"|par[aá]graf[o0]\s+(?:[uú]nic[o0]|\d+[ºo°]?(?:-[A-Za-z])?)(?:\s*[.:–—-])?)"
)

def _roman_to_text(number):
    values = (
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    )
    out = []
    for value, symbol in values:
        count, number = divmod(number, value)
        out.append(symbol * count)
    return "".join(out)

_ROMAN_FORMS = tuple(_roman_to_text(number) for number in range(1, 101))
ROMAN_RE = r"(?:%s)" % "|".join(sorted(_ROMAN_FORMS, key=lambda item: (-len(item), item)))
_ROMAN_SUFFIX_RE = rf"(?:{ROMAN_RE})(?:-[A-Za-z]{{1,3}})?"

_ROMAN_MARKER = rf"(?-i:{_ROMAN_SUFFIX_RE})\s*(?:\)|[.–—-](?=\s|$))"
_ALINEA_MARKER = (
    r"(?:\([A-Za-z]{1,3}\)|[A-Za-z]{1,3}\s*\))"
    r"|(?:[A-Za-z]{1,3}\s*[–—-](?=\s|$))"
)
_ITEM_MARKER = r"(?:\(\d{1,3}\)|\d{1,3}\s*(?:\)|[.–—-](?=\s|$)))"
_NAMED_INCISO_MARKER = rf"(?:Inciso)\s+(?-i:{_ROMAN_SUFFIX_RE})\s*(?:\)|[.–—-])?(?=\s|$)"
_NAMED_ALINEA_MARKER = rf"(?:Al[ií]nea)\s+[A-Za-z]{{1,3}}\s*(?:\)|[.–—-])?(?=\s|$)"

_CHILD_MARKER = (
    rf"{PARAGRAFO_RE}"
    rf"|{_NAMED_INCISO_MARKER}"
    rf"|{_NAMED_ALINEA_MARKER}"
    rf"|{_ROMAN_MARKER}"
    rf"|{_ALINEA_MARKER}"
    rf"|{_ITEM_MARKER}"
)

# Início de linha ou pontuação anterior cobre tanto PDF convencional quanto PDF achatado.
CHILD_RE = re.compile(
    rf"(?m)(?:(?<=^)|(?<=[\f;:!?»”])|(?<!\d)(?<=\.))[ \t]*({_CHILD_MARKER})[ \t]*",
    re.IGNORECASE,
)
CHILD_INLINE_RE = CHILD_RE


def _find(text, rx, kind):
    matches = list(rx.finditer(text))
    if not matches:
        return None
    out = []
    if matches[0].start() > 0 and text[:matches[0].start()].strip():
        out.append({"kind": "generic", "ref": None, "start": 0, "text": text[:matches[0].start()].strip()})
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[start:end].strip()
        if value:
            out.append({"kind": kind, "ref": match.group(1).strip(), "start": start, "text": value})
    return out


_HEADER_LEVELS = (
    (
        "norma",
        0,
        re.compile(
            r"^\s*(?:LEI|DECRETO(?:-LEI)?|PORTARIA|RESOLUÇÃO|RESOLUCAO|INSTRUÇÃO|INSTRUCAO|EMENDA CONSTITUCIONAL|CONSTITUIÇÃO|CONSTITUICAO|LEI COMPLEMENTAR)\b.*$",
            re.I,
        ),
    ),
    ("parte", 1, re.compile(r"^\s*PARTE\b.*$", re.I)),
    ("livro", 2, re.compile(r"^\s*LIVRO\b.*$", re.I)),
    ("titulo", 3, re.compile(r"^\s*T[IÍ]TULO\b.*$", re.I)),
    ("capitulo", 4, re.compile(r"^\s*CAP[IÍ]TULO\b.*$", re.I)),
    ("secao", 5, re.compile(r"^\s*SE[CÇ][AÃ]O\b.*$", re.I)),
    ("subsecao", 6, re.compile(r"^\s*SUBSE[CÇ][AÃ]O\b.*$", re.I)),
    ("anexo", 1, re.compile(r"^\s*ANEXO\b.*$", re.I)),
)
_HEADER_TITLE_MAX = 90


def _normalized_header_line(line):
    return re.sub(r"\s+", " ", line).strip()


def _heading_title_at(text, end):
    position = end
    seen = 0
    while position < len(text) and seen < 2:
        if text[position:position + 1] == "\n":
            position += 1
        next_newline = text.find("\n", position)
        if next_newline < 0:
            next_newline = len(text)
        candidate = _normalized_header_line(text[position:next_newline])
        position = next_newline
        seen += 1
        if not candidate:
            continue
        if (
            candidate.isupper()
            and len(candidate) <= _HEADER_TITLE_MAX
            and not any(pattern.match(candidate) for _key, _rank, pattern in _HEADER_LEVELS)
            and not ARTIGO_RE.match(candidate)
        ):
            return candidate
        return None
    return None


def _heading_title(lines, index):
    for line in lines[index + 1:index + 3]:
        candidate = _normalized_header_line(line)
        if not candidate:
            continue
        if (
            candidate.isupper()
            and len(candidate) <= _HEADER_TITLE_MAX
            and not any(pattern.match(candidate) for _key, _rank, pattern in _HEADER_LEVELS)
            and not ARTIGO_RE.match(candidate)
        ):
            return candidate
        return None
    return None


def _ordered_headers(levels):
    return [
        levels[key][1]
        for key, _rank, _pattern in _HEADER_LEVELS
        if key != "anexo" and key in levels
    ]


def _norma_only_headers(levels):
    return [levels["norma"][1]] if "norma" in levels else []


def _header_key_for_line(normalized):
    for key, _rank, pattern in _HEADER_LEVELS:
        if pattern.match(normalized):
            return key
    return None


_HEADER_SCAN_PATTERN = (
    r"(?P<header>^[ \t]*(?:LEI COMPLEMENTAR|LEI|DECRETO-LEI|DECRETO|PORTARIA|RESOLUÇÃO|RESOLUCAO|INSTRUÇÃO|INSTRUCAO|EMENDA CONSTITUCIONAL|CONSTITUIÇÃO|CONSTITUICAO|PARTE|LIVRO|TÍTULO|TITULO|CAPÍTULO|CAPITULO|SEÇÃO|SECAO|SUBSEÇÃO|SUBSECAO|ANEXO)\b[^\n]*$)"
)
_STRUCTURE_SCAN_RE = re.compile(
    rf"{_HEADER_SCAN_PATTERN}|(?P<article_ref>(?<![\w])Art(?:igo)?\.?[ \t]*{_ART_NUMBER}(?=\s|$))",
    re.IGNORECASE | re.MULTILINE,
)


def _merged_marker_matches(text, *regexes):
    matches = []
    occupied = []
    for regex in regexes:
        for candidate in regex.finditer(text):
            if any(candidate.start() < end and candidate.end() > start for start, end in occupied):
                continue
            matches.append(candidate)
            occupied.append((candidate.start(), candidate.end()))
    dedup = []
    for candidate in sorted(matches, key=lambda match: match.start()):
        ref = candidate.group(1).strip().casefold()
        if any(
            ref == previous.group(1).strip().casefold()
            and abs(candidate.start() - previous.start()) <= 2
            for previous in dedup[-2:]
        ):
            continue
        dedup.append(candidate)
    return dedup

def _headers_before(text, start):
    scanned = _scan_structure(text)
    positions = scanned["header_positions"]
    if not positions:
        return []
    index = bisect.bisect_right(positions, start) - 1
    return list(scanned["header_events"][index][1]) if index >= 0 else []


@lru_cache(maxsize=2)
def _scan_structure(text):
    """
    Estado hierárquico da norma em uma única varredura:
    Norma -> Parte -> Livro -> Título -> Capítulo -> Seção -> Subseção -> Artigo.
    O snapshot do cabeçalho acompanha cada artigo e novos cabeçalhos encerram a unidade anterior.
    """
    normalized = _ocr_structure_view(text)
    levels = {}
    header_events = []
    units = []
    current = None
    inside_anexo = False
    current_anexo_ref = None
    current_anexo_id = None

    def finalize(end):
        nonlocal current
        if current is None:
            return
        raw = text[current["start"]:end].strip()
        if current.get("kind") == "artigo":
            raw = raw.removesuffix("“").rstrip()
        if not raw:
            current = None
            return
        unit = dict(current)
        unit["text"] = raw
        units.append(unit)
        current = None

    for match in _STRUCTURE_SCAN_RE.finditer(normalized):
        if match.group("header"):
            header_start = match.start("header")
            normalized_line = _normalized_header_line(normalized[header_start:match.end("header")])
            key = _header_key_for_line(normalized_line)
            if key is None:
                continue

            # Dentro de artigo, "Lei nº 8.666..." pode ser continuação de uma citação quebrada.
            if key == "norma" and current is not None and not normalized_line.isupper():
                continue

            finalize(header_start)

            if key == "anexo":
                for other in list(levels):
                    if other != "norma":
                        del levels[other]
                current_anexo_ref = normalized_line
                current_anexo_id = f"anexo:{_normalize_article_ref(normalized_line) or header_start}@{header_start}"
                current = {
                    "kind": "anexo",
                    "ref": normalized_line,
                    "start": header_start,
                    "headers": _norma_only_headers(levels),
                    "node_id": current_anexo_id,
                    "anexo_id": current_anexo_id,
                    "anexo_ref": normalized_line,
                    "anexo_path": [normalized_line],
                }
                inside_anexo = True
                header_events.append((header_start, tuple(_norma_only_headers(levels) + [normalized_line])))
                continue

            if key == "norma":
                inside_anexo = False
                current_anexo_ref = None
                current_anexo_id = None
            rank = next(rank for name, rank, _pattern in _HEADER_LEVELS if name == key)
            title = _heading_title_at(normalized, match.end("header")) if key != "norma" else None
            for other, (other_rank, _value) in list(levels.items()):
                if other_rank >= rank:
                    del levels[other]
            levels[key] = (
                rank,
                f"{normalized_line} — {title}" if title and title not in normalized_line else normalized_line,
            )
            event_headers = _ordered_headers(levels)
            if inside_anexo and current_anexo_ref:
                norma_headers = _norma_only_headers(levels)
                event_headers = norma_headers + [current_anexo_ref] + [
                    header for header in event_headers if header not in norma_headers
                ]
            header_events.append((header_start, tuple(event_headers)))
            continue

        article_ref = match.group("article_ref")
        if article_ref is None:
            continue

        article_start = match.start("article_ref")
        article_end = match.end("article_ref")
        ref = article_ref.strip()
        if not _article_marker_is_real_header_at(text, article_start, article_end, ref):
            continue

        finalize(article_start)
        if inside_anexo and current_anexo_ref:
            norma_headers = _norma_only_headers(levels)
            internal_headers = [
                header for header in _ordered_headers(levels)
                if header not in norma_headers
            ]
            headers = norma_headers + [current_anexo_ref] + internal_headers
            anexo_ref = current_anexo_ref
            anexo_path = [current_anexo_ref] + internal_headers
            anexo_id = current_anexo_id
        else:
            headers = _ordered_headers(levels)
            anexo_ref = None
            anexo_path = []
            anexo_id = None
        structural_path = "/".join(
            _normalized_structure_component(item)
            for item in (*headers, ref)
            if item
        )
        current = {
            "kind": "artigo",
            "ref": ref,
            "start": article_start,
            "text": "",
            "headers": headers,
            "node_id": f"{structural_path}@{article_start}",
            "anexo_ref": anexo_ref,
            "anexo_path": anexo_path,
            "anexo_id": anexo_id,
        }

    finalize(len(text))
    return {
        "units": tuple(units),
        "header_events": tuple(header_events),
        "header_positions": tuple(position for position, _headers in header_events),
    }


CITATION_WORD_RE = re.compile(
    r"[ \t]+(?:desta|deste|dessa|desse|daquela|daquele|da|do|das|dos|de|e|ou|a|à|ao|aos|no|na|nos|nas|pelo|pela|pelos|pelas|c/c|combinado|caput|incisos?|par[aá]grafos?|al[ií]neas?|bem|todos|seguintes?|anterior(?:es)?|supra|infra|acima|abaixo|cit|mencionado|referido|supracitado)\b"
)

def _article_marker_is_real_header_at(text, start, end, ref):
    tail = text[end:end + 220]
    if not ref or not ref[:1].isupper():
        return False
    if ARTICLE_CITATION_TAIL_RE.match(tail):
        return False
    if not ref.endswith(".") and CITATION_WORD_RE.match(tail):
        return False

    context_start = max(0, start - 500)
    context = text[context_start:start]
    amendment_match = AMENDMENT_CONTEXT_RE.search(context)
    if amendment_match:
        trailing_after_amendment = context[amendment_match.end():]
        before_marker = text[max(0, start - 120):start]
        after_marker = text[end:end + 120]
        quoted_article_prefix = bool(re.search(r'["“‘\'\"]\s*Art(?:igo)?\.?\s*', before_marker, re.I))
        quoted_article_suffix = bool(re.search(r'["”’]\s*(?:\([A-ZÀ-Ý]+\)|\s*(?:\([A-ZÀ-Ý]+\)|\(NR\)|\(NR\)?)?)?$', after_marker))
        has_opening_quote = bool(re.search(r'["“‘\'\"]', trailing_after_amendment))
        has_intervening_article = bool(ARTIGO_INLINE_RE.search(trailing_after_amendment))
        if quoted_article_prefix and quoted_article_suffix:
            return False
        if has_opening_quote and not has_intervening_article:
            return False

    line_start = text.rfind("\n", 0, start) + 1
    before = text[line_start:start]
    stripped_before = before.strip()

    if stripped_before and ARTICLE_CITATION_PREFIX_RE.search(before[-100:]):
        return False

    if stripped_before and not re.match(
        r"\s*(?:[A-ZÀ-Ý§(“\"']|[IVXLCDM]+(?:\s*(?:\)|[.–—-]))?)",
        tail,
    ):
        return False
    return True


def _article_marker_is_real_header(text, match):
    if "article_ref" in match.groupdict():
        ref = match.group("article_ref")
        start = match.start("article_ref")
        end = match.end("article_ref")
    else:
        ref = match.group(1)
        start = match.start(1)
        end = match.end(1)
    return _article_marker_is_real_header_at(text, start, end, ref.strip())


def _is_article_number_inline_child(text, match):
    ref = match.group(1).strip()
    if not re.fullmatch(r"\d{1,3}\s*[.)–—-]", ref, re.I):
        return False
    marker_start = match.start(1)
    return bool(
        re.search(
            r"Art(?:igo)?\.?\s*$",
            _ocr_structure_view(text[max(0, marker_start - 16):marker_start]),
            re.I,
        )
    )


def _classify_child(ref):
    normalized = ref.strip()
    if normalized.startswith("§") or re.match(r"^par[aá]graf[o0]\s+", normalized, re.I):
        return "paragrafo"
    if re.match(r"^Inciso\b", normalized, re.I):
        return "inciso"
    if re.match(r"^Al[ií]nea\b", normalized, re.I):
        return "alinea"
    if re.fullmatch(rf"{_ROMAN_SUFFIX_RE}\s*(?:[.)–—-]|$)", normalized, re.I):
        return "inciso"
    if (
        re.fullmatch(r"\([A-Za-z]{1,3}\)", normalized)
        or re.fullmatch(r"[A-Za-z]{1,3}\s*(?:\)|[–—-])", normalized)
    ):
        return "alinea"
    return "item"


_CHILD_RANK = {"paragrafo": 1, "inciso": 2, "alinea": 3, "item": 4}


def _is_thousands_fragment(article_text, match):
    ref = match.group(1).strip()
    if not re.fullmatch(r"\d{1,3}\s*[.)–—-]", ref):
        return False
    marker_start = match.start(1)
    # Em "Art. 1.045.", o regex de item pode enxergar "045." após o ponto.
    # Um item real após uma frase ("2024. 1. ...") possui espaço antes do marcador.
    return (
        marker_start >= 2
        and article_text[marker_start - 2].isdigit()
        and article_text[marker_start - 1] == "."
    )


AMENDMENT_ACTION_RE = re.compile(
    r"(?i)\b(?:passa(?:m)?\s+a\s+vigorar|fica(?:m)?\s+(?:acrescid[oa]s?|acrescentad[oa]s?|"
    r"inserid[oa]s?|inclu[ií]d[oa]s?|revogad[oa]s?|suprimid[oa]s?|alterad[oa]s?|"
    r"substitu[ií]d[oa]s?)|acrescenta(?:m|-se)?|inclui(?:m|-se)?|altera(?:m|-se)?|"
    r"revoga(?:m|-se)?|suprime(?:m|-se)?|substitui(?:m|-se)?|"
    r"substitu[ií]d[oa]s?|d[aáo] nova reda[cç][aã]o)\b"
)
_DEVICE_REFERENCE_PATTERNS = (
    ("alinea", re.compile(
        r"\bal[ií]nea\s+(?:[\"“‘]([^\"”’]+)[\"”’]|([A-Za-z]{1,3}))"
        r"(?:\s+do\s+inciso\s+[IVXLCDM]+(?:-[A-Za-z]{1,3})?)?"
        r"(?:\s+do\s+art(?:igo)?\.?\s*\d+(?:[ºo°]|-[A-Za-z]{1,3})?(?:\.\d+)?(?:-[A-Za-z]{1,3})?)?",
        re.I,
    )),
    ("paragrafo", re.compile(
        r"(?:§\s*\d+[ºo°]?(?:-[A-Za-z])?|§\s*[uú]nico|par[aá]grafo\s+(?:[uú]nico|\d+[ºo°]?))"
        r"(?:\s+do\s+art(?:igo)?\.?\s*\d+(?:[ºo°]|-[A-Za-z]{1,3})?(?:\.\d+)?(?:-[A-Za-z]{1,3})?)?",
        re.I,
    )),
    ("inciso", re.compile(
        r"\binciso\s+[IVXLCDM]+(?:-[A-Za-z]{1,3})?"
        r"(?:\s+do\s+art(?:igo)?\.?\s*\d+(?:[ºo°]|-[A-Za-z]{1,3})?(?:\.\d+)?(?:-[A-Za-z]{1,3})?)?",
        re.I,
    )),
    ("item", re.compile(r"\bitem\s+\d+(?:\.\d+)*", re.I)),
    ("artigo", re.compile(
        r"\barts?\.?\s*\d+(?:[ºo°]|-[A-Za-z]{1,3})?(?:\.\d+)?(?:-[A-Za-z]{1,3})?\.?",
        re.I,
    )),
)
_ARTICLE_LIST_RE = re.compile(
    r"\barts?\.?\s*(?P<refs>\d+(?:[ºo°]|-[A-Za-z]{1,3})?"
    r"(?:\s*(?:,|e|ou)\s*\d+(?:[ºo°]|-[A-Za-z]{1,3})?)+)",
    re.I,
)
QUOTED_ARTICLE_RE = re.compile(
    rf"(?im)^[ \t]*[\"“‘]?[ \t]*(Art(?:igo)?\.?[ \t]*{_ART_NUMBER})(?=\s|$)"
)


def _normalized_structure_component(value):
    raw = unicodedata.normalize('NFKD', str(value or ''))
    normalized = ''.join(char for char in raw if not unicodedata.combining(char)).casefold()
    normalized = re.sub(r'[^a-z0-9]+', '-', normalized).strip('-')
    return normalized or 'estrutura'


def _normalize_article_ref(ref):
    if ref is None:
        return None
    normalized = re.sub(r"\s+", " ", str(ref).strip())
    normalized = normalized.lower().replace("º", "o").replace("°", "o")
    normalized = re.sub(r"[^a-z0-9-]", "", normalized)
    return normalized


def _reproduced_article_ranges(text):
    ranges = []
    for match in re.finditer(r'[“‘"]\s*Art(?:igo)?\.?\s*\d', text, re.I):
        opener = text[match.start()]
        closer = {'“': '”', '‘': '’', '"': '"'}.get(opener, '"')
        close = text.find(closer, match.end())
        if close < 0:
            close = len(text) - 1
        ranges.append((match.start(), close + 1))
    return ranges


def _position_inside_ranges(position, ranges):
    return any(start <= position < end for start, end in ranges)


def _detect_amendment(text, current_ref=None):
    if not text:
        return None
    action = AMENDMENT_ACTION_RE.search(text)
    if not action:
        return None

    target_text = text
    reproduced_article = re.search(r"[\"“‘]\s*Art(?:igo)?\.?\s*\d", text, re.I)
    if reproduced_article:
        target_text = text[:reproduced_article.start()]

    matches = []
    for kind, pattern in _DEVICE_REFERENCE_PATTERNS:
        for target_match in pattern.finditer(target_text):
            start, end = target_match.span()
            if kind == "alinea" and target_match.group(1):
                ref = target_match.group(1)
                ref = f'alínea "{ref}"' + target_match.group(0)[target_match.group(0).find("\"") + len(ref) + 2:]
            elif kind == "alinea" and target_match.group(2):
                ref = f"alínea {target_match.group(2)}" + target_match.group(0)[len("alínea") + 1 + len(target_match.group(2)):]
            elif kind == "artigo":
                ref = re.sub(r"^arts?\.?\s*", "Art. ", target_match.group(0), flags=re.I)
            else:
                ref = target_match.group(0)
            ref = re.sub(r"\s+", " ", ref).strip(" \t\r\n,;:")
            if current_ref and kind == "artigo" and _normalize_article_ref(ref) == _normalize_article_ref(current_ref):
                continue
            matches.append((start, end, kind, ref))

    for list_match in _ARTICLE_LIST_RE.finditer(target_text):
        for ref_match in re.finditer(r"\d+(?:[ºo°]|-[A-Za-z]{1,3})?", list_match.group("refs")):
            ref = f"Art. {ref_match.group(0)}"
            if current_ref and _normalize_article_ref(ref) == _normalize_article_ref(current_ref):
                continue
            matches.append((list_match.start("refs") + ref_match.start(), list_match.start("refs") + ref_match.end(), "artigo", ref))

    if not matches and reproduced_article:
        quoted_text = text[reproduced_article.start():]
        for target_match in QUOTED_ARTICLE_RE.finditer(quoted_text):
            ref = re.sub(r"^art(?:igo)?\.?\s*", "Art. ", target_match.group(1), flags=re.I)
            matches.append((
                reproduced_article.start() + target_match.start(1),
                reproduced_article.start() + target_match.end(1),
                "artigo",
                re.sub(r"\s+", " ", ref).strip(),
            ))

    selected = []
    for candidate in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]))):
        # Referências compostas, como "§ 2º do art. 75", devem permanecer
        # como um único dispositivo-alvo, sem gerar o artigo pai como alvo irmão.
        if candidate[2] == "artigo" and any(
            selected_item[2] != "artigo"
            and selected_item[0] <= candidate[0]
            and candidate[1] <= selected_item[1]
            for selected_item in selected
        ):
            continue
        if any(candidate[0] < end and candidate[1] > start for start, end, _kind, _ref in selected):
            continue
        if not any(kind == candidate[2] and ref.casefold() == candidate[3].casefold() for _start, _end, kind, ref in selected):
            selected.append(candidate)

    if not selected:
        return None

    amendment_operation_patterns = (
        ('redacao', re.compile(r'(?i)passa\s+a\s+vigorar(?:\s+com\s+(?:a\s+)?seguinte\s+reda[cç][aã]o)?|d[aá]\s+nova\s+reda[cç][aã]o')),
        ('alteracao', re.compile(r'(?i)\b(?:altera(?:m|-se)?|(?:fica|ficam)\s+alterad[oa]s?)\b')),
        ('revogacao', re.compile(r'(?i)\b(?:revoga(?:m|-se)?|(?:fica|ficam)\s+revogad[oa]s?)\b')),
        ('supressao', re.compile(r'(?i)\b(?:suprime(?:m|-se)?|(?:fica|ficam)\s+suprimid[oa]s?)\b')),
        ('acrescimo', re.compile(r'(?i)\b(?:acrescenta(?:m|-se)?|(?:fica|ficam)\s+acrescentad[oa]s?|(?:fica|ficam)\s+acrescid[oa]s?)\b')),
        ('inclusao', re.compile(r'(?i)\b(?:inclui(?:m|-se)?|(?:fica|ficam)\s+inclu[ií]d[oa]s?)\b')),
        ('substituicao', re.compile(r'(?i)\b(?:substitu[ií]do[as]?|substitui(?:m|-se)?)\b')),
    )
    operation_hits = []
    reproduced_ranges = _reproduced_article_ranges(text)
    for operation, pattern in amendment_operation_patterns:
        for operation_match in pattern.finditer(text):
            if _position_inside_ranges(operation_match.start(), reproduced_ranges):
                continue
            operation_hits.append((operation_match.start(), operation))
    amendment_operations = []
    for _position, operation in sorted(operation_hits, key=lambda item: item[0]):
        if operation not in amendment_operations:
            amendment_operations.append(operation)
    if not amendment_operations:
        amendment_operations = ['redacao']
    amendment_type = amendment_operations[0]

    target_devices = [
        {"kind": kind, "ref": ref}
        for _start, _end, kind, ref in selected
    ]
    target_articles = [item["ref"] for item in target_devices if item["kind"] == "artigo"]
    return {
        "amendment": True,
        "target_devices": target_devices,
        "target_articles": target_articles,
        "target_article": target_articles[0] if target_articles else None,
        "amendment_type": amendment_type,
        "amendment_operations": amendment_operations,
    }


def _article_children(article_text):
    filtered_matches = []
    for match in _merged_marker_matches(_ocr_structure_view(article_text), CHILD_RE, CHILD_INLINE_RE):
        if _is_article_number_inline_child(article_text, match):
            continue
        if _is_thousands_fragment(article_text, match):
            continue
        ref = match.group(1).strip()
        if re.fullmatch(r"\(?N\.?R\.?\)?", ref, re.I):
            before = article_text[max(0, match.start(1) - 200):match.start(1)]
            if re.search(r'["“‘\'\"]\s*Art(?:igo)?\.?\s*.*?["”’]\s*$', before, re.I | re.S):
                continue
        filtered_matches.append(match)
    matches = filtered_matches
    if not matches:
        return article_text.strip(), []

    first_start = matches[0].start(1)
    caput = article_text[:first_start].strip()
    children = []
    stack = []

    for index, match in enumerate(matches):
        marker_start = match.start(1)
        end = matches[index + 1].start(1) if index + 1 < len(matches) else len(article_text)
        value = article_text[marker_start:end].strip()
        ref = match.group(1).strip()
        if not value:
            continue

        kind = _classify_child(ref)
        rank = _CHILD_RANK[kind]
        while stack and stack[-1][0] >= rank:
            stack.pop()
        stack.append((rank, ref))
        children.append((kind, ref, value, marker_start, [ref for _rank, ref in stack]))

    return caput, children


ABBREVIATION_DOT_RE = re.compile(
    r"\b(?:art|inc|inciso|par|p|n|no|fls|proc|cf|etc|sr|sra|dr|dra|prof|p[aá]g|pag|vol|ed)\.",
    re.I,
)
ABBREVIATION_DOT_SENTINEL = "\ue000"


def _protect_abbreviation_dots(text):
    return ABBREVIATION_DOT_RE.sub(lambda match: match.group(0)[:-1] + ABBREVIATION_DOT_SENTINEL, text)


def _restore_abbreviation_dots(text):
    return text.replace(ABBREVIATION_DOT_SENTINEL, ".")
@lru_cache(maxsize=2)
def _default_tokenizer(providers=None):
    try:
        from fastembed import TextEmbedding
        selected_providers = tuple(providers) if providers is not None else tuple(config.FASTEMBED_PROVIDERS)
        model=TextEmbedding(model_name=config.DENSE_MODEL,max_length=config.DENSE_MAX_TOKENS,providers=list(selected_providers))
        tokenizer=getattr(getattr(model,"model",None),"tokenizer",None)
        if tokenizer is not None and hasattr(tokenizer,"no_truncation"):
            tokenizer.no_truncation()
        return tokenizer
    except Exception as exc:
        print(f"Aviso: tokenizer do embedding indisponível no chunking; fallback por caracteres: {exc}");return None

def get_cpu_tokenizer():
    """Retorna o tokenizer do embedding sem ocupar a GPU."""
    return _default_tokenizer(("CPUExecutionProvider",))

def _token_length_factory(tokenizer:Any|None)->Callable[[str],int]:
    if tokenizer is None:return len
    if hasattr(tokenizer,"no_truncation"):
        tokenizer.no_truncation()
    def length(text):
        try:
            encoded=tokenizer.encode(text);return len(getattr(encoded,"ids",encoded))
        except Exception:
            try:
                encoded=tokenizer.encode_batch([text])[0];return len(getattr(encoded,"ids",encoded))
            except Exception:return len(text)
    return length

def _split_text_spans(text,max_size,overlap,tokenizer=None):
    if max_size<=0:raise ValueError("max_size deve ser maior que zero")
    length_fn=_token_length_factory(tokenizer)
    if length_fn(text)<=max_size:return [(text,0,len(text))]
    effective_overlap=min(overlap,max(0,max_size-1));protected=_protect_abbreviation_dots(text)
    splitter=RecursiveCharacterTextSplitter(chunk_size=max_size,chunk_overlap=effective_overlap,length_function=length_fn,separators=["\n\n","\n",". ","; ",": "," ",""],keep_separator="end",add_start_index=True)
    spans=[]
    previous_start = -1
    for doc in splitter.create_documents([protected]):
        raw_piece = doc.page_content
        piece = _restore_abbreviation_dots(raw_piece)
        start = int(doc.metadata.get("start_index", -1))
        if start < 0 or protected[start:start + len(raw_piece)] != raw_piece:
            # O start_index gerado pelo splitter pode divergir do texto protegido.
            # Como a proteção de abreviações altera apenas o último caractere,
            # reconstruímos o offset usando o trecho restaurado no texto original.
            search_from = max(0, previous_start + 1)
            start = text.find(piece, search_from)
            if start < 0:
                # Em textos com trechos repetidos, tentar também a primeira
                # ocorrência evita depender de um start_index incorreto.
                start = text.find(piece)
            if start < 0:
                raise RuntimeError("Não foi possível reconstruir o span exato de um chunk.")
        end = start + len(piece)
        if text[start:end] != piece:
            raise RuntimeError("Não foi possível reconstruir o span exato de um chunk.")
        spans.append((piece, start, end))
        previous_start = start
    return spans

def _token_count(text,tokenizer=None):return _token_length_factory(tokenizer)(text)
def _truncate_words_to_tokens(text,budget,tokenizer=None):
    if budget<=0:return ""
    if _token_count(text,tokenizer)<=budget:return text
    words=list(re.finditer(r"\S+",text));lo,hi,best=0,len(words),""
    while lo<=hi:
        mid=(lo+hi)//2;candidate=text[:words[mid-1].end()].rstrip() if mid else ""
        if _token_count(candidate,tokenizer)<=budget:best=candidate;lo=mid+1
        else:hi=mid-1
    return best

def _excerpt_caput(caput,budget,tokenizer=None):
    label="CAPUT (trechos inicial e final): "
    if _token_count(caput,tokenizer)<=budget:return caput
    available=max(0,budget-_token_count(label,tokenizer))
    if available<=0:return _truncate_words_to_tokens(label,budget,tokenizer)
    ellipsis=" […] ";payload=max(1,available-_token_count(ellipsis,tokenizer));left_budget=max(1,int(payload*.30));right_budget=max(1,payload-left_budget);left=_truncate_words_to_tokens(caput,left_budget,tokenizer);words=list(re.finditer(r"\S+",caput));lo,hi,best=0,len(words),""
    while lo<=hi:
        mid=(lo+hi)//2;candidate=caput[words[len(words)-mid].start():].lstrip() if mid else ""
        if _token_count(candidate,tokenizer)<=right_budget:best=candidate;lo=mid+1
        else:hi=mid-1
    return _truncate_words_to_tokens((label+left+ellipsis+best).strip(),budget,tokenizer)

def _fit_child_prefix_info(prefix, child_text, max_size, tokenizer=None):
    """Reduz contexto auxiliar para reservar orçamento ao texto-fonte do filho."""
    context_oversize = (
        _token_count(prefix, tokenizer)
        + _token_count(child_text, tokenizer)
        + 1
        > max_size
    )
    path, separator, caput = prefix.partition("\n")
    path_parts = [part.strip() for part in path.split(" > ") if part.strip()]
    prefix_budget = max(0, max_size - 2)
    fitted_path = ""
    for start in range(len(path_parts)):
        candidate = " > ".join(path_parts[start:])
        if _token_count(candidate, tokenizer) <= prefix_budget:
            fitted_path = candidate
            break

    if not fitted_path and path_parts:
        fitted_path = _truncate_words_to_tokens(path_parts[-1], prefix_budget, tokenizer)

    fitted_prefix = fitted_path
    if separator and caput and fitted_path:
        caput_budget = prefix_budget - _token_count(fitted_path, tokenizer) - 1
        if caput_budget > 0:
            excerpt = _excerpt_caput(caput, caput_budget, tokenizer)
            if excerpt:
                excerpt = re.sub(r"^CAPUT \(trechos inicial e final\):\s*", "", excerpt)
                fitted_prefix = f"{fitted_path}\n{excerpt}"
    if _token_count(fitted_prefix, tokenizer) > prefix_budget:
        fitted_prefix = _truncate_words_to_tokens(fitted_path, prefix_budget, tokenizer)
    return fitted_prefix, context_oversize


def _fit_child_prefix(prefix, child_text, max_size, tokenizer=None):
    fitted, _oversize = _fit_child_prefix_info(prefix, child_text, max_size, tokenizer)
    return fitted


def _article_units(text):
    scanned = _scan_structure(text)
    return [
        {
            **unit,
            "headers": list(unit.get("headers") or []),
        }
        for unit in scanned["units"]
    ] or None

CHUNKING_VERSION = 3
LEGAL_AST_SCHEMA_VERSION = 2


@dataclass
class LegalNode:
    """Nó canônico da árvore jurídica; offsets apontam para o texto original recebido."""
    node_id: str
    kind: str
    ref: str | None
    parent_id: str | None
    source_start: int
    source_end: int
    source_text: str
    children: list["LegalNode"] = field(default_factory=list)
    path: list[str] = field(default_factory=list)
    anexo_ref: str | None = None
    anexo_path: list[str] = field(default_factory=list)

    def add_child(self, child: "LegalNode") -> None:
        child.parent_id = self.node_id
        self.children.append(child)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "ref": self.ref,
            "parent_id": self.parent_id,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "source_text": self.source_text,
            "children": [child.to_dict() for child in self.children],
            "path": list(self.path),
            "anexo_ref": self.anexo_ref,
            "anexo_path": list(self.anexo_path),
        }


def build_legal_ast(text: str) -> LegalNode:
    """Constrói a árvore jurídica canônica que alimenta a projeção em chunks."""
    scanned = _scan_structure(text)
    root = LegalNode(
        node_id="norma",
        kind="norma",
        ref=None,
        parent_id=None,
        source_start=0,
        source_end=len(text),
        source_text=text,
    )
    annex_nodes: dict[str, LegalNode] = {}
    header_nodes: dict[tuple[str, ...], LegalNode] = {}

    # A hierarquia de títulos/capítulos/seções também é materializada como nós.
    for event_index, (position, headers) in enumerate(scanned["header_events"]):
        if not headers:
            continue
        path = tuple(str(item) for item in headers)
        if path in header_nodes:
            continue
        heading = path[-1]
        line_start = int(position)
        line_end = text.find("\n", line_start)
        if line_end < 0:
            line_end = len(text)
        parent = root
        parent_path = path[:-1]
        if parent_path:
            parent = header_nodes.get(parent_path, root)
        node = LegalNode(
            node_id=f"header:{'/'.join(_normalized_structure_component(item) for item in path)}@{position}",
            kind=(
                "anexo" if re.match(r"^ANEXO\b", heading, re.I) else
                next((kind for kind, rank, pattern in _HEADER_LEVELS if kind != "anexo" and pattern.match(heading)), "estrutura")
            ),
            ref=heading,
            parent_id=parent.node_id,
            source_start=line_start,
            source_end=line_end,
            source_text=text[line_start:line_end],
            path=list(path),
            anexo_ref=(
                path[next((index for index, item in enumerate(path) if re.match(r"^ANEXO\b", item, re.I)), len(path) - 1)]
                if any(re.match(r"^ANEXO\b", item, re.I) for item in path) else None
            ),
            anexo_path=(
                path[next((index for index, item in enumerate(path) if re.match(r"^ANEXO\b", item, re.I)), len(path)) :]
                if any(re.match(r"^ANEXO\b", item, re.I) for item in path) else []
            ),
        )
        parent.add_child(node)
        header_nodes[path] = node

    for unit in scanned["units"]:
        kind = str(unit.get("kind") or "generic")
        ref = unit.get("ref")
        start = int(unit.get("start") or 0)
        source_text = str(unit.get("text") or "")
        source_end = start + len(source_text)

        if kind == "anexo":
            path = tuple(list(unit.get("headers") or []) + ([str(ref)] if ref else []))
            node = header_nodes.get(path)
            if node is None:
                node = LegalNode(
                    node_id=str(unit.get("node_id") or f"anexo:{_normalize_article_ref(ref) or start}@{start}"),
                    kind="anexo",
                    ref=ref,
                    parent_id=root.node_id,
                    source_start=start,
                    source_end=source_end,
                    source_text=source_text,
                    path=list(path),
                    anexo_ref=str(ref) if ref else None,
                    anexo_path=list(unit.get("anexo_path") or ([str(ref)] if ref else [])),
                )
                root.add_child(node)
            else:
                node.source_start = start
                node.source_end = source_end
                node.source_text = source_text
                node.anexo_ref = str(ref) if ref else None
                node.anexo_path = list(unit.get("anexo_path") or ([str(ref)] if ref else []))
            annex_nodes[node.node_id] = node
            for alias in (unit.get("anexo_id"), node.anexo_ref):
                if alias:
                    annex_nodes[str(alias)] = node
            continue

        if kind != "artigo":
            continue

        anexo_ref = unit.get("anexo_ref")
        annex_key = str(unit.get("anexo_id") or anexo_ref or "")
        path = list(unit.get("headers") or [])
        if ref:
            path.append(str(ref))

        header_path = tuple(path[:-1])
        if anexo_ref:
            parent = header_nodes.get(header_path)
            if parent is None or parent.kind == 'anexo':
                parent = annex_nodes.get(annex_key)
        else:
            parent = header_nodes.get(header_path, root)
        if parent is None:
            parent = root
        node = LegalNode(
            node_id=str(unit.get("node_id") or f"artigo:{_normalize_article_ref(ref) or start}@{start}"),
            kind="artigo",
            ref=ref,
            parent_id=parent.node_id,
            source_start=start,
            source_end=source_end,
            source_text=source_text,
            path=path,
            anexo_ref=str(anexo_ref) if anexo_ref else None,
            anexo_path=list(unit.get("anexo_path") or []),
        )
        parent.add_child(node)

        # Dispositivos filhos são nós explícitos da mesma árvore.
        _caput, children = _article_children(source_text)
        for child_kind, child_ref, child_text, child_start, path_tail in children:
            child_source_start = start + child_start
            child = LegalNode(
                node_id=f"{node.node_id}/{child_kind}:{_normalize_article_ref(child_ref) or child_start}",
                kind=child_kind,
                ref=child_ref,
                parent_id=node.node_id,
                source_start=child_source_start,
                source_end=child_source_start + len(child_text),
                source_text=child_text,
                path=path + list(path_tail),
                anexo_ref=node.anexo_ref,
                anexo_path=list(node.anexo_path),
            )
            node.add_child(child)

    return root


def _ast_units(root: LegalNode) -> list[dict[str, Any]]:
    """Projeta a AST em unidades compatíveis com o splitter atual."""
    units = []

    def walk(node: LegalNode):
        for child in node.children:
            if child.kind in {"artigo", "anexo"}:
                units.append({
                    "kind": child.kind,
                    "ref": child.ref,
                    "start": child.source_start,
                    "text": child.source_text,
                    "headers": (
                        list(child.path[:-1])
                        if child.kind == "artigo" and child.ref
                        else list(child.path[:-1]) if child.kind == "anexo" and child.ref else list(child.path)
                    ),
                    "node_id": child.node_id,
                    "parent_id": child.parent_id,
                    "anexo_ref": child.anexo_ref,
                    "anexo_path": list(child.anexo_path),
                    "anexo_id": next(
                        (candidate.node_id for candidate in root.children
                         if candidate.kind == "anexo" and candidate.node_id == child.parent_id),
                        None,
                    ),
                })
            walk(child)

    walk(root)
    return units



JURIS_SECTION_RE=re.compile(r"(?im)^[ \t]*(EMENTA|TESE/ENTENDIMENTO|TESE|DECISÃO|DECISAO|INTEIRO TEOR|RELATÓRIO|RELATORIO|VOTO|DISPOSITIVO)\s*:?[ \t]*$")

def _trimmed_span(value,base_start=0):
    leading=len(value)-len(value.lstrip())
    return base_start+leading,value.strip()

def _jurisprudencia_units(text):
    matches=list(JURISPRUDENCIA_RE.finditer(text))
    if not matches:return None
    units=[]
    for i,m in enumerate(matches):
        start=m.start();end=matches[i+1].start() if i+1<len(matches) else len(text);start,value=_trimmed_span(text[start:end],start);process=re.search(r"^PROCESSO:\s*(.+)$",value,re.I|re.M);sumula=re.search(r"^S[ÚU]MULA:\s*(.+)$",value,re.I|re.M);ref=process.group(1).strip() if process else sumula.group(1).strip() if sumula else None
        units.append({"kind":"jurisprudencia","ref":ref,"start":start,"text":value,"headers":[]})
    return units or None

def _jurisprudencia_sections(text):
    matches=list(JURIS_SECTION_RE.finditer(text))
    if not matches:
        start,value=_trimmed_span(text)
        return [{"kind":"jurisprudencia","ref":None,"start":start,"text":value,"section":"inteiro_teor"}] if value else []
    sections=[];first=matches[0].start()
    start,value=_trimmed_span(text[:first])
    if value:sections.append({"kind":"jurisprudencia","ref":None,"start":start,"text":value,"section":"metadados"})
    for i,m in enumerate(matches):
        start=m.start();end=matches[i+1].start() if i+1<len(matches) else len(text);label=re.sub(r"\s+"," ",m.group(1)).strip().casefold().replace(" ","_");start,value=_trimmed_span(text[start:end],start)
        if value:sections.append({"kind":"jurisprudencia","ref":None,"start":start,"text":value,"section":label})
    return sections

def _units(text):
    juris=_jurisprudencia_units(text)
    if juris:return juris
    articles=_article_units(text)
    if articles:return articles
    sums=_find(text,SUMULA_RE,"sumula")
    if sums:
        for u in sums:u["headers"]=_headers_before(text,u["start"])
        return sums
    temas=_find(text,TEMA_RE,"tema")
    if temas:
        for u in temas:u["headers"]=_headers_before(text,u["start"])
        return temas
    return [{"kind":"generic","ref":None,"start":0,"text":text.strip(),"headers":[]}]


def _assert_source_spans(full_text: str, chunks: list[dict[str, Any]]) -> None:
    """Garante que toda evidência recuperável aponta exatamente para a fonte."""
    for index, chunk in enumerate(chunks):
        start = int(chunk.get("source_start", chunk.get("start", 0)))
        end = int(chunk.get("source_end", chunk.get("end", start)))
        source_text = str(chunk.get("source_text") or "")
        if start < 0 or end < start or end > len(full_text):
            raise RuntimeError(f"Offset jurídico inválido no chunk {index}: {start}:{end}.")
        if full_text[start:end] != source_text:
            raise RuntimeError(
                f"Fonte do chunk {index} não corresponde aos offsets fonte {start}:{end}."
            )


def _attach_device_ids(chunks):
    for chunk in chunks:
        unit_id = str(chunk.get("unit_id") or "")
        unit_ref = chunk.get("unit_ref")
        path = list(chunk.get("hierarchy_path") or [])
        if chunk.get("unit_kind") == "artigo" and unit_ref:
            article_index = next(
                (index for index in range(len(path) - 1, -1, -1) if path[index] == unit_ref),
                None,
            )
            device_path = path[article_index + 1:] if article_index is not None else []
            suffix = "/".join(str(part).strip() for part in device_path if str(part).strip()) or "caput"
            chunk["device_id"] = f"{unit_id}/{suffix}"
        else:
            chunk["device_id"] = unit_id
    return chunks


def build_structural_chunks(full_text,max_size,overlap,*,metadata=None,tokenizer=None):
    if max_size<=0:raise ValueError("max_size deve ser maior que zero")
    if overlap<0 or overlap>=max_size:raise ValueError("overlap deve ser maior ou igual a zero e menor que max_size")
    if tokenizer is None:
        tokenizer=_default_tokenizer()
    elif hasattr(tokenizer,"no_truncation"):
        tokenizer.no_truncation()
    source_metadata = metadata or {}
    source_role = str(source_metadata.get("source_role") or "").strip().casefold()
    tipo_documento = str(source_metadata.get("tipo_documento") or "").strip().casefold()
    normative_types = {
        "constituicao", "constituicao_estadual", "lei", "lei_complementar",
        "lei_ordinaria", "decreto", "decreto_lei", "emenda_constitucional",
        "instrucao_normativa", "portaria", "resolucao", "deliberacao",
        "ato_normativo", "norma",
    }
    # O parser jurídico só deve ser aplicado quando a fonte é normativa.
    # Mantemos o comportamento legado quando metadata não foi fornecido ou
    # quando a classificação é desconhecida, para não quebrar chamadas externas.
    use_legal_ast = (
        metadata is None
        or source_role in {"", "norma"}
        or tipo_documento in normative_types
    )
    if use_legal_ast:
        try:
            ast = build_legal_ast(full_text)
            units = _ast_units(ast) or _units(full_text)
        except Exception:
            # Uma falha do parser não pode tornar uma fonte inteira indisponível.
            # O fallback preserva os offsets da evidência e mantém o orçamento de tokens.
            start, value = _trimmed_span(full_text)
            units = [{"kind": "generic", "ref": None, "start": start, "text": value, "headers": []}]
    else:
        start, value = _trimmed_span(full_text)
        units = [{"kind": "generic", "ref": None, "start": start, "text": value, "headers": []}]

    juris_units=_jurisprudencia_units(full_text)
    if juris_units:
        output=[];ref_counts={}
        for u in juris_units:
            ref=u.get("ref");ref_counts[ref]=ref_counts.get(ref,0)+1
        for u in juris_units:
            ref=u.get("ref")
            unit_key=ref or u["start"]
            unit_id=f"jurisprudencia:{ref or u['start']}"+(f":{u['start']}" if ref and ref_counts[ref]>1 else "")
            unit_token_count = _token_count(u["text"], tokenizer)
            full_unit_text = u["text"] if unit_token_count <= max_size else None
            for section in _jurisprudencia_sections(u["text"]):
                for piece,rel,_end in _split_text_spans(section["text"],max_size,overlap,tokenizer):
                    source_start=u["start"]+section["start"]+rel;source_end=u["start"]+section["start"]+_end
                    output.append({"text":piece,"source_text":piece,"retrieval_text":piece,"full_unit_text":full_unit_text,"page_content":piece,"unit_kind":"jurisprudencia","unit_ref":ref,"unit_id":unit_id,"node_id":f"{unit_id}/{section['section']}","parent_id":None,"chunk_index":len(output),"unit_length":len(u["text"]),"start":source_start,"end":source_end,"source_start":source_start,"source_end":source_end,"page_uncertain":False,"chunking_method":"structural","hierarchy_headers":[],"hierarchy_path":[section["section"]],"parent_caput":None,"segment_kind":section["section"],"segment_ref":section["section"],"child_index":None,"prefix_truncated":False})
        if output:
            output = _attach_device_ids(output)
            _assert_source_spans(full_text, output)
            return output
    output=[];ref_counts={}
    for unit in units:
        ref=unit.get("ref")
        if ref:ref_counts[(unit["kind"],ref)]=ref_counts.get((unit["kind"],ref),0)+1
    for unit in units:
        if not unit["text"].strip():continue
        ref=unit.get("ref")
        legacy_unit_id = (
            (f"{unit['kind']}:{ref}" if ref else f"{unit['kind']}:{unit['start']}")
            + (f":{unit['start']}" if ref and ref_counts.get((unit["kind"],ref),0)>1 else "")
        )
        # unit_id continua compatível com o corpus histórico; node_id identifica
        # a posição estrutural exata na AST. Em anexos, o node_id evita colisões.
        unit_id = str(unit.get("node_id") or legacy_unit_id) if unit.get("anexo_ref") else legacy_unit_id
        headers=list(unit.get("headers") or [])
        amendment = _detect_amendment(unit["text"], ref) if unit["kind"] == "artigo" else None
        if unit["kind"]!="artigo":
            unit_token_count = _token_count(unit["text"], tokenizer)
            full_unit_text = unit["text"] if unit_token_count <= max_size else None
            for idx,(piece,start,_end) in enumerate(_split_text_spans(unit["text"],max_size,overlap,tokenizer)):
                output.append({"text":piece,"source_text":piece,"retrieval_text":piece,"full_unit_text":full_unit_text,"page_content":piece,"unit_kind":unit["kind"],"unit_ref":ref,"unit_id":unit_id,"chunk_index":idx,"unit_length":len(unit["text"]),"start":unit["start"]+start,"end":unit["start"]+_end,"source_start":unit["start"]+start,"source_end":unit["start"]+_end,"page_uncertain":False,"chunking_method":"structural","hierarchy_headers":headers,"hierarchy_path":headers+([ref] if ref else []),"parent_caput":None,"segment_kind":unit["kind"],"segment_ref":ref,"prefix_truncated":False,"node_id":unit.get("node_id"),"parent_id":unit.get("parent_id"),"anexo_ref":unit.get("anexo_ref"),"anexo_path":list(unit.get("anexo_path") or [])})
            continue
        caput,children=_article_children(unit["text"])
        article_ref=ref or "Artigo"
        article_header=[*headers,article_ref]
        node_id = unit.get("node_id")
        parent_id = unit.get("parent_id")
        anexo_ref = unit.get("anexo_ref")
        anexo_path = list(unit.get("anexo_path") or [])
        if not children:
            unit_token_count = _token_count(unit["text"], tokenizer)
            full_unit_text = unit["text"] if unit_token_count <= max_size else None
            for idx,(piece,start,_end) in enumerate(_split_text_spans(unit["text"],max_size,overlap,tokenizer)):
                output.append({"text":piece,"source_text":piece,"retrieval_text":piece,"full_unit_text":full_unit_text,"page_content":piece,"unit_kind":"artigo","unit_ref":ref,"unit_id":unit_id,"chunk_index":idx,"unit_length":len(unit["text"]),"start":unit["start"]+start,"end":unit["start"]+_end,"source_start":unit["start"]+start,"source_end":unit["start"]+_end,"page_uncertain":False,"chunking_method":"structural","hierarchy_headers":headers,"hierarchy_path":article_header,"parent_caput":caput,"segment_kind":"caput","segment_ref":None,"prefix_truncated":False,"node_id":node_id,"parent_id":parent_id,"anexo_ref":anexo_ref,"anexo_path":anexo_path,"amendment":bool(amendment),"target_article":(amendment or {}).get("target_article"),"target_articles":(amendment or {}).get("target_articles", []),"target_devices":(amendment or {}).get("target_devices", []),"amendment_type":(amendment or {}).get("amendment_type"),"amendment_operations":(amendment or {}).get("amendment_operations", [])})
            continue
        caput_token_count = _token_count(caput, tokenizer)
        caput_full_unit_text = caput if caput_token_count <= max_size else None
        caput_index=0
        for piece,start,_end in _split_text_spans(caput,max_size,overlap,tokenizer):
            output.append({"text":piece,"source_text":piece,"retrieval_text":piece,"full_unit_text":caput_full_unit_text,"page_content":piece,"unit_kind":"artigo","unit_ref":ref,"unit_id":unit_id,"chunk_index":caput_index,"unit_length":len(unit["text"]),"start":unit["start"]+start,"end":unit["start"]+_end,"source_start":unit["start"]+start,"source_end":unit["start"]+_end,"page_uncertain":False,"chunking_method":"structural","hierarchy_headers":headers,"hierarchy_path":article_header+["CAPUT"],"parent_caput":caput,"segment_kind":"caput","segment_ref":None,"prefix_truncated":False,"node_id":node_id,"parent_id":parent_id,"anexo_ref":anexo_ref,"anexo_path":anexo_path,"amendment":bool(amendment),"target_article":(amendment or {}).get("target_article"),"target_articles":(amendment or {}).get("target_articles", []),"target_devices":(amendment or {}).get("target_devices", []),"amendment_type":(amendment or {}).get("amendment_type"),"amendment_operations":(amendment or {}).get("amendment_operations", [])})
            caput_index+=1
        next_index=max(1,caput_index)
        for child_index,(kind,child_ref,child_text,child_start,path_tail) in enumerate(children):
            child_path=article_header+path_tail
            raw_prefix=" > ".join(child_path)+"\n"+caput
            child_prefix,context_oversize=_fit_child_prefix_info(raw_prefix,child_text,max_size,tokenizer)
            child_budget=max(1,max_size-_token_count(child_prefix,tokenizer)-2)
            child_spans=_split_text_spans(child_text,child_budget,overlap,tokenizer)
            for local_index,(piece,relative,_end) in enumerate(child_spans):
                rendered=f"{child_prefix}\n{piece}".strip()
                while _token_count(rendered,tokenizer)>max_size and child_prefix:
                    allowed_prefix=max(0,max_size-_token_count(piece,tokenizer)-2)
                    child_prefix=_truncate_words_to_tokens(child_prefix,allowed_prefix,tokenizer)
                    rendered=f"{child_prefix}\n{piece}".strip()
                if _token_count(rendered,tokenizer)>max_size:
                    raise RuntimeError("Segmento jurídico excede o orçamento de tokens após a divisão.")
                output.append({"text":rendered,"source_text":piece,"retrieval_text":rendered,"full_unit_text":None,"page_content":rendered,"unit_kind":"artigo","unit_ref":ref,"unit_id":unit_id,"chunk_index":next_index+local_index,"unit_length":len(unit["text"]),"start":unit["start"]+child_start+relative,"end":unit["start"]+child_start+relative+len(piece),"source_start":unit["start"]+child_start+relative,"source_end":unit["start"]+child_start+relative+len(piece),"page_uncertain":False,"chunking_method":"structural","hierarchy_headers":headers,"hierarchy_path":child_path,"parent_caput":caput,"segment_kind":kind,"segment_ref":child_ref,"child_index":child_index,"prefix_truncated":False,"context_reduced":context_oversize or child_prefix != raw_prefix.split("\n", 1)[0] + "\n" + caput,"context_oversize":context_oversize,"amendment":bool(amendment),"target_article":(amendment or {}).get("target_article"),"target_articles":(amendment or {}).get("target_articles", []),"target_devices":(amendment or {}).get("target_devices", []),"amendment_type":(amendment or {}).get("amendment_type"),"amendment_operations":(amendment or {}).get("amendment_operations", []),"node_id":node_id + "/" + kind + ":" + (_normalize_article_ref(child_ref) or str(child_index)),"parent_id":node_id,"anexo_ref":anexo_ref,"anexo_path":anexo_path})
            next_index+=len(child_spans)
    output = _attach_device_ids(output)
    _assert_source_spans(full_text, output)
    return output