import re

import chunking


def test_roman_incises_cover_xl_through_c():
    assert re.fullmatch(rf"{chunking.ROMAN_RE}", "XL")
    assert re.fullmatch(rf"{chunking.ROMAN_RE}", "XLI")
    assert re.fullmatch(rf"{chunking.ROMAN_RE}", "XLVIII")
    assert re.fullmatch(rf"{chunking.ROMAN_RE}", "LXXVIII")
    assert re.fullmatch(rf"{chunking.ROMAN_RE}", "XCIX")
    assert re.fullmatch(rf"{chunking.ROMAN_RE}", "C")
    assert not re.fullmatch(rf"{chunking.ROMAN_RE}", "CI")


def test_inciso_xl_e_xlviii_nao_somem():
    text = (
        "Art. 75. Regra geral.\n"
        "XL - hipótese quarenta.\n"
        "XLI - hipótese quarenta e um.\n"
        "XLVIII - hipótese quarenta e oito.\n"
        "LXXVIII - hipótese setenta e oito.\n"
        "C - hipótese cem.\n"
    )
    chunks = chunking.build_structural_chunks(text, 1000, 0, tokenizer=None)
    incisos = [item for item in chunks if item["segment_kind"] == "inciso"]
    assert [item["segment_ref"] for item in incisos] == [
        "XL -",
        "XLI -",
        "XLVIII -",
        "LXXVIII -",
        "C -",
    ]


def test_alineas_accept_double_letters_uppercase_and_parenthesized_form():
    text = (
        "Art. 5º Requisitos:\n"
        "I - condição.\n"
        "aa) alínea composta.\n"
        "AB - alínea maiúscula.\n"
        "II - outra condição.\n"
        "(a) alínea parentetizada.\n"
        "Parágrafo único - fechamento.\n"
        "1. item do parágrafo único.\n"
    )
    chunks = chunking.build_structural_chunks(text, 1000, 0, tokenizer=None)
    alinea = [item for item in chunks if item["segment_kind"] == "alinea"]
    assert [item["segment_ref"] for item in alinea] == ["aa)", "AB -", "(a)"]
    assert alinea[0]["hierarchy_path"][-2:] == ["I -", "aa)"]
    assert alinea[1]["hierarchy_path"][-2:] == ["I -", "AB -"]
    assert alinea[2]["hierarchy_path"][-2:] == ["II -", "(a)"]


def test_named_inciso_and_alinea_markers_are_supported():
    text = (
        "Art. 6º Regra.\n"
        "Inciso XLVIII - hipótese.\n"
        "Alínea aa) detalhe.\n"
    )
    chunks = chunking.build_structural_chunks(text, 1000, 0, tokenizer=None)
    assert [item["segment_kind"] for item in chunks] == ["caput", "inciso", "alinea"]
    assert chunks[1]["hierarchy_path"][-1] == "Inciso XLVIII -"
    assert chunks[2]["hierarchy_path"][-1] == "Alínea aa)"


def test_article_citation_with_leading_words_is_not_a_new_unit():
    text = (
        "Art. 10. Regra válida.\n"
        "Conforme o Art. 75. da CF, deve observar também esta regra.\n"
        "Art. 11. Outra regra.\n"
    )
    units = chunking._article_units(text)
    assert [unit["ref"] for unit in units] == ["Art. 10.", "Art. 11."]


def test_flattened_articles_and_children_use_one_linear_structural_scan(monkeypatch):
    text = (
        "LEI Nº 14.133, DE 1º DE ABRIL DE 2021\n"
        "CAPÍTULO I\n"
        "Art. 75. Regra geral: I - inciso XLVIII; a) alínea aa; b) outra.\n"
        "Art. 76. Regra seguinte: C - inciso cem.\n"
    )

    def fail_headers_before(*_args, **_kwargs):
        raise AssertionError("_headers_before não deve ser chamado pelo parser principal")

    monkeypatch.setattr(chunking, "_headers_before", fail_headers_before)
    units = chunking._article_units(text)
    assert [unit["ref"] for unit in units] == ["Art. 75.", "Art. 76."]
    assert units[0]["headers"] == ["LEI Nº 14.133, DE 1º DE ABRIL DE 2021", "CAPÍTULO I"]


def test_ocr_structure_view_never_changes_offsets():
    text = "Artig0 10. Regra.\nCAPÍTUL0 I\nArt1g0 20. Outra regra.\n"
    normalized = chunking._ocr_structure_view(text)
    assert len(normalized) == len(text)
    assert "Artigo 10." in normalized
    assert "CAPITULO I" in normalized
    assert "Artigo 20." in normalized


def test_offsets_still_point_into_original_ocr_text():
    text = (
        "Artig0 10. Regra principal.\n"
        "§ 1º A Administração deverá observar a regra.\n"
        "Art1g0 20. Regra seguinte.\n"
    )
    chunks = chunking.build_structural_chunks(text, 1000, 0, tokenizer=None)
    for chunk in chunks:
        source = text[chunk["start"]:chunk["end"]]
        assert source.strip()
        assert source.strip() in chunk["text"]
