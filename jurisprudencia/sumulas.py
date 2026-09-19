from __future__ import annotations

import concurrent.futures
import re

import requests
import threading
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import config
from .collector import clean_text, make_session
from .schema import JurisprudenciaRecord

TCU_SUMULA_URL = "https://pesquisa.apps.tcu.gov.br/resultado/sumula/{numero}"
TCU_SUMULA_SEARCH_URL = "https://pesquisa.apps.tcu.gov.br/resultado/sumula/%2A/NUMERO%253A{numero}/sinonimos%253Dtrue"
TCU_SUMULA_CATALOG_URL = "https://pesquisa.apps.tcu.gov.br/resultado/todas-bases/%2A?pb=sumula"
TCESP_SUMULA_URL = "https://www.tce.sp.gov.br/boletim-de-jurisprudencia/sumulas"
TCU_SUMULA_MAX_NUMBER = 400
def _strip_markup(value: str) -> str:
    return re.sub(r"~~|\*\*", "", str(value or "")).strip()


def _tcu_record(numero: int, raw: bytes) -> JurisprudenciaRecord | None:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "aside"]):
        tag.decompose()
    text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    match = re.search(
        rf"(?is)S[ÚU]MULA\s+TCU\s+{numero}\s*(?:\(([^)]+)\))?\s*:\s*(.+?)(?=\n\s*Acórdão\b|\n\s*Acórdão:|\Z)",
        text,
    )
    if not match:
        return None
    situation = clean_text(match.group(1) or "")
    enunciado = _strip_markup(clean_text(match.group(2)))
    if not enunciado:
        return None
    return JurisprudenciaRecord(
        tribunal="TCU",
        tipo_documento="sumula",
        numero_processo=f"Súmula TCU {numero}",
        numero_sumula=str(numero),
        numero_decisao=str(numero),
        tipo_decisao="Súmula",
        orgao_julgador="Plenário",
        ementa=enunciado,
        situacao=situation or "VIGENTE",
        url_oficial=TCU_SUMULA_URL.format(numero=numero),
        origem="TCU — Pesquisa de Jurisprudência — Súmulas",
    )


_thread_state = threading.local()


def _thread_session():
    session = getattr(_thread_state, 'session', None)
    if session is None:
        session = make_session()
        _thread_state.session = session
    return session


def _parse_tcu_sumulas_text(text: str) -> list[JurisprudenciaRecord]:
    cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    records = []
    pattern = re.compile(
        r"(?is)S[ÚU]MULA\s+TCU\s+(\d+)\s*(?:\(([^)]+)\))?\s*:\s*(.+?)(?=\n\s*(?:Acórdão|Decisão)\b|\n\s*S[ÚU]MULA\s+TCU\s+\d+\s*(?:\(|:)|\Z)"
    )
    for match in pattern.finditer(cleaned):
        number = int(match.group(1))
        status = clean_text(match.group(2) or "")
        enunciado = _strip_markup(clean_text(match.group(3)))
        if not enunciado:
            continue
        records.append(
            JurisprudenciaRecord(
                tribunal="TCU",
                tipo_documento="sumula",
                numero_processo=f"Súmula TCU {number}",
                numero_sumula=str(number),
                numero_decisao=str(number),
                tipo_decisao="Súmula",
                orgao_julgador="Plenário",
                ementa=enunciado,
                situacao=status or "VIGENTE",
                url_oficial=TCU_SUMULA_CATALOG_URL,
                origem="TCU — Repertório oficial de Súmulas",
            )
        )
    return records


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


def _fetch_tcu_sumula(_session, numero: int) -> JurisprudenciaRecord | None:
    session = _thread_session()
    urls = (
        TCU_SUMULA_URL.format(numero=numero),
        TCU_SUMULA_SEARCH_URL.format(numero=numero),
    )
    for url in urls:
        response = session.get(url, timeout=(8, 45), allow_redirects=True)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        records = _parse_tcu_sumulas_page(response.content)
        for record in records:
            if record.numero_sumula == str(numero):
                return record
    return None


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
            visited_urls = set()
            for _ in range(max_pages):
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeoutError:
                    pass
                body_text = page.locator("body").inner_text(timeout=10000)
                for record in _parse_tcu_sumulas_text(body_text):
                    number = int(record.numero_sumula or 0)
                    if 1 <= number <= max_number:
                        by_number[number] = record
                current_url = page.url
                if current_url in visited_urls:
                    break
                visited_urls.add(current_url)

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
                before_signature = body_text[-4000:]
                page.locator("a,button").nth(next_index).click()
                try:
                    page.wait_for_function(
                        "(oldText) => document.body && document.body.innerText.slice(-4000) !== oldText",
                        arg=before_signature,
                        timeout=10000,
                    )
                except PlaywrightTimeoutError:
                    break
        finally:
            browser.close()
    return [by_number[number] for number in sorted(by_number)]


def collect_tcu_sumulas(session=None, max_number: int = TCU_SUMULA_MAX_NUMBER) -> list[JurisprudenciaRecord]:
    session = session or make_session()
    try:
        response = session.get(TCU_SUMULA_CATALOG_URL, timeout=(8, 60), allow_redirects=True)
        response.raise_for_status()
        records = _parse_tcu_sumulas_page(response.content)
    except requests.RequestException:
        records = []
    if records:
        by_number = {}
        for record in records:
            number = int(record.numero_sumula or 0)
            if 1 <= number <= max_number:
                by_number[number] = record
        if len(by_number) >= 1:
            return [by_number[number] for number in sorted(by_number)]
    return _collect_tcu_sumulas_browser(max_number=max_number)


def collect_tcesp_sumulas(session=None) -> list[JurisprudenciaRecord]:
    session = session or make_session()
    response = session.get(TCESP_SUMULA_URL, timeout=(8, 45), allow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "aside"]):
        tag.decompose()
    text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    matches = list(re.finditer(
        r"(?ims)^S[ÚU]MULA\s+N[ºO°]?\s*(\d+)\s*-\s*(.*?)(?=^S[ÚU]MULA\s+N[ºO°]?\s*\d+\s*-|\Z)",
        text,
    ))
    records = []
    for match in matches:
        number = int(match.group(1))
        block = match.group(2).strip()
        block = re.sub(r"\(Veja histórico e fundamento\)", "", block, flags=re.I)
        cancelled = bool(re.search(r"\bCANCELADA\b", block, re.I))
        enunciado = re.sub(r"\s+", " ", block).strip()
        enunciado = re.sub(r"\s*\(CANCELADA\)\s*", " ", enunciado, flags=re.I)
        enunciado = _strip_markup(enunciado)
        if not enunciado:
            continue
        records.append(JurisprudenciaRecord(
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
        ))
    return sorted(records, key=lambda item: int(item.numero_decisao or 0))


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
    print("Smoke súmulas OK: TCU 222, 247, 259, 263, 292 | TCESP 1-53")


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
        tcu_numbers = {int(item.numero_decisao) for item in result['tcu'] if item.numero_decisao and item.numero_decisao.isdigit()}
        if not tcu_numbers:
            failures.append('TCU: nenhuma súmula estruturada foi encontrada')
        else:
            tcu_max = max(tcu_numbers)
            missing = sorted(set(range(1, tcu_max + 1)) - tcu_numbers)
            if tcu_max < 290 or missing:
                detail = f'; ausentes={missing[:10]}' if missing else ''
                failures.append(f'TCU: cobertura estrutural incompleta até a súmula {tcu_max}{detail}')
        tcesp_numbers = {int(item.numero_decisao) for item in result['tcesp'] if item.numero_decisao and item.numero_decisao.isdigit()}
        if tcesp_numbers != set(range(1, 54)):
            missing = sorted(set(range(1, 54)) - tcesp_numbers)
            failures.append(f'TCESP: cobertura estrutural incompleta; ausentes={missing}')
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
