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
    assert all(item["segment_kind"] in {"caput", "paragrafo"} for item in chunks)


def test_semantic_group_validation_rejects_missing_or_reordered_ids():
    with pytest.raises(SemanticChunkingError):
        _validate_groups(
            {"groups": [{"ids": ["B0001", "B0000"], "topic": "", "section": ""}]},
            ["B0000", "B0001"],
        )
