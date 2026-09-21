from __future__ import annotations

import csv
import io
import re
import threading

import requests
from bs4 import BeautifulSoup

from .collector import clean_text, make_session, page_text
from .schema import JurisprudenciaRecord

TCU_SUMULA_DOCUMENT_URL = (
    "https://pesquisa.apps.tcu.gov.br/documento/sumula/%2A/"
    "NUMERO%253A{numero}/DTRELEVANCIA%2520desc%252C%2520NUMEROINT%2520desc/"
    "0/sinonimos%253Dtrue"
)
TCU_SUMULA_SEARCH_URL = (
    "https://pesquisa.apps.tcu.gov.br/resultado/sumula/%2A/"
    "NUMERO%253A{numero}/sinonimos%253Dtrue"
)
TCESP_SUMULA_URL = "https://www.tce.sp.gov.br/boletim-de-jurisprudencia/sumulas"

TCU_SUMULA_CSV_URL = "https://sites.tcu.gov.br/dados-abertos/jurisprudencia/arquivos/sumula/sumula.csv"
TCU_SUMULA_MIN_RECORDS = 1
TCU_SUMULA_REQUIRED_NUMBERS = (222, 247, 259, 263, 292)
TCESP_SUMULA_MIN_RECORDS = 52

_thread_state = threading.local()


def _thread_session():
    session = getattr(_thread_state, "session", None)
    if session is None:
        session = make_session()
        _thread_state.session = session
    return session


def _strip_markup(value: str) -> str:
    return re.sub(r"~~|\*\*", "", str(value or "")).strip()


def _status_from_text(text: str) -> str:
    match = re.search(r"\b(CANCELADA|CANCELADO|REVOGADA|REVOGADO)\b", text, re.IGNORECASE)
    return match.group(1).upper() if match else "VIGENTE"


def _strip_status_marker(text: str) -> str:
    return re.sub(r"\s*\((?:CANCELADA|CANCELADO|REVOGADA|REVOGADO)\)\s*$", "", text, flags=re.IGNORECASE).strip()


def _make_tcu_record(numero: int, enunciado: str, *, source_url: str, context: str = "") -> JurisprudenciaRecord:
    return JurisprudenciaRecord(
        tribunal="TCU",
        tipo_documento="sumula",
        numero_processo="",
        numero_sumula=str(numero),
        numero_decisao=None,
        tipo_decisao="Súmula",
        orgao_julgador="Plenário",
        ementa=_strip_markup(clean_text(enunciado)),
        situacao=_status_from_text(context),
        url_oficial=source_url,
        origem="TCU — Repertório oficial de Súmulas",
    )


def _parse_tcu_sumula_text(text: str, numero: int, source_url: str) -> JurisprudenciaRecord | None:
    number_pattern = rf"(?:N[ºO°]?\s*)?{numero}\b"
    header_pattern = re.compile(
        rf"S[ÚU]MULA\s+TCU\s+{number_pattern}"
        rf"(?:\s*\((?P<status>[^\n)]{{1,40}})\))?"
        rf"\s*[:\-–—]\s*(?P<enunciado>.+?)"
        rf"(?=\n\s*(?:Excerto|Fundamento legal|ÍNDICE|Decisão|Acórdão|Área)\b|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    match = header_pattern.search(text)
    if not match:
        return None
    enunciado = match.group("enunciado").strip()
    if not enunciado:
        return None
    status = match.group("status")
    context = status or text[max(0, match.start() - 200):min(len(text), match.end() + 500)]
    return _make_tcu_record(numero, enunciado, source_url=source_url, context=context)

def _parse_tcu_sumula_document(raw: bytes, numero: int, source_url: str) -> JurisprudenciaRecord | None:
    return _parse_tcu_sumula_text(page_text(raw), numero, source_url)


def _csv_rows(raw: bytes) -> list[dict[str, str]]:
    text = ""
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        raise ValueError("CSV de Súmulas TCU não pôde ser decodificado")

    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;|\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows: list[dict[str, str]] = []
    for raw_row in reader:
        row = {
            str(key or "").strip().lstrip("\ufeff").upper(): str(value or "").strip()
            for key, value in raw_row.items()
            if key is not None
        }
        if row:
            rows.append(row)
    return rows


def _csv_value(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return clean_text(str(value))
    return ""


def _normalize_tcu_sumula_number(value: str) -> str:
    raw = clean_text(value).replace(",", ".")
    match = re.fullmatch(r"(\d+)(?:\.0+)?", raw)
    return match.group(1) if match else ""


def _tcu_csv_situacao(value: str) -> str:
    folded = clean_text(value).casefold()
    if folded in {"sim", "s", "true", "1", "vigente"}:
        return "VIGENTE"
    if folded in {"não", "nao", "n", "false", "0", "revogada", "revogado", "cancelada", "cancelado"}:
        return "REVOGADA"
    return clean_text(value).upper() or "VIGENTE"


def _make_tcu_csv_record(row: dict[str, str]) -> JurisprudenciaRecord | None:
    numero = _normalize_tcu_sumula_number(_csv_value(row, "NUMERO"))
    enunciado = _csv_value(row, "ENUNCIADO")
    if not numero or not enunciado:
        return None

    approval = _csv_value(row, "NUMAPROVACAO")
    approval_year = _csv_value(row, "ANOAPROVACAO")
    decisao = f"{approval}/{approval_year}" if approval and approval_year else approval

    assuntos = [
        item for item in (
            _csv_value(row, "AREA"),
            _csv_value(row, "TEMA"),
            _csv_value(row, "SUBTEMA"),
        )
        if item
    ]

    return JurisprudenciaRecord(
        tribunal="TCU",
        tipo_documento="sumula",
        numero_processo="",
        numero_sumula=numero,
        numero_decisao=decisao or None,
        tipo_decisao="Súmula",
        orgao_julgador=_csv_value(row, "COLEGIADO") or "Plenário",
        data=_csv_value(row, "DATASESSAOFORMATADA"),
        assunto=assuntos,
        ementa=enunciado,
        situacao=_tcu_csv_situacao(_csv_value(row, "VIGENTE")),
        url_oficial=TCU_SUMULA_CSV_URL,
        origem="TCU — Repertório oficial de Súmulas (dados abertos)",
    )


def _parse_tcu_sumulas_csv(raw: bytes) -> list[JurisprudenciaRecord]:
    records_by_number: dict[int, JurisprudenciaRecord] = {}
    for row in _csv_rows(raw):
        record = _make_tcu_csv_record(row)
        if record is None:
            continue
        number = int(record.numero_sumula or 0)
        if number:
            records_by_number[number] = record
    return [records_by_number[number] for number in sorted(records_by_number)]


def collect_tcu_sumulas(session=None) -> list[JurisprudenciaRecord]:
    session = session or make_session()
    response = session.get(
        TCU_SUMULA_CSV_URL,
        timeout=(8, 90),
        allow_redirects=True,
    )
    response.raise_for_status()
    return _parse_tcu_sumulas_csv(response.content)


def _parse_tcesp_sumulas_text(text: str) -> list[JurisprudenciaRecord]:
    raw_text = str(text or "")
    if "<" in raw_text and ">" in raw_text:
        raw_text = page_text(raw_text.encode("utf-8"))
    lines = [clean_text(line) for line in raw_text.replace("\xa0", " ").splitlines() if clean_text(line)]
    heading = re.compile(
        r"^S[ÚU]MULA\s+(?:N[ºO°]?\s*)?(\d+)\s*(?:[-–—]\s*)?(.*)$",
        re.IGNORECASE,
    )
    blocks: list[tuple[int, str]] = []
    current_number = None
    current_lines: list[str] = []

    for line in lines:
        match = heading.match(line)
        if match:
            if current_number is not None:
                blocks.append((current_number, "\n".join(current_lines)))
            current_number = int(match.group(1))
            current_lines = [match.group(2).strip()] if match.group(2).strip() else []
            continue
        if current_number is not None:
            current_lines.append(line)
    if current_number is not None:
        blocks.append((current_number, "\n".join(current_lines)))

    records = []
    for number, block in blocks:
        status = _status_from_text(block)
        body = re.split(r"(?im)^HIST[ÓO]RICO\b", block, maxsplit=1)[0]
        body = re.split(r"(?im)^FUNDAMENTO\b", body, maxsplit=1)[0]
        body = re.sub(r"\(Veja histórico e fundamento\)", "", body, flags=re.IGNORECASE)
        body = _strip_markup(body)
        body = _strip_status_marker(body)
        body = re.sub(r"\s+", " ", body).strip(" -–—")
        if not body or body.casefold() == "veja histórico e fundamento":
            continue
        records.append(
            JurisprudenciaRecord(
                tribunal="TCESP",
                tipo_documento="sumula",
                numero_processo="",
                numero_sumula=str(number),
                numero_decisao=None,
                tipo_decisao="Súmula",
                orgao_julgador="Tribunal Pleno",
                ementa=clean_text(body),
                situacao=status,
                url_oficial=TCESP_SUMULA_URL,
                origem="TCESP — Repertório de Súmulas",
            )
        )
    return sorted(records, key=lambda item: int(item.numero_sumula or 0))


def collect_tcesp_sumulas(session=None) -> list[JurisprudenciaRecord]:
    session = session or make_session()
    response = session.get(TCESP_SUMULA_URL, timeout=(8, 45), allow_redirects=True)
    response.raise_for_status()
    records = _parse_tcesp_sumulas_text(page_text(response.content))
    unique_by_number: dict[int, JurisprudenciaRecord] = {}
    for record in records:
        number = str(record.numero_sumula or '').strip()
        if not number.isdigit():
            continue
        unique_by_number.setdefault(int(number), record)
    return [unique_by_number[number] for number in sorted(unique_by_number)]


def smoke_test_sumulas() -> None:
    result = collect_sumulas(strict=True)
    tcu_numbers = {
        int(item.numero_sumula)
        for item in result["tcu"]
        if item.numero_sumula and item.numero_sumula.isdigit()
    }
    tcesp_numbers = {
        int(item.numero_sumula)
        for item in result["tcesp"]
        if item.numero_sumula and item.numero_sumula.isdigit()
    }
    print(
        f"Smoke súmulas OK: TCU {len(tcu_numbers)} números "
        f"(1-{max(tcu_numbers, default=0)}) | "
        f"TCESP {len(tcesp_numbers)} números "
        f"(1-{max(tcesp_numbers, default=0)})"
    )


def collect_sumulas(
    *,
    tribunals=("tcu", "tcesp"),
    strict: bool = False,
) -> dict[str, list[JurisprudenciaRecord]]:
    requested = tuple(dict.fromkeys(str(tribunal).strip().casefold() for tribunal in tribunals))
    unknown = sorted(set(requested) - {"tcu", "tcesp"})
    if unknown:
        raise ValueError("tribunais de súmulas inválidos: " + ", ".join(unknown))

    result: dict[str, list[JurisprudenciaRecord]] = {"tcu": [], "tcesp": []}
    failures = []

    if "tcu" in requested:
        try:
            result["tcu"] = collect_tcu_sumulas()
        except Exception as exc:
            failures.append(f"TCU: {type(exc).__name__}: {exc}")

    if "tcesp" in requested:
        try:
            result["tcesp"] = collect_tcesp_sumulas()
        except Exception as exc:
            failures.append(f"TCESP: {type(exc).__name__}: {exc}")

    if strict and "tcu" in requested:
        tcu_numbers = {
            int(item.numero_sumula)
            for item in result["tcu"]
            if item.numero_sumula and item.numero_sumula.isdigit()
        }
        if len(tcu_numbers) < TCU_SUMULA_MIN_RECORDS:
            failures.append(
                f"TCU: apenas {len(tcu_numbers)} súmulas estruturadas; "
                f"esperado pelo menos {TCU_SUMULA_MIN_RECORDS}"
            )
        if len(tcu_numbers) != len(result["tcu"]):
            failures.append(
                f"TCU: números de súmula duplicados ou inconsistentes; "
                f"registros={len(result['tcu'])} números_únicos={len(tcu_numbers)}"
            )

    if strict and "tcesp" in requested:
        tcesp_numbers = {
            int(item.numero_sumula)
            for item in result["tcesp"]
            if item.numero_sumula and item.numero_sumula.isdigit()
        }
        if len(tcesp_numbers) < TCESP_SUMULA_MIN_RECORDS:
            failures.append(
                f"TCESP: apenas {len(tcesp_numbers)} súmulas estruturadas; "
                f"esperado pelo menos {TCESP_SUMULA_MIN_RECORDS}"
            )
        if len(tcesp_numbers) != len(result["tcesp"]):
            failures.append(
                f"TCESP: números de súmula duplicados ou inconsistentes; "
                f"registros={len(result['tcesp'])} números_únicos={len(tcesp_numbers)}"
            )

    if failures:
        raise RuntimeError("Falhas na coleta estruturada de súmulas: " + "; ".join(failures))
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Coleta as Súmulas do TCU e do TCESP em registros estruturados."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--strict", action="store_true")
    group.add_argument("--health", action="store_true")
    args = parser.parse_args()

    try:
        if args.health:
            smoke_test_sumulas()
            return 0
        result = collect_sumulas(strict=args.strict)
    except Exception as exc:
        print(f"FAIL súmulas: {type(exc).__name__}: {exc}")
        return 1

    print(f"TCU: {len(result['tcu'])} súmulas | TCESP: {len(result['tcesp'])} súmulas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
