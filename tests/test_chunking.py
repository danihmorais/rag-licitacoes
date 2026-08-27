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
