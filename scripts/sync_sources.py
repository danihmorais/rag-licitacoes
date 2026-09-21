from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import httpx
from bs4 import BeautifulSoup
from scripts.sources import SOURCES, SourceSpec
from scripts.sources_additional import ADDITIONAL_SOURCES
from config import SETTINGS

CACHE = SETTINGS.cache_dir
HEADERS = {"User-Agent": "rag-licitacoes/1.0"}

def _safe(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("_")

def _fetch(url: str) -> str:
    r = httpx.get(url, timeout=SETTINGS.request_timeout, follow_redirects=True, headers=HEADERS)
    r.raise_for_status()
    return r.text

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def write_cache(source: SourceSpec, text: str, links: list[str] | None = None):
    CACHE.mkdir(parents=True, exist_ok=True)
    body = {"source_id": source.source_id, "title": source.title, "url": source.url,
            "jurisdiction": source.jurisdiction, "sphere": source.sphere,
            "source_role": source.source_role, "authority_level": source.authority_level,
            "tribunal": source.tribunal, "hash": _hash(text), "content": text, "links": links or []}
    path = CACHE / f"{_safe(source.source_id)}.json"
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return path

def discover_links(url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http://") or href.startswith("https://"):
            if href.lower().endswith((".pdf",".html",".htm")):
                out.append(href)
    return sorted(set(out))

def sync_sources(include_additional: bool = True) -> list[str]:
    sources = SOURCES + (ADDITIONAL_SOURCES if include_additional else [])
    done = []
    for source in sources:
        try:
            html = _fetch(source.url)
            links = discover_links(source.url, html) if source.follow_links else []
            done.append(str(write_cache(source, html, links)))
        except Exception as exc:
            print(f"FAIL {source.source_id}: {exc}")
    return done

if __name__ == "__main__":
    for p in sync_sources():
        print(p)
