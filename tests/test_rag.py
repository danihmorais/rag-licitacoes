from pathlib import Path
from chunking import build_structural_chunks
from metadata import extract_metadata

def test_structural_ids_include_position():
    text="Art. 1º Primeiro.\n\nArt. 1º Segundo."
    chunks=build_structural_chunks(text)
    keys={(c.unit_id,c.chunk_index) for c in chunks}
    assert len(keys)==len(chunks)

def test_sidecar_authority(tmp_path:Path):
    p=tmp_path/"decisao.pdf"; p.write_bytes(b"%PDF")
    Path(str(p)+".json").write_text('{"tribunal":"TCESP","source_role":"jurisprudencia_controle"}',encoding="utf-8")
    assert extract_metadata(p,"TRIBUNAL: TCESP")["authority_level"]==4
