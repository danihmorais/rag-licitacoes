from scripts.sources import SOURCES
from scripts.sources_additional import EXTRA_SOURCES
from scripts.sync_sources import discover_links, normalized_pattern


def test_pdf_follow_pattern_accepts_normal_and_double_escaped_regex():
    html = '<main><a href="/docs/a.pdf">PDF oficial</a><a href="/docs/b.html">HTML</a></main>'
    normal = r"\.pdf(?:$|\?)"
    overescaped = normal.replace("\\", "\\\\")
    source = {"follow_patterns": [overescaped], "max_follow": 10}
    assert normalized_pattern(overescaped) == normal
    assert discover_links(html, "https://example.gov.br/pagina", source) == [("https://example.gov.br/docs/a.pdf", "PDF oficial")]


def test_source_catalog_has_unique_ids_and_current_jurisprudence():
    sources = [dict(item) for item in SOURCES] + [dict(item) for item in EXTRA_SOURCES]
    ids = [item["id"] for item in sources]
    assert len(ids) == len(set(ids))
    required = {"lei14133","cf1988","sp-const","tcesp","tcesp-srp","decreto11462","decreto11878","in65","in58","in81","sp-pca","lei14770","lei15190","lei15266","lei15471","decreto13031","decreto13106","tcu-dados-jurisprudencia","stj-jurisprudencia","stf-jurisprudencia"}
    assert required <= set(ids)
