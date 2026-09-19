from __future__ import annotations

import concurrent.futures
import re

import requests
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import config
from .collector import clean_text, make_session
from .schema import JurisprudenciaRecord

TCU_SUMULA_CATALOG_URL = "https://pesquisa.apps.tcu.gov.br/resultado/todas-bases/%2A?pb=sumula"
TCESP_SUMULA_URL = "https://www.tce.sp.gov.br/boletim-de-jurisprudencia/sumulas"
TCU_SUMULA_MAX_NUMBER = 400
TCU_SUMULA_MIN_RECORDS = 295
TCU_SUMULA_REQUIRED_NUMBERS = (222, 247, 259, 263, 292)
def _strip_markup(value: str) -> str:
    return re.sub(r"~~|\*\*", "", str(value or "")).strip()



def _parse_tcu_sumulas_text(text: str) -> list[JurisprudenciaRecord]:
    lines = [line.strip() for line in text.replace("\xa0", " ").splitlines() if line.strip()]
    heading = re.compile(
        r"^S[ÚU]MULA(?:\s+TCU)?\s+(?:N[ºO°]?\s*)?(\d+)\s*(?:\(([^)]*)\))?\s*(?:\s*(?::|-)[ \t]*)?(.*)$",
        re.IGNORECASE,
    )
    records = []
    current = None
    for line in lines:
        match = heading.match(line)
        if match:
            if current is not None:
                records.append(current)
            current = {
                "numero": int(match.group(1)),
                "status": clean_text(match.group(2) or ""),
                "parts": [match.group(3).strip()] if match.group(3).strip() else [],
            }
            continue
        if current is None:
            continue
        if re.match(r"^(?:Acórdão|Decisão|Ata)\b", line, re.IGNORECASE):
            continue
        current["parts"].append(line)
    if current is not None:
        records.append(current)

    result = []
    for item in records:
        block = " ".join(part for part in item["parts"] if part)
        block = re.split(r"\s+(?:Acórdão|Decisão|Ata)\b", block, maxsplit=1, flags=re.IGNORECASE)[0]
        block = re.split(r"\s+Área\s*:", block, maxsplit=1, flags=re.IGNORECASE)[0]
        enunciado = _strip_markup(clean_text(block))
        if not enunciado:
            continue
        number = item["numero"]
        result.append(
            JurisprudenciaRecord(
                tribunal="TCU",
                tipo_documento="sumula",
                numero_processo=f"Súmula TCU {number}",
                numero_sumula=str(number),
                numero_decisao=str(number),
                tipo_decisao="Súmula",
                orgao_julgador="Plenário",
                ementa=enunciado,
                situacao=item["status"] or "VIGENTE",
                url_oficial=TCU_SUMULA_CATALOG_URL,
                origem="TCU — Repertório oficial de Súmulas",
            )
        )
    return result


def _parse_tcu_sumulas_page(raw: bytes) -> list[JurisprudenciaRecord]:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "aside"]):
        tag.decompose()
    return _parse_tcu_sumulas_text(soup.get_text("\n"))


def _pagination_links(raw: bytes, base_url: str) -> list[str]:
    soup = BeautifulSoup(raw, "html.parser")
    host = urlparse(base_url).netloc.casefold()
    links = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, str(anchor["href"]).strip())
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.casefold() != host:
            continue
        path = parsed.path.casefold()
        query = parsed.query.casefold()
        label = clean_text(anchor.get_text(" ", strip=True)).casefold()
        aria = str(anchor.get("aria-label") or "").casefold()
        title = str(anchor.get("title") or "").casefold()
        pagination_hint = (
            "todas-bases" in path
            and (
                "pb=sumula" in query
                or "sumula" in label
                or "sumula" in aria
                or "sumula" in title
                or bool(re.search(r"(?:pagina|page|offset)=?\d+", query))
            )
        )
        if pagination_hint:
            links.append(href.split("#", 1)[0])
    return list(dict.fromkeys(links))



def _collect_tcu_sumulas_browser(max_pages: int = 40, max_number: int = TCU_SUMULA_MAX_NUMBER) -> list[JurisprudenciaRecord]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright é necessário para renderizar o catálogo de Súmulas do TCU.") from exc

    by_number = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        try:
            page.goto(TCU_SUMULA_CATALOG_URL, wait_until="domcontentloaded", timeout=60000)
            visited_signatures = set()
            for _ in range(max_pages):
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeoutError:
                    pass
                body_text = page.locator("body").inner_text(timeout=10000)
                if not body_text.strip():
                    print(f"  diagnóstico: catálogo TCU sem texto renderizado em {page.url}")
                for record in _parse_tcu_sumulas_text(body_text):
                    number = int(record.numero_sumula or 0)
                    if 1 <= number <= max_number:
                        by_number[number] = record
                page_signature = re.sub(r"\s+", " ", body_text)
                if page_signature in visited_signatures:
                    break
                visited_signatures.add(page_signature)

                next_locator = page.get_by_role("button", name="Próxima página").last
                if next_locator.count() == 0:
                    candidates = page.locator("a,button")
                    next_index = None
                    for index in range(candidates.count()):
                        item = candidates.nth(index)
                        try:
                            label = " ".join(filter(None, [
                                item.inner_text(timeout=1000),
                                item.get_attribute("aria-label"),
                                item.get_attribute("title"),
                            ])).strip().casefold()
                        except Exception:
                            continue
                        normalized = re.sub(r"\s+", " ", label)
                        if (
                            re.search(r"\b(próxima|proxima|next)\b", normalized)
                            or normalized in {">", "›", "»", "→"}
                        ):
                            disabled = item.get_attribute("disabled")
                            aria_disabled = item.get_attribute("aria-disabled")
                            if disabled is None and aria_disabled != "true":
                                next_index = index
                                break
                    if next_index is None:
                        break
                    next_locator = candidates.nth(next_index)
                disabled = next_locator.get_attribute("disabled")
                aria_disabled = next_locator.get_attribute("aria-disabled")
                if disabled is not None or aria_disabled == "true":
                    break
                before_url = page.url
                before_signature = re.sub(r"\s+", " ", body_text)
                next_locator.click(force=True)
                changed = False
                for _attempt in range(75):
                    try:
                        page.wait_for_timeout(200)
                        new_url = page.url
                        new_text = page.locator("body").inner_text(timeout=1000)
                    except Exception:
                        continue
                    if new_url != before_url or re.sub(r"\s+", " ", new_text) != before_signature:
                        changed = True
                        break
                if not changed:
                    break
        finally:
            browser.close()
    if not by_number:
        diagnostics = [
            re.sub(r"\s+", " ", line).strip()
            for line in body_text.splitlines()
            if "súmula" in line.casefold()
        ]
        print("  diagnóstico TCU: nenhuma súmula extraída.")
        print(f"  URL renderizada: {page.url if 'page' in locals() else TCU_SUMULA_CATALOG_URL}")
        if diagnostics:
            print("  linhas contendo 'súmula': " + " | ".join(diagnostics[:20]))
        elif 'body_text' in locals():
            print("  início do texto renderizado: " + re.sub(r"\s+", " ", body_text[:3000]).strip())
    return [by_number[number] for number in sorted(by_number)]


def _has_complete_tcu_coverage(records: list[JurisprudenciaRecord], max_number: int) -> bool:
    numbers = {
        int(record.numero_sumula)
        for record in records
        if record.numero_sumula and str(record.numero_sumula).isdigit()
        and 1 <= int(record.numero_sumula) <= max_number
    }
    return len(numbers) >= TCU_SUMULA_MIN_RECORDS and all(
        number in numbers for number in TCU_SUMULA_REQUIRED_NUMBERS
    )


def collect_tcu_sumulas(session=None, max_number: int = TCU_SUMULA_MAX_NUMBER) -> list[JurisprudenciaRecord]:
    session = session or make_session()
    try:
        response = session.get(TCU_SUMULA_CATALOG_URL, timeout=(8, 60), allow_redirects=True)
        response.raise_for_status()
        records = _parse_tcu_sumulas_page(response.content)
    except requests.RequestException:
        records = []
    if records and _has_complete_tcu_coverage(records, max_number):
        by_number = {}
        for record in records:
            number = int(record.numero_sumula or 0)
            if 1 <= number <= max_number:
                by_number[number] = record
        return [by_number[number] for number in sorted(by_number)]
    return _collect_tcu_sumulas_browser(max_number=max_number)


def _parse_tcesp_sumulas_text(text: str) -> list[JurisprudenciaRecord]:
    normalized = text.replace(" ", " ")
    pattern = re.compile(
        r"(?is)S[ÚU]MULA\s+(?:N[ºO°]?\s*)?(\d+)\s*(?:[-–—:]\s*)?"
    )
    matches = list(pattern.finditer(normalized))
    records = []
    for index, match in enumerate(matches):
        number = int(match.group(1))
        if not 1 <= number <= 53:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        block = normalized[match.end():end]
        block = re.sub(r"\(Veja histórico e fundamento\)", "", block, flags=re.I)
        cancelled = bool(re.search(r"\bCANCELADA\b", block, re.I))
        block = re.split(r"\n\s*(?:Veja|Histórico|Fundamento)\b", block, maxsplit=1, flags=re.I)[0]
        block = re.sub(r"\s*\(CANCELADA\)\s*", " ", block, flags=re.I)
        enunciado = _strip_markup(clean_text(block))
        if not enunciado:
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
                ementa=enunciado,
                situacao="CANCELADA" if cancelled else "VIGENTE",
                url_oficial=TCESP_SUMULA_URL,
                origem="TCESP — Repertório de Súmulas",
            )
        )
    by_number = {int(record.numero_decisao): record for record in records}
    return [by_number[number] for number in sorted(by_number)]


def _collect_tcesp_sumulas_browser(max_pages: int = 10) -> list[JurisprudenciaRecord]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright é necessário para renderizar o catálogo de Súmulas do TCESP.") from exc

    by_number = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        try:
            page.goto(TCESP_SUMULA_URL, wait_until="domcontentloaded", timeout=60000)
            visited_signatures = set()
            for _ in range(max_pages):
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeoutError:
                    pass
                body_text = page.locator("body").inner_text(timeout=15000)
                signature = re.sub(r"\s+", " ", body_text)
                if signature in visited_signatures:
                    break
                visited_signatures.add(signature)
                for record in _parse_tcesp_sumulas_text(body_text):
                    by_number[int(record.numero_sumula)] = record
                expected = set(range(1, 54))
                if expected.issubset(by_number):
                    break

                controls = page.locator("a,button")
                next_index = None
                for control_index in range(controls.count()):
                    control = controls.nth(control_index)
                    try:
                        label = " ".join(
                            filter(
                                None,
                                [
                                    control.inner_text(timeout=1000),
                                    control.get_attribute("aria-label"),
                                    control.get_attribute("title"),
                                ],
                            )
                        ).strip().casefold()
                    except Exception:
                        continue
                    normalized = re.sub(r"\s+", " ", label)
                    if (
                        re.search(r"\b(próxima|proxima|próximo|proximo|next)\b", normalized)
                        or normalized in {">", "›", "»", "→"}
                    ):
                        disabled = control.get_attribute("disabled")
                        aria_disabled = control.get_attribute("aria-disabled")
                        if disabled is None and aria_disabled != "true":
                            next_index = control_index
                            break
                if next_index is None:
                    break
                before = signature
                controls.nth(next_index).click(force=True)
                try:
                    page.wait_for_function(
                        "(oldText) => document.body && document.body.innerText.replace(/\\s+/g, ' ').trim() !== oldText",
                        arg=before,
                        timeout=15000,
                    )
                except PlaywrightTimeoutError:
                    pass
        finally:
            browser.close()
    return [by_number[number] for number in sorted(by_number)]


def collect_tcesp_sumulas(session=None) -> list[JurisprudenciaRecord]:
    session = session or make_session()
    response = session.get(TCESP_SUMULA_URL, timeout=(8, 45), allow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "aside"]):
        tag.decompose()
    records = _parse_tcesp_sumulas_text(soup.get_text("\n"))
    numbers = {
        int(record.numero_sumula)
        for record in records
        if record.numero_sumula and record.numero_sumula.isdigit()
    }
    if len(numbers) < 53 or 53 not in numbers:
        records = _collect_tcesp_sumulas_browser()
    return records



def smoke_test_sumulas() -> None:
    session = make_session()
    tcu_records = collect_tcu_sumulas(session)
    by_number = {int(item.numero_sumula): item for item in tcu_records if item.numero_sumula and item.numero_sumula.isdigit()}
    for number in (222, 247, 259, 263, 292):
        record = by_number.get(number)
        if record is None:
            raise RuntimeError(f"Súmula TCU {number} não foi encontrada no catálogo oficial.")
        if not record.ementa or record.tipo_decisao != "Súmula" or record.numero_sumula != str(number):
            raise RuntimeError(f"Súmula TCU {number} retornou registro estrutural inválido.")
    records = collect_tcesp_sumulas(session)
    numbers = {int(item.numero_decisao) for item in records if item.numero_decisao and item.numero_decisao.isdigit()}
    expected = set(range(1, 54))
    if numbers != expected:
        missing = sorted(expected - numbers)
        raise RuntimeError(f"TCESP: repertório de súmulas incompleto no portal oficial; ausentes={missing}")
    if len(tcu_records) < TCU_SUMULA_MIN_RECORDS:
        raise RuntimeError(
            f"TCU: catálogo retornou apenas {len(tcu_records)} súmulas; esperado pelo menos {TCU_SUMULA_MIN_RECORDS}."
        )
    print(
        f"Smoke súmulas OK: TCU={len(tcu_records)} | TCU-chave=222,247,259,263,292 | TCESP={len(records)}"
    )


def collect_sumulas(*, strict: bool = False) -> dict[str, list[JurisprudenciaRecord]]:
    session = make_session()
    result: dict[str, list[JurisprudenciaRecord]] = {"tcu": [], "tcesp": []}
    failures = []
    try:
        result["tcu"] = collect_tcu_sumulas(session)
    except Exception as exc:
        failures.append(f"TCU: {type(exc).__name__}: {exc}")
    try:
        result["tcesp"] = collect_tcesp_sumulas(session)
    except Exception as exc:
        failures.append(f"TCESP: {type(exc).__name__}: {exc}")
    if strict:
        tcu_numbers = {
            int(item.numero_decisao)
            for item in result["tcu"]
            if item.numero_decisao and item.numero_decisao.isdigit()
        }
        if len(result["tcu"]) < TCU_SUMULA_MIN_RECORDS:
            failures.append(
                f"TCU: apenas {len(result['tcu'])} súmulas estruturadas; esperado pelo menos {TCU_SUMULA_MIN_RECORDS}"
            )
        missing = [number for number in TCU_SUMULA_REQUIRED_NUMBERS if number not in tcu_numbers]
        if missing:
            failures.append(f"TCU: súmulas essenciais ausentes={missing}")
        tcesp_numbers = {
            int(item.numero_decisao)
            for item in result["tcesp"]
            if item.numero_decisao and item.numero_decisao.isdigit()
        }
        if tcesp_numbers != set(range(1, 54)):
            missing = sorted(set(range(1, 54)) - tcesp_numbers)
            failures.append(f"TCESP: cobertura estrutural incompleta; ausentes={missing}")
    if failures:
        raise RuntimeError("Falhas na coleta estruturada de súmulas: " + "; ".join(failures))
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Coleta as Súmulas do TCU e do TCESP em registros estruturados.")
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
