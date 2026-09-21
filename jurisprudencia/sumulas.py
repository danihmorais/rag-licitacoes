from __future__ import annotations
import re
from pathlib import Path
import httpx
from bs4 import BeautifulSoup

TCU_SUMULAS_URL = "https://pesquisa.apps.tcu.gov.br/pesquisa/sumulas"

def collect_sumulas(strict: bool = True, minimum: int = 295) -> list[dict]:
    try:
        r = httpx.get(TCU_SUMULAS_URL, timeout=30.0, follow_redirects=True)
        r.raise_for_status()
    except Exception as exc:
        if strict:
            raise RuntimeError(f"Falha ao coletar súmulas TCU: {exc}") from exc
        return []

    soup = BeautifulSoup(r.text, "lxml")
    text = soup.get_text("\n", strip=True)
    matches = re.findall(r"S[ÚU]MULA\s+TCU\s+(\d+)\s*:\s*(.+?)(?=S[ÚU]MULA\s+TCU\s+\d+\s*:|$)", text, re.S | re.I)
    records = [{"tribunal":"TCU", "numero":int(n), "texto":re.sub(r"\s+"," ",t).strip(), "url":TCU_SUMULAS_URL} for n,t in matches]
    if strict and len(records) < minimum:
        raise RuntimeError(f"Falhas na coleta estruturada de súmulas: TCU: apenas {len(records)} súmulas estruturadas; esperado pelo menos {minimum}")
    return records
