from scripts.sources import SOURCES
from pathlib import Path
import pytest

from scripts.sync_sources import discover_links, normalized_pattern, validate


def test_pdf_follow_pattern_accepts_normal_and_double_escaped_regex():
    normal = "\\.pdf(?:$|\\?)"
    overescaped = normal.replace("\\", "\\\\")
    source = {"follow_patterns": [overescaped], "max_follow": 10}
    html = '<main><a href="/docs/a.pdf">PDF oficial</a><a href="/docs/b.html">HTML</a></main>'
    assert normalized_pattern(overescaped) == normal
    assert discover_links(html, "https://example.gov.br/pagina", source) == [("https://example.gov.br/docs/a.pdf", "PDF oficial")]


def test_source_catalog_is_unique_and_broad():
    ids = [item["id"] for item in SOURCES]
    assert len(ids) == len(set(ids))
    required = {"cf1988","lei14133","lei9784","lei8429","lei12846","lei12527","lei13709","lei13303","lei8987","lei11079","lrf","lei4320","lc123","lei13019","lei13460","lei14129","decreto11462","decreto11878","in65","in58","in81","sp-pca","lei14770","lei15190","lei15266","lei15471","decreto13031","decreto13106","pl-14230","pl-lc173","pl-12232","pl-13243","pl-10973","sp-const","sp-lei10177","sp-lai","tcesp-srp","lei4717","lei7347","lc131","decreto7724","lei6019","lei12016","lc182","spm-decreto62100","spm-decreto62436","spm-decreto64863","spm-in-seges6-2023","spm-pgm38-2025","sp-pge-pareceres"}
    assert required <= set(ids)
    retired = {"tcu","tcesp","tcu-dados-jurisprudencia","tcu-jurisprudencia-pesquisa","stj-jurisprudencia","stj-teses","stj-repetitivos-iacs","stj-sumulas-anotadas","stj-legislacao-aplicada","stj-informativos","stf-jurisprudencia","stf-repercussao-geral","stf-teses-rg","stf-tesauro","tjsp-jurisprudencia","tjsp-saj-jurisprudencia"}
    assert retired.isdisjoint(set(ids))
    areas = {item.get("ramo_direito") for item in SOURCES if item.get("ramo_direito")}
    assert {"Constitucional","Administrativo","Processual Público","Tributário","Financeiro e Orçamentário","Ambiental","Urbanístico","Saúde Pública","Educação Pública","Assistência Social","Pessoal e Servidores","Serviços Públicos"} <= areas


def test_discovery_indexes_are_not_indexed_as_corpus_documents():
    index_ids = {"pl-discovery-camara","pl-discovery-lexml","pl-discovery-leis-2026","pl-discovery-leis-2025","pl-discovery-lc-atualizadas","pl-discovery-decretos-2026"}
    catalog = {item["id"]: item for item in SOURCES}
    index_ids.update({"pncp", "compras", "compras-in", "sp-compras", "sp-pge-pareceres", "pl-discovery-camara", "pl-discovery-lexml", "pl-discovery-leis-2026", "pl-discovery-leis-2025", "pl-discovery-lc-atualizadas", "pl-discovery-decretos-2026"})
    assert all(catalog[item].get("index_only") is True for item in index_ids)



def test_no_duplicate_primary_source_urls():
    urls = [url for item in SOURCES if not item.get("index_only") for url in item.get("urls", [])]
    assert len(urls) == len(set(urls))


ROOT = Path(__file__).resolve().parents[1]


def test_validator_rejects_spa_portal_shell():
    shell = (ROOT / "tests" / "fixtures" / "spa_shell.html").read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="casca de portal"):
        validate(next(item for item in SOURCES if item["id"] == "lei14133"), shell)


def test_validator_rejects_wrong_normative_identity():
    legal = (ROOT / "tests" / "fixtures" / "legal_act.txt").read_text(encoding="utf-8").replace("14.133", "13.999")
    with pytest.raises(RuntimeError, match="identidade normativa"):
        validate(next(item for item in SOURCES if item["id"] == "lei14133"), legal)


def test_validator_accepts_structured_normative_content():
    legal = (ROOT / "tests" / "fixtures" / "legal_act.txt").read_text(encoding="utf-8")
    validate(next(item for item in SOURCES if item["id"] == "lei14133"), legal)


def test_validator_accepts_official_guidance_content():
    guidance = (ROOT / "tests" / "fixtures" / "pge_guidance.txt").read_text(encoding="utf-8")
    validate(next(item for item in SOURCES if item["id"] == "sp-pge-pareceres"), guidance, linked=True)
