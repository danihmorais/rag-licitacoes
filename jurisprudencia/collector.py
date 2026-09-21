from __future__ import annotations
import re
import time
from abc import ABC, abstractmethod
from typing import Iterable
import httpx
from bs4 import BeautifulSoup
from .schema import JurisprudenciaRecord

class TribunalAdapter(ABC):
    tribunal = "GEN"

    def __init__(self, timeout: float = 30.0):
        self.client = httpx.Client(timeout=timeout, follow_redirects=True, headers={
            "User-Agent": "rag-licitacoes/1.0 (+https://github.com/danihmorais/rag-licitacoes)"
        })

    @abstractmethod
    def search(self, query: str, limit: int = 50) -> Iterable[JurisprudenciaRecord]:
        raise NotImplementedError

    @staticmethod
    def _clean(value: str | None) -> str | None:
        if not value:
            return None
        return re.sub(r"\s+", " ", value).strip() or None

class TCUAdapter(TribunalAdapter):
    tribunal = "TCU"
    endpoint = "https://pesquisa.apps.tcu.gov.br/rest/publico/base-de-dados/search"

    def search(self, query: str, limit: int = 50):
        try:
            r = self.client.get(self.endpoint, params={"query": query, "size": limit})
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []
        items = data.get("content") or data.get("results") or data.get("items") or []
        for item in items[:limit]:
            ementa = self._clean(item.get("ementa") or item.get("texto") or item.get("summary"))
            if not ementa:
                continue
            yield JurisprudenciaRecord(
                tribunal="TCU",
                numero_processo=self._clean(item.get("processo") or item.get("numeroProcesso")),
                data_julgamento=self._clean(item.get("dataJulgamento") or item.get("data")),
                relator=self._clean(item.get("relator")),
                tipo=self._clean(item.get("tipo") or "Acórdão"),
                ementa=ementa,
                assunto=self._clean(item.get("assunto")),
                orgao_julgador=self._clean(item.get("colegiado") or item.get("orgao")),
                url=item.get("url"),
                fonte=self.endpoint,
                metadados={"raw": item},
            )

class GenericHtmlAdapter(TribunalAdapter):
    def __init__(self, tribunal: str, urls: list[str], timeout: float = 30.0):
        super().__init__(timeout)
        self.tribunal = tribunal
        self.urls = urls

    def search(self, query: str, limit: int = 50):
        for url in self.urls:
            try:
                r = self.client.get(url, params={"q": query, "query": query})
                r.raise_for_status()
            except Exception:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            text = soup.get_text("\n", strip=True)
            blocks = re.split(r"\n{2,}", text)
            for block in blocks[:limit * 3]:
                block = self._clean(block)
                if not block or len(block) < 120:
                    continue
                proc = re.search(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b", block)
                yield JurisprudenciaRecord(
                    tribunal=self.tribunal,
                    numero_processo=proc.group(0) if proc else None,
                    data_julgamento=None,
                    relator=None,
                    tipo="Jurisprudência",
                    ementa=block,
                    fonte=url,
                    url=url,
                )
                if limit <= 1:
                    return
                limit -= 1

def adapters() -> dict[str, TribunalAdapter]:
    return {
        "TCU": TCUAdapter(),
        "TCESP": GenericHtmlAdapter("TCESP", ["https://www.tce.sp.gov.br/"],),
        "STJ": GenericHtmlAdapter("STJ", ["https://www.stj.jus.br/sites/portalp/Paginas/Pesquisa.aspx"]),
        "STF": GenericHtmlAdapter("STF", ["https://jurisprudencia.stf.jus.br/pages/search"]),
    }

def collect(tribunal: str, query: str, limit: int = 50) -> list[JurisprudenciaRecord]:
    adapter = adapters()[tribunal.upper()]
    out = []
    for record in adapter.search(query, limit=limit):
        out.append(record)
        time.sleep(0.05)
    return out
