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



def _collect_tcu_sumulas_by_number(session, max_number: int = TCU_SUMULA_MAX_NUMBER) -> list[JurisprudenciaRecord]:
    records = []
    for number in range(1, max_number + 1):
        try:
            record = _fetch_tcu_sumula(session, number)
        except requests.RequestException:
            continue
        if record is not None:
            records.append(record)
    return records


def collect_tcu_sumulas(session=None, max_number: int = TCU_SUMULA_MAX_NUMBER) -> list[JurisprudenciaRecord]:
    session = session or make_session()
    return _collect_tcu_sumulas_by_number(session, max_number=max_number)


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
