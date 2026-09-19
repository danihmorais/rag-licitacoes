from __future__ import annotations

import concurrent.futures
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

TCU_SUMULA_MAX_NUMBER = 400
TCU_SUMULA_MIN_RECORDS = 295
TCU_SUMULA_REQUIRED_NUMBERS = (222, 247, 259, 263, 292)

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


def _make_tcu_record(numero: int, enunciado: str, *, source_url: str, context: str = "") -> JurisprudenciaRecord:
    return JurisprudenciaRecord(
        tribunal="TCU",
        tipo_documento="sumula",
        numero_processo=f"Súmula TCU {numero}",
        numero_sumula=str(numero),
        numero_decisao=str(numero),
        tipo_decisao="Súmula",
        orgao_julgador="Plenário",
        ementa=_strip_markup(clean_text(enunciado)),
        situacao=_status_from_text(context),
        url_oficial=source_url,
        origem="TCU — Repertório oficial de Súmulas",
    )


def _parse_tcu_sumula_document(raw: bytes, numero: int, source_url: str) -> JurisprudenciaRecord | None:
    text = page_text(raw)
    pattern = re.compile(
        rf"(?is)\bEnunciado\b\s*S[ÚU]MULA\s+TCU\s+(?:N[ºO°]?\s*)?{numero}\s*"
        rf"\s*[:\-–—]\s*(.+?)(?=\n\s*(?:Excerto|Fundamento legal|ÍNDICE)\b|\Z)"
    )
    match = pattern.search(text)
    if not match:
        pattern = re.compile(
            rf"(?is)S[ÚU]MULA\s+TCU\s+(?:N[ºO°]?\s*)?{numero}\s*"
            rf"\s*[:\-–—]\s*(.+?)(?=\n\s*(?:Decisão|Acórdão|Área|Excerto|Fundamento legal|ÍNDICE)\b|\Z)"
        )
        match = pattern.search(text)
    if not match:
        return None
    enunciado = match.group(1).strip()
    context = text[max(0, match.start() - 200):min(len(text), match.end() + 500)]
    return _make_tcu_record(numero, enunciado, source_url=source_url, context=context)


def _fetch_tcu_sumula(numero: int) -> JurisprudenciaRecord | None:
    session = _thread_session()
    for url in (
        TCU_SUMULA_DOCUMENT_URL.format(numero=numero),
        TCU_SUMULA_SEARCH_URL.format(numero=numero),
    ):
        try:
            response = session.get(url, timeout=(8, 45), allow_redirects=True)
        except requests.RequestException:
            continue
        if response.status_code == 404:
            continue
        response.raise_for_status()
        record = _parse_tcu_sumula_document(response.content, numero, response.url)
        if record is not None:
            return record
    return None


def collect_tcu_sumulas(session=None, max_number: int = TCU_SUMULA_MAX_NUMBER) -> list[JurisprudenciaRecord]:
    numbers = range(1, max_number + 1)
    records: list[JurisprudenciaRecord] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch_tcu_sumula, number): number for number in numbers}
        for future in concurrent.futures.as_completed(futures):
            number = futures[future]
            try:
                record = future.result()
            except (requests.RequestException, ValueError) as exc:
                print(f"  aviso: Súmula TCU {number} indisponível: {type(exc).__name__}: {exc}")
                continue
            if record is not None:
                records.append(record)
    return sorted(records, key=lambda item: int(item.numero_sumula or 0))


def _parse_tcesp_sumulas_text(text: str) -> list[JurisprudenciaRecord]:
    lines = [clean_text(line) for line in text.replace("\xa0", " ").splitlines() if clean_text(line)]
    heading = re.compile(
        r"^S[ÚU]MULA\s+N[ºO°]?\s*(\d+)\s*(?:[-–—]\s*)?(.*)$",
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
        body = re.sub(r"\s+", " ", body).strip(" -–—")
        if not body or body.casefold() == "veja histórico e fundamento":
            continue
        records.append(
            JurisprudenciaRecord(
                tribunal="TCESP",
                tipo_documento="sumula",
                numero_processo=f"Súmula TCESP {number}",
                numero_sumula=str(number),
                numero_decisao=str(number),
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
    return _parse_tcesp_sumulas_text(page_text(response.content))


def smoke_test_sumulas() -> None:
    critical_numbers = (222, 247, 259, 263, 292)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_tcu_sumula, number): number for number in critical_numbers}
        tcu_records = [future.result() for future in futures]
    for number, record in zip(critical_numbers, tcu_records):
        if record is None:
            raise RuntimeError(f"Súmula TCU {number} não foi encontrada no portal oficial.")
        if not record.ementa or record.numero_sumula != str(number) or record.tipo_documento != "sumula":
            raise RuntimeError(f"Súmula TCU {number} retornou registro estrutural inválido.")

    tcesp_records = collect_tcesp_sumulas()
    tcesp_numbers = {
        int(record.numero_sumula)
        for record in tcesp_records
        if record.numero_sumula and record.numero_sumula.isdigit()
    }
    expected = set(range(1, 54))
    if tcesp_numbers != expected:
        missing = sorted(expected - tcesp_numbers)
        raise RuntimeError(f"TCESP: repertório de súmulas incompleto no portal oficial; ausentes={missing}")

    print("Smoke súmulas OK: TCU 222, 247, 259, 263, 292 | TCESP 1-53")


def collect_sumulas(*, strict: bool = False) -> dict[str, list[JurisprudenciaRecord]]:
    result: dict[str, list[JurisprudenciaRecord]] = {"tcu": [], "tcesp": []}
    failures = []

    try:
        result["tcu"] = collect_tcu_sumulas()
    except Exception as exc:
        failures.append(f"TCU: {type(exc).__name__}: {exc}")

    try:
        result["tcesp"] = collect_tcesp_sumulas()
    except Exception as exc:
        failures.append(f"TCESP: {type(exc).__name__}: {exc}")

    if strict:
        tcu_numbers = {
            int(item.numero_sumula)
            for item in result["tcu"]
            if item.numero_sumula and item.numero_sumula.isdigit()
        }
        if len(result["tcu"]) < TCU_SUMULA_MIN_RECORDS:
            failures.append(
                f"TCU: apenas {len(result['tcu'])} súmulas estruturadas; esperado pelo menos {TCU_SUMULA_MIN_RECORDS}"
            )
        missing = sorted(set(TCU_SUMULA_REQUIRED_NUMBERS) - tcu_numbers)
        if missing:
            failures.append(f"TCU: súmulas essenciais ausentes={missing}")

        tcesp_numbers = {
            int(item.numero_sumula)
            for item in result["tcesp"]
            if item.numero_sumula and item.numero_sumula.isdigit()
        }
        if tcesp_numbers != set(range(1, 54)):
            missing = sorted(set(range(1, 54)) - tcesp_numbers)
            failures.append(f"TCESP: cobertura estrutural incompleta; ausentes={missing}")

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
