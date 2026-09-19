import re
from chunking import build_structural_chunks

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
