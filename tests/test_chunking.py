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
