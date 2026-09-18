from scripts.sources import SOURCE_BY_ID
from scripts.sync_sources import _expected_normative_number, _source_urls


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
