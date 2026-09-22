from types import SimpleNamespace

import chunking


class FakeEncoding:
    def __init__(self, ids):
        self.ids = ids


class FakeTokenizer:
    def encode(self, text):
        tokens = []
        for word in text.split():
            tokens.extend([word] * (3 if len(word) >= 8 else 1))
        return FakeEncoding(tokens)


def test_headers_preserve_all_hierarchy_levels():
    text = """LIVRO I
TÍTULO I
CAPÍTULO I
SEÇÃO I
SUBSEÇÃO I
Art. 1º Texto.
SEÇÃO II
Art. 2º Outro texto.
"""
    units = chunking._article_units(text)
    assert units[0]["headers"] == ["LIVRO I", "TÍTULO I", "CAPÍTULO I", "SEÇÃO I", "SUBSEÇÃO I"]
    assert units[1]["headers"] == ["LIVRO I", "TÍTULO I", "CAPÍTULO I", "SEÇÃO II", "SUBSEÇÃO I"]


def test_paragrafo_emendado_is_structural_unit():
    caput, children = chunking._article_children(
        "Art. 1º Regra principal.\n§ 3º-A Exceção incluída por emenda.\nIV - Outra regra."
    )
    assert caput == "Art. 1º Regra principal."
    assert [item[1] for item in children] == ["§ 3º-A", "IV -"]


def test_roman_false_positive_is_not_classified_as_inciso():
    _caput, children = chunking._article_children(
        "Art. 1º Regra.\nMIL. Texto que não é inciso.\nI - Inciso verdadeiro."
    )
    assert all(item[1] != "MIL." for item in children)
    assert any(item[0] == "inciso" and item[1].startswith("I") for item in children)


def test_prefix_truncation_is_explicit():
    tokenizer = FakeTokenizer()
    prefix = "Art. 1º\n" + " ".join(["condição"] * 80)
    fitted, truncated = chunking._fit_child_prefix(prefix, "IV - consequência " + "texto " * 20, 32, tokenizer)
    assert truncated is True
    assert fitted
    assert chunking._token_count(fitted, tokenizer) <= 32


def test_offsets_come_from_splitter_not_find():
    tokenizer = FakeTokenizer()
    text = "alpha repetido repetido. beta repetido repetido. gamma."
    spans = chunking._split_text_spans(text, 5, 0, tokenizer)
    for piece, start, end in spans:
        assert text[start:end] == piece


def test_token_budget_is_respected():
    tokenizer = FakeTokenizer()
    text = " ".join(["palavralonga"] * 100)
    spans = chunking._split_text_spans(text, 20, 0, tokenizer)
    assert spans
    assert all(chunking._token_count(piece, tokenizer) <= 20 for piece, _s, _e in spans)


def test_jurisprudencia_keeps_ementa_and_voto_separate():
    text = """TRIBUNAL: TCU
PROCESSO: 123
EMENTA:
Ementa com tese central.

RELATÓRIO:
Relatório factual.

VOTO:
Fundamentação do voto.

DISPOSITIVO:
Acordam.
"""
    units = chunking._jurisprudencia_units(text)
    assert units
    sections = chunking._jurisprudencia_sections(units[0]["text"])
    names = [item["section"] for item in sections]
    assert "ementa" in names
    assert "voto" in names
    assert "dispositivo" in names
    assert names.index("ementa") < names.index("voto") < names.index("dispositivo")


def test_structural_chunk_marks_prefix_truncation():
    tokenizer = FakeTokenizer()
    text = "CAPÍTULO I\nArt. 1º " + " ".join(["condição"] * 80) + "\nIV - " + " ".join(["consequência"] * 30)
    chunks = chunking.build_structural_chunks(text, 32, 0, tokenizer=tokenizer)
    child_chunks = [item for item in chunks if item.get("segment_kind") == "inciso"]
    assert child_chunks
    assert any(item["prefix_truncated"] for item in child_chunks)
