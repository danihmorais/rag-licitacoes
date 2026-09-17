from scripts.sources import SOURCES
from scripts.sync_sources import discover_links, normalized_pattern


def test_pdf_follow_pattern_accepts_normal_and_double_escaped_regex():
    html = '<main><a href="/docs/a.pdf">PDF oficial</a><a href="/docs/b.html">HTML</a></main>'
    normal = r"\.pdf(?:$|\?)"
    overescaped = normal.replace("\", "\\")
    source = {"follow_patterns": [overescaped], "max_follow": 10}
    assert normalized_pattern(overescaped) == normal
    assert discover_links(html, "https://example.gov.br/pagina", source) == [("https://example.gov.br/docs/a.pdf", "PDF oficial")]


def test_source_catalog_is_unique_and_broad():
    ids = [item["id"] for item in SOURCES]
    assert len(ids) == len(set(ids))
    required = {"lei14133","cf1988","lei9784","lei8429","lei12846","lei12527","lei13709","lei13303","lei8987","lei11079","lrf","lei4320","lc123","lei13019","lei13460","lei14129","pl-cp5212","pl-ms12016","pl-acp7347","pl-9868","pl-9882","pl-8112","pl-13869","pl-5172","pl-6830","pl-11107","pl-13089","pl-8080","pl-9394","pl-8742","pl-6938","pl-12651","pl-9433","pl-9985","pl-10257","pl-6766","pl-13465","pl-11445","pl-14026","pl-dl3365","pl-14230","pl-lc173","pl-12232","pl-13243","pl-10973","pl-15432","sp-const","sp-lei10177","sp-10261","sp-lc709","tcu-dados-jurisprudencia","stj-jurisprudencia","stf-jurisprudencia"}
    assert required <= set(ids)
    areas = {item.get("ramo_direito") for item in SOURCES if item.get("ramo_direito")}
    assert {"Constitucional","Administrativo","Processual Público","Tributário","Financeiro e Orçamentário","Ambiental","Urbanístico","Saúde Pública","Educação Pública","Assistência Social","Pessoal e Servidores","Serviços Públicos"} <= areas


def test_discovery_indexes_are_not_indexed_as_corpus_documents():
    index_ids = {"pl-camara-federal","pl-lexml","pl-leis-2026","pl-leis-2025","pl-lc-atualizadas","pl-decretos-2026"}
    catalog = {item["id"]: item for item in SOURCES}
    assert all(catalog[item].get("index_only") is True for item in index_ids)
