import re
from types import SimpleNamespace


import chunking
from chunking import build_structural_chunks


class TruncatingTokenizer:
    def __init__(self, max_length=512):
        self.max_length = max_length
        self.truncated = True

    @property
    def truncation(self):
        return {"max_length": self.max_length} if self.truncated else {}

    def no_truncation(self):
        self.truncated = False

    def enable_truncation(self, max_length=512):
        self.max_length = max_length
        self.truncated = True

    def encode(self, text):
        tokens = text.split()
        if self.truncated:
            tokens = tokens[:self.max_length]
        return SimpleNamespace(ids=tokens)


def test_default_tokenizer_disables_fastembed_truncation(monkeypatch):
    import fastembed

    tokenizer = TruncatingTokenizer()
    text = " ".join(["palavra"] * 2000)

    class FakeTextEmbedding:
        def __init__(self, **kwargs):
            self.model = SimpleNamespace(tokenizer=tokenizer)

    monkeypatch.setattr(fastembed, "TextEmbedding", FakeTextEmbedding)
    chunking._default_tokenizer.cache_clear()
    try:
        loaded = chunking._default_tokenizer()
        assert loaded is tokenizer
        assert len(loaded.encode(text).ids) == 2000
    finally:
        chunking._default_tokenizer.cache_clear()

def test_cpu_tokenizer_does_not_request_cuda(monkeypatch):
    import fastembed

    tokenizer = TruncatingTokenizer()
    providers_seen = []

    class FakeTextEmbedding:
        def __init__(self, **kwargs):
            providers_seen.append(kwargs["providers"])
            self.model = SimpleNamespace(tokenizer=tokenizer)

    monkeypatch.setattr(fastembed, "TextEmbedding", FakeTextEmbedding)
    chunking._default_tokenizer.cache_clear()
    try:
        loaded = chunking.get_cpu_tokenizer()
        assert loaded is tokenizer
        assert providers_seen == [["CPUExecutionProvider"]]
    finally:
        chunking._default_tokenizer.cache_clear()


def test_truncating_tokenizer_is_disabled_before_chunk_sizing():
    tokenizer = TruncatingTokenizer()
    text = " ".join(["palavra"] * 2000)
    chunks = chunking.build_structural_chunks(text, 1000, 0, tokenizer=tokenizer)

    assert len(chunks) > 1
    assert chunking._token_count(text, tokenizer) == 2000
    assert all(chunking._token_count(item["text"], tokenizer) <= 1000 for item in chunks)


def test_long_unit_is_not_duplicated():
    text='Art. 1º '+'Texto juridico. '*200+'\n\nArt. 2º Regra.\n\nArt. 3º Regra.\n\nArt. 4º Regra.'
    xs=[x for x in build_structural_chunks(text,500,50) if x['unit_ref'].startswith('Art. 1')]
    assert len(xs)>1 and all(x['full_unit_text'] is None for x in xs)
    assert [x['chunk_index'] for x in xs]==list(range(len(xs)))

def test_small_units_keep_text():
    xs=build_structural_chunks('Art. 1º A.\n\nArt. 2º B.\n\nArt. 3º C.\n\nArt. 4º D.',500,50)
    assert len(xs)==4 and all(x['full_unit_text']==x['text'] for x in xs)


def test_child_chunking_handles_long_caput_with_default_overlap():
    caput = 'A regra constitucional aplicável à Administração Pública deve observar planejamento, transparência, eficiência e controle. ' * 20
    text = f'Art. 1º {caput.strip()}\n§ 1º O disposto neste artigo aplica-se às contratações públicas com as adaptações previstas em lei.'
    xs = build_structural_chunks(text, 1000, 150)
    assert xs
    tokenizer = chunking._default_tokenizer()
    assert all(chunking._token_count(item['text'], tokenizer) <= 1000 for item in xs)
    children = [item for item in xs if item['segment_kind'] == 'paragrafo']
    assert children
    assert all(chunking._token_count(item['text'], tokenizer) <= 1000 for item in children)
    assert all(' > § 1º' in item['text'] for item in children)


def test_article_children_preserve_parent_hierarchy():
    text = (
        'Art. 10. Regra do caput.\n'
        'I - hipótese um;\n'
        'a) subhipótese A;\n'
        'b) subhipótese B;\n'
        'II - hipótese dois;\n'
        'a) subhipótese C;\n'
        'b) subhipótese D;\n'
    )
    chunks = build_structural_chunks(text, 500, 50)
    alinea_chunks = [item for item in chunks if item['segment_kind'] == 'alinea']
    assert [item['segment_ref'] for item in alinea_chunks] == ['a)', 'b)', 'a)', 'b)']
    assert alinea_chunks[0]['hierarchy_path'][-2:] == ['I -', 'a)']
    assert alinea_chunks[1]['hierarchy_path'][-2:] == ['I -', 'b)']
    assert alinea_chunks[2]['hierarchy_path'][-2:] == ['II -', 'a)']
    assert alinea_chunks[3]['hierarchy_path'][-2:] == ['II -', 'b)']
    assert 'Art. 10. > I - > a)' in alinea_chunks[0]['text']
    assert 'Art. 10. > II - > a)' in alinea_chunks[2]['text']


def test_item_preserves_alinea_parent_hierarchy():
    text = (
        'Art. 11. Regra do caput.\n'
        'I - hipótese;\n'
        'a) subhipótese;\n'
        '1) item um;\n'
        '2) item dois;\n'
    )
    chunks = build_structural_chunks(text, 500, 50)
    items = [item for item in chunks if item['segment_kind'] == 'item']
    assert len(items) == 2
    assert items[0]['hierarchy_path'][-3:] == ['I -', 'a)', '1)']
    assert items[1]['hierarchy_path'][-3:] == ['I -', 'a)', '2)']

def test_written_paragrafo_unico_resets_hierarchy_for_items():
    text = (
        "Art. 70. Regra do caput.\n"
        "I - hipótese um;\n"
        "II - hipótese dois;\n"
        "Parágrafo único. Considera-se: 1. bem público; 2. bem dominical."
    )
    chunks = build_structural_chunks(text, 500, 50)
    paragrafo = [item for item in chunks if item["segment_kind"] == "paragrafo"]
    items = [item for item in chunks if item["segment_kind"] == "item"]
    assert len(paragrafo) == 1
    assert paragrafo[0]["segment_ref"].casefold().startswith("parágrafo único")
    assert [item["segment_ref"] for item in items] == ["1.", "2."]
    assert items[0]["hierarchy_path"][-2:] == ["Parágrafo único.", "1."]
    assert items[1]["hierarchy_path"][-2:] == ["Parágrafo único.", "2."]
    assert all("II -" not in item["hierarchy_path"] for item in items)


def test_pdf_soft_wrap_detects_inline_article_and_nested_children():
    text = (
        "Texto anterior sem quebra Art. 10. Regra do caput: "
        "I - hipótese um; a) subhipótese A; b) subhipótese B; "
        "II - hipótese dois; a) subhipótese C."
    )
    chunks = build_structural_chunks(text, 500, 50)
    articles = [item for item in chunks if item["segment_kind"] == "alinea"]
    assert len(articles) == 3
    assert articles[0]["hierarchy_path"][-2:] == ["I -", "a)"]
    assert articles[1]["hierarchy_path"][-2:] == ["I -", "b)"]
    assert articles[2]["hierarchy_path"][-2:] == ["II -", "a)"]


def test_article_citation_at_line_start_is_not_mistaken_for_article_unit():
    text = (
        "Art. 5º da CF garante direitos fundamentais citados no parecer.\n"
        "Art. 6º Regra normativa efetiva."
    )
    chunks = build_structural_chunks(text, 500, 50)
    assert [item["unit_ref"] for item in chunks] == ["Art. 6º"]


def test_concatenated_jurisprudencia_is_split_into_independent_units(monkeypatch):
    text = (
        "TRIBUNAL: TCU\nPROCESSO: TC 000.001/2026\n"
        "EMENTA: Primeira decisão sobre planejamento da contratação.\n"
        + ("Fundamentação do TCU. " * 20)
        + "\n\nTRIBUNAL: STJ\nPROCESSO: REsp 000002/SP\n"
        "EMENTA: Segunda decisão sobre habilitação.\n"
        + ("Fundamentação do STJ. " * 20)
    )
    chunks = build_structural_chunks(text, 300, 30)
    assert {item["unit_ref"] for item in chunks} == {
        "TC 000.001/2026",
        "REsp 000002/SP",
    }
    assert all(
        not (
            item["unit_ref"] == "TC 000.001/2026"
            and "TRIBUNAL: STJ" in item["text"]
        )
        for item in chunks
    )
    assert all(
        not (
            item["unit_ref"] == "REsp 000002/SP"
            and "TRIBUNAL: TCU" in item["text"]
        )
        for item in chunks
    )


def test_child_prefix_keeps_both_ends_of_long_caput():
    from chunking import _fit_child_prefix

    caput = (
        "INICIO DA REGRA: planejamento obrigatório e transparente. "
        + ("Meio do dispositivo. " * 30)
        + "CONDICAO FINAL OBRIGATORIA: somente nos casos expressamente previstos."
    )
    prefix = _fit_child_prefix(
        f"Art. 20.\n{caput}",
        "I - hipótese subordinada.",
        180,
    )
    assert "CAPUT (trechos inicial e final):" not in prefix
    assert caput in prefix
    assert "INICIO DA REGRA" in prefix
    assert "CONDICAO FINAL OBRIGATORIA" in prefix


def test_ocr_structural_markers_are_normalized_without_changing_source_text():
    from chunking import _article_children, _article_units

    text = (
        "Preâmbulo.\n"
        "Artig0 10. Regra principal.\n"
        "Paragraf0 unic0. A Administração deverá observar a regra.\n"
    )
    units = _article_units(text)
    assert len(units) == 1
    assert units[0]["ref"] == "Artigo 10."
    assert units[0]["text"].startswith("Artig0 10.")

    caput, children = _article_children(units[0]["text"])
    assert caput == "Artig0 10. Regra principal."
    assert len(children) == 1
    kind, ref, child_text, _, _ = children[0]
    assert kind == "paragrafo"
    assert ref.casefold().startswith("paragrafo unico")
    assert child_text.startswith("Paragraf0 unic0.")

    chunks = build_structural_chunks(text, 500, 50)
    assert chunks[0]["text"].startswith("Artig0 10.")
    assert any("Paragraf0 unic0." in chunk["text"] for chunk in chunks)


def test_ocr_article_marker_does_not_break_nested_hierarchy():
    text = (
        "Art1g0 20. Regra do caput. "
        "I - hipótese; a) subhipótese; b) outra subhipótese."
    )
    chunks = build_structural_chunks(text, 500, 50)
    alinea = [item for item in chunks if item["segment_kind"] == "alinea"]
    assert [item["hierarchy_path"][-2:] for item in alinea] == [
        ["I -", "a)"],
        ["I -", "b)"],
    ]