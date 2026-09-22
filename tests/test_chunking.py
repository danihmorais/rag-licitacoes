import json
import re

import pytest

from chunking import build_structural_chunks
from llm.semantic_chunker import SemanticChunkingError, _validate_groups


class FakeSemanticProvider:
    model = "fake-semantic"

    def __init__(self):
        self.calls = 0

    def generate(self, system_prompt, user_prompt):
        self.calls += 1
        ids = re.findall(r"^ID (B\d{4})$", user_prompt, re.MULTILINE)
        groups = []
        for index in range(0, len(ids), 2):
            groups.append({
                "ids": ids[index:index + 2],
                "topic": f"tema-{index // 2 + 1}",
                "section": "fundamentação",
            })
        return json.dumps({"groups": groups}, ensure_ascii=False)


class ExplodingProvider:
    def __init__(self):
        self.calls = 0

    def generate(self, system_prompt, user_prompt):
        self.calls += 1
        raise AssertionError("provider não deveria ser chamado para norma")



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
    assert all(len(item['text']) <= 1000 for item in xs)
    children = [item for item in xs if item['segment_kind'] == 'paragrafo']
    assert children
    assert all(len(item['text']) <= 1000 for item in children)
    assert all(' > § 1º' in item['text'] for item in children)


def test_split_text_clamps_overlap_when_available_chunk_is_smaller():
    from chunking import _split_text
    xs = _split_text('abcdef', 1, 150)
    assert xs == list('abcdef')


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

def test_ai_semantic_chunking_preserves_source_and_returns_metadata(monkeypatch):
    text = (
        "TRIBUNAL: TCU\nPROCESSO: TC 000.000/2026\n\n"
        "Contexto fático e histórico da contratação. A Administração descreveu a necessidade do objeto e os fatos relevantes.\n\n"
        "A questão jurídica submetida ao tribunal envolve habilitação e qualificação técnica. Foram analisados os requisitos do edital e a legislação aplicável.\n\n"
        "A fundamentação examina a proporcionalidade da exigência e os efeitos sobre a competitividade do certame.\n\n"
        "Conclusão: o colegiado fixou o entendimento aplicável ao caso concreto, conforme a fundamentação apresentada."
    )
    provider = FakeSemanticProvider()
    monkeypatch.setattr("config.AI_CHUNKING_ENABLED", True)
    monkeypatch.setattr("config.AI_CHUNKING_MIN_CHARS", 100)
    chunks = build_structural_chunks(
        text,
        1000,
        50,
        metadata={
            "source_role": "jurisprudencia",
            "tipo_documento": "jurisprudencia",
            "processo": "TC 000.000/2026",
        },
        semantic_provider=provider,
    )
    assert provider.calls >= 1
    assert chunks
    assert all(item["chunking_method"] == "ai_semantic" for item in chunks)
    assert all(item["page_content"] == item["text"] for item in chunks)
    assert all(item["chunking_model"] == "fake-semantic" for item in chunks)
    assert all(item["semantic_source_units"] for item in chunks)
    assert any("A questão jurídica submetida" in item["text"] for item in chunks)
    assert any("Conclusão:" in item["text"] for item in chunks)


def test_normative_documents_never_call_semantic_provider(monkeypatch):
    text = (
        "LEI Nº 14.133, DE 1º DE ABRIL DE 2021\n\n"
        "Art. 1º Esta Lei estabelece normas gerais de licitação e contratação.\n"
        "Parágrafo único. A Administração deverá observar os princípios previstos nesta Lei."
    ) * 20
    provider = ExplodingProvider()
    monkeypatch.setattr("config.AI_CHUNKING_ENABLED", True)
    monkeypatch.setattr("config.AI_CHUNKING_MIN_CHARS", 100)
    chunks = build_structural_chunks(
        text,
        1000,
        50,
        metadata={"source_role": "norma", "tipo_documento": "lei"},
        semantic_provider=provider,
    )
    assert provider.calls == 0
    assert chunks
    assert any(item["segment_kind"] == "paragrafo" for item in chunks)
    assert all(item["segment_kind"] in {"caput", "paragrafo"} for item in chunks)


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


def test_semantic_chunking_failure_falls_back_to_structural(monkeypatch):
    text = (
        "MANUAL DE LICITAÇÕES DO TCU\n\n"
        + ("Orientação sobre planejamento, governança e fiscalização da contratação. " * 80)
    )
    provider = ExplodingProvider()
    monkeypatch.setattr("config.AI_CHUNKING_ENABLED", True)
    monkeypatch.setattr("config.AI_CHUNKING_REQUIRED", True)
    monkeypatch.setattr("config.AI_CHUNKING_FALLBACK_TO_STRUCTURAL", True)
    monkeypatch.setattr("config.AI_CHUNKING_MIN_CHARS", 100)
    chunks = build_structural_chunks(
        text,
        500,
        50,
        metadata={"source_role": "orientacao_oficial", "tipo_documento": "manual"},
        semantic_provider=provider,
    )
    assert provider.calls >= 1
    assert chunks
    assert all(item["chunking_method"] == "structural" for item in chunks)
    assert all(item["segment_kind"] == "generic" for item in chunks)


def test_concatenated_jurisprudencia_falls_back_as_a_whole_when_one_unit_fails(monkeypatch):
    class FailOnSecondCallProvider(FakeSemanticProvider):
        def generate(self, system_prompt, user_prompt):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("segunda unidade indisponível")
            ids = re.findall(r"^ID (B\d{4})$", user_prompt, re.MULTILINE)
            return json.dumps(
                {
                    "groups": [
                        {
                            "ids": ids,
                            "topic": "primeira unidade",
                            "section": "fundamentação",
                        }
                    ]
                },
                ensure_ascii=False,
            )

    text = (
        "TRIBUNAL: TCU\nPROCESSO: TC 000.100/2026\n\n"
        + ("Contexto TCU sobre planejamento. " * 20)
        + "\n\nTRIBUNAL: STJ\nPROCESSO: REsp 000200/SP\n\n"
        + ("Contexto STJ sobre habilitação. " * 20)
    )
    provider = FailOnSecondCallProvider()
    monkeypatch.setattr("config.AI_CHUNKING_ENABLED", True)
    monkeypatch.setattr("config.AI_CHUNKING_REQUIRED", True)
    monkeypatch.setattr("config.AI_CHUNKING_FALLBACK_TO_STRUCTURAL", True)
    monkeypatch.setattr("config.AI_CHUNKING_MIN_CHARS", 100)
    monkeypatch.setattr("config.AI_CHUNKING_ATTEMPTS", 1)

    chunks = build_structural_chunks(
        text,
        500,
        50,
        metadata={"source_role": "jurisprudencia", "tipo_documento": "jurisprudencia"},
        semantic_provider=provider,
    )
    assert provider.calls == 2
    assert chunks
    assert all(item["chunking_method"] == "structural" for item in chunks)
    assert {item["unit_ref"] for item in chunks} == {
        "TC 000.100/2026",
        "REsp 000200/SP",
    }


def test_semantic_provider_initialization_failure_falls_back_to_structural(monkeypatch):
    text = "Manual TCU.\n\n" + ("Conteúdo jurídico do manual. " * 80)
    monkeypatch.setattr("config.AI_CHUNKING_ENABLED", True)
    monkeypatch.setattr("config.AI_CHUNKING_REQUIRED", True)
    monkeypatch.setattr("config.AI_CHUNKING_FALLBACK_TO_STRUCTURAL", True)
    monkeypatch.setattr("config.AI_CHUNKING_MIN_CHARS", 100)

    def fail_provider(purpose="answer"):
        raise RuntimeError(f"LLM indisponível para {purpose}")

    monkeypatch.setattr("llm.factory.get_llm_provider", fail_provider)
    chunks = build_structural_chunks(
        text,
        500,
        50,
        metadata={"source_role": "orientacao_oficial", "tipo_documento": "manual"},
    )
    assert chunks
    assert all(item["chunking_method"] == "structural" for item in chunks)


def test_semantic_chunking_strict_mode_still_raises(monkeypatch):
    text = "Manual TCU.\n\n" + ("Conteúdo jurídico do manual. " * 80)
    provider = ExplodingProvider()
    monkeypatch.setattr("config.AI_CHUNKING_ENABLED", True)
    monkeypatch.setattr("config.AI_CHUNKING_REQUIRED", True)
    monkeypatch.setattr("config.AI_CHUNKING_FALLBACK_TO_STRUCTURAL", False)
    monkeypatch.setattr("config.AI_CHUNKING_MIN_CHARS", 100)
    with pytest.raises(SemanticChunkingError):
        build_structural_chunks(
            text,
            500,
            50,
            metadata={"source_role": "orientacao_oficial", "tipo_documento": "manual"},
            semantic_provider=provider,
        )


def test_semantic_group_validation_rejects_missing_or_reordered_ids():
    with pytest.raises(SemanticChunkingError):
        _validate_groups(
            {"groups": [{"ids": ["B0001", "B0000"], "topic": "", "section": ""}]},
            ["B0000", "B0001"],
        )


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
    monkeypatch.setattr("config.AI_CHUNKING_ENABLED", False)
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


def test_ai_semantic_chunking_keeps_concatenated_jurisprudencia_separate(monkeypatch):
    text = (
        "TRIBUNAL: TCU\nPROCESSO: TC 000.010/2026\n\n"
        + ("Contexto TCU sobre planejamento. " * 80)
        + "\n\nTRIBUNAL: STJ\nPROCESSO: REsp 000020/SP\n\n"
        + ("Contexto STJ sobre habilitação. " * 80)
    )
    provider = FakeSemanticProvider()
    monkeypatch.setattr("config.AI_CHUNKING_ENABLED", True)
    monkeypatch.setattr("config.AI_CHUNKING_MIN_CHARS", 100)
    chunks = build_structural_chunks(
        text,
        1000,
        50,
        metadata={"source_role": "jurisprudencia", "tipo_documento": "jurisprudencia"},
        semantic_provider=provider,
    )
    refs = {item["unit_ref"] for item in chunks}
    assert refs == {"TC 000.010/2026", "REsp 000020/SP"}
    assert provider.calls == 2
    assert all(item["chunking_method"] == "ai_semantic" for item in chunks)


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
    assert "CAPUT (trechos inicial e final):" in prefix
    assert "INICIO DA REGRA" in prefix
    assert "CONDICAO FINAL OBRIGATORIA" in prefix


def test_split_text_does_not_split_after_common_legal_abbreviation():
    from chunking import _split_text

    text = "Art. 1º A regra inicial. " + ("Conteúdo jurídico complementar. " * 30)
    pieces = _split_text(text, 30, 0)
    assert all(piece.strip() != "Art." for piece in pieces)
    assert "Art. 1º" in pieces[0]


def test_locator_does_not_jump_to_repeated_text_before_expected_position():
    from chunking import _locate_piece

    text = "Parágrafo único. primeiro bloco. Parágrafo único. segundo bloco."
    first = text.find("Parágrafo único.")
    second = text.find("Parágrafo único.", first + 1)
    found, uncertain = _locate_piece(
        text,
        "Parágrafo único.",
        first + 4,
        second - first,
    )
    assert found == second
    assert uncertain is False

def test_ocr_structural_markers_are_normalized_without_changing_source_text():
    text = (
        "Preâmbulo.\n"
        "Artig0 10. Regra principal.\n"
        "Paragraf0 unic0. A Administração deverá observar a regra.\n"
    )
    chunks = build_structural_chunks(text, 500, 50)
    assert len(chunks) == 2
    assert chunks[0]["unit_ref"] == "Artigo 10."
    assert chunks[0]["text"].startswith("Artig0 10.")
    paragrafo = [item for item in chunks if item["segment_kind"] == "paragrafo"]
    assert len(paragrafo) == 1
    assert paragrafo[0]["segment_ref"].casefold().startswith("paragrafo unico")
    assert "Paragraf0 unic0." in paragrafo[0]["text"]


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
