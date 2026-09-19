from __future__ import annotations

import concurrent.futures
import re

import requests
import threading
from bs4 import BeautifulSoup

import config
from .collector import clean_text, make_session
from .schema import JurisprudenciaRecord

TCU_SUMULA_URL = "https://pesquisa.apps.tcu.gov.br/resultado/sumula/{numero}"
TCESP_SUMULA_URL = "https://www.tce.sp.gov.br/boletim-de-jurisprudencia/sumulas"


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


def _fetch_tcu_sumula(_session, numero: int) -> JurisprudenciaRecord | None:
    url = TCU_SUMULA_URL.format(numero=numero)
    response = _thread_session().get(url, timeout=(8, 45), allow_redirects=True)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return _tcu_record(numero, response.content)


def collect_tcu_sumulas(session=None, max_number: int = 400) -> list[JurisprudenciaRecord]:
    session = session or make_session()
    numbers = range(1, max_number + 1)
    records: list[JurisprudenciaRecord] = []
    workers = 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_fetch_tcu_sumula, session, number): number for number in numbers}
        for future in concurrent.futures.as_completed(futures):
            try:
                record = future.result()
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                number = futures[future]
                print(f"  aviso: Súmula TCU {number} indisponível: {type(exc).__name__}: {exc}")
                continue
            if record is not None:
                records.append(record)
    records.sort(key=lambda item: int(item.numero_decisao or 0))
    return records


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
