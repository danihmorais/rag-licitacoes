from __future__ import annotations

import asyncio
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
TCU_SUMULA_BROWSER_CONCURRENCY = 6
TCU_SUMULA_BROWSER_TIMEOUT_MS = 60000
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


def _fetch_tcu_sumula(numero: int) -> JurisprudenciaRecord | None:
    session = _thread_session()
    try:
        response = session.get(
            TCU_SUMULA_DOCUMENT_URL.format(numero=numero),
            timeout=(8, 45),
            allow_redirects=True,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return _parse_tcu_sumula_document(response.content, numero, response.url)
    except requests.RequestException:
        return None


async def _fetch_tcu_sumula_browser(page, numero: int) -> JurisprudenciaRecord | None:
    url = TCU_SUMULA_DOCUMENT_URL.format(numero=numero)
    try:
        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=TCU_SUMULA_BROWSER_TIMEOUT_MS,
        )
        if response is not None and response.status >= 400:
            return None
        await page.wait_for_function(
            "(needle) => document.body && document.body.innerText.includes(needle)",
            arg=f"SÚMULA TCU {numero}",
            timeout=30000,
        )
        text = await page.locator("body").inner_text()
    except Exception as exc:
        print(f"  aviso: Súmula TCU {numero} via navegador falhou: {type(exc).__name__}: {exc}")
        return None
    return _parse_tcu_sumula_text(text, numero, page.url)


async def _collect_tcu_sumulas_browser(numbers: list[int]) -> list[JurisprudenciaRecord]:
    from playwright.async_api import async_playwright

    semaphore = asyncio.Semaphore(TCU_SUMULA_BROWSER_CONCURRENCY)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)

        async def fetch_one(numero: int) -> JurisprudenciaRecord | None:
            async with semaphore:
                page = await browser.new_page()
                try:
                    return await _fetch_tcu_sumula_browser(page, numero)
                finally:
                    await page.close()

        records = await asyncio.gather(*(fetch_one(numero) for numero in numbers))
        await browser.close()

    return [record for record in records if record is not None]


def _collect_tcu_sumulas(numbers) -> list[JurisprudenciaRecord]:
    numbers = list(numbers)
    records_by_number: dict[int, JurisprudenciaRecord] = {}

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
                records_by_number[number] = record

    missing = [number for number in numbers if number not in records_by_number]
    if missing:
        try:
            browser_records = asyncio.run(_collect_tcu_sumulas_browser(missing))
        except Exception as exc:
            print(f"  aviso: fallback Chromium das Súmulas TCU falhou: {type(exc).__name__}: {exc}")
            browser_records = []
        for record in browser_records:
            number = int(record.numero_sumula or 0)
            if number:
                records_by_number[number] = record

    return sorted(records_by_number.values(), key=lambda item: int(item.numero_sumula or 0))


def collect_tcu_sumulas(session=None, max_number: int = TCU_SUMULA_MAX_NUMBER) -> list[JurisprudenciaRecord]:
    return _collect_tcu_sumulas(range(1, max_number + 1))


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
    return _parse_tcesp_sumulas_text(page_text(response.content))


def smoke_test_sumulas() -> None:
    critical_numbers = (222, 247, 259, 263, 292)
    tcu_records = _collect_tcu_sumulas(critical_numbers)
    tcu_by_number = {
        int(record.numero_sumula): record
        for record in tcu_records
        if record.numero_sumula and record.numero_sumula.isdigit()
    }
    for number in critical_numbers:
        record = tcu_by_number.get(number)
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
    if len(tcesp_numbers) < TCESP_SUMULA_MIN_RECORDS:
        raise RuntimeError(
            f"TCESP: apenas {len(tcesp_numbers)} súmulas estruturadas; "
            f"esperado pelo menos {TCESP_SUMULA_MIN_RECORDS}"
        )
    highest = max(tcesp_numbers, default=0)
    expected = set(range(1, highest + 1))
    if tcesp_numbers != expected:
        missing = sorted(expected - tcesp_numbers)
        raise RuntimeError(
            f"TCESP: repertório de súmulas com lacunas no portal oficial; ausentes={missing}"
        )

    print(
        f"Smoke súmulas OK: TCU 222, 247, 259, 263, 292 | "
        f"TCESP 1-{highest} ({len(tcesp_numbers)} registros)"
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
        if len(result["tcu"]) < TCU_SUMULA_MIN_RECORDS:
            failures.append(
                f"TCU: apenas {len(result['tcu'])} súmulas estruturadas; esperado pelo menos {TCU_SUMULA_MIN_RECORDS}"
            )
        missing = sorted(set(TCU_SUMULA_REQUIRED_NUMBERS) - tcu_numbers)
        if missing:
            failures.append(f"TCU: súmulas essenciais ausentes={missing}")

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
        highest = max(tcesp_numbers, default=0)
        expected = set(range(1, highest + 1))
        if tcesp_numbers != expected:
            missing = sorted(expected - tcesp_numbers)
            failures.append(
                f"TCESP: cobertura estrutural com lacunas; ausentes={missing}"
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
