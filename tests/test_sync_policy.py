from scripts.sync_sources import (
    _expected_normative_number,
    _source_urls,
    apply_runtime_limits,
    strict_failure_ids,
)
from scripts.sources import SOURCE_BY_ID


def test_constitution_year_is_not_treated_as_normative_number():
    assert _expected_normative_number(SOURCE_BY_ID["cf1988"]) is None


def test_normative_numbers_are_extracted_without_the_year():
    assert _expected_normative_number(SOURCE_BY_ID["lei14133"]) == "14.133"
    assert _expected_normative_number(SOURCE_BY_ID["decreto12807"]) == "12.807"
    assert _expected_normative_number(SOURCE_BY_ID["lindb"]) == "4.657"


def test_official_fallback_urls_are_tried_after_primary():
    source = SOURCE_BY_ID["lei14133"]
    urls = _source_urls(source)
    assert urls[0] == "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm"
    assert urls[-1] == "https://www2.camara.leg.br/legin/fed/lei/2021/lei-14133-1-abril-2021-791222-normaatualizada-pl.html"


def test_every_explicit_legislation_source_has_a_retrieval_url():
    legislation = [
        source for source in SOURCE_BY_ID.values()
        if source.get("source_role") == "norma" and not source.get("index_only")
    ]
    assert legislation
    assert all(_source_urls(source) for source in legislation)


def test_strict_failure_ids_block_every_corpus_source():
    sources = [
        {"id": "norma", "source_role": "norma"},
        {"id": "orientacao", "source_role": "orientacao_oficial"},
        {"id": "web", "source_type": "web_articles"},
        {"id": "indice", "source_role": "descoberta_legislativa", "index_only": True},
    ]
    failures = ["norma", "orientacao", "web", "indice"]
    assert strict_failure_ids(sources, failures) == ["norma", "orientacao", "web"]


def test_strict_failure_ids_ignores_only_discovery_indexes():
    sources = [
        {"id": "indice-a", "index_only": True},
        {"id": "indice-b", "index_only": True},
    ]
    assert strict_failure_ids(sources, ["indice-a", "indice-b"]) == []


def test_runtime_limits_cap_only_web_sources_without_mutating_catalog():
    sources = [
        {"id": "web", "source_type": "web_articles", "max_documents": 250, "discovery_max_pages": 100},
        {"id": "lei", "source_role": "norma", "max_documents": 10, "discovery_max_pages": 10},
    ]

    limited = apply_runtime_limits(
        sources,
        max_web_documents=2,
        max_web_discovery_pages=5,
    )

    assert limited[0]["max_documents"] == 2
    assert limited[0]["discovery_max_pages"] == 5
    assert limited[1] == sources[1]
    assert sources[0]["max_documents"] == 250
    assert sources[0]["discovery_max_pages"] == 100


def test_runtime_limits_do_not_expand_existing_web_bounds():
    source = {"id": "web", "source_type": "web_articles", "max_documents": 2, "discovery_max_pages": 4}

    limited = apply_runtime_limits(
        [source],
        max_web_documents=10,
        max_web_discovery_pages=10,
    )

    assert limited[0]["max_documents"] == 2
    assert limited[0]["discovery_max_pages"] == 4
