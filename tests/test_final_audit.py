import json
from pathlib import Path
from index_manifest import current_manifest
from metadata import extract_metadata

def test_manifest_hashes_logic():
    m=current_manifest()
    assert len(m["chunking_sha256"])==64
    assert len(m["metadata_sha256"])==64
    assert m["algorithm_version"]

def test_jurisprudence_authority_normalization(tmp_path:Path):
    p=tmp_path/"x.pdf"; p.write_bytes(b"%PDF")
    Path(str(p)+".json").write_text(json.dumps({"tribunal":"STF","source_role":"jurisprudencia"}),encoding="utf-8")
    assert extract_metadata(p,"TRIBUNAL: STF")["authority_level"]==2

def test_hierarchy_in_prompt():
    from llm.openai_compatible import SYSTEM_PROMPT
    assert "Constituição/lei/decreto/ato normativo" in SYSTEM_PROMPT
