from types import SimpleNamespace

import config
import ingest
import query
from chunking import build_structural_chunks
from metadata import embedding_metadata_prefix, extract_metadata
from qdrant_client import models


def test_normative_children_propagate_caput_and_hierarchy():
    text = (
        "LEI Nº 14.133, DE 1º DE ABRIL DE 2021.\n"
        "CAPÍTULO I\n"
        "Art. 1º A licitação observará os princípios da legalidade e da eficiência.\n"
        "§ 1º O procedimento será motivado.\n"
        "I - a decisão será fundamentada.\n"
        "a) com publicidade.\n"
        "Art. 2º Regra independente."
    )
    chunks = build_structural_chunks(text, 500, 50)
    children = [item for item in chunks if item["segment_kind"] in {"paragrafo", "inciso", "alinea"}]
    assert children
    assert all("A licitação observará os princípios" in item["text"] for item in children)
    assert all(item["hierarchy_headers"][0].startswith("LEI Nº 14.133") for item in children)
    assert all(item["hierarchy_path"][-1] for item in children)


def test_embedding_prefix_contains_regime_status_and_esfera(tmp_path):
    path = tmp_path / "lei14133.pdf"
    path.write_bytes(b"")
    metadata = extract_metadata(
        "LEI Nº 14.133, DE 1º DE ABRIL DE 2021.\nArt. 1º Regra.",
        path,
    )
    prefix = embedding_metadata_prefix(metadata)
    assert metadata["regime_juridico"] == "lei_14133"
    assert "[REGIME: Lei 14.133/2021" in prefix
    assert "ESFERA: federal" in prefix


def test_old_regimes_are_hard_excluded_for_normal_queries():
    compiled = query.qfilter({}, "regra de licitação")
    assert compiled is not None
    assert compiled.must_not
    assert compiled.must_not[0].key == "regime_juridico"
    assert set(compiled.must_not[0].match.any) == {"lei_8666"}


def test_transition_query_does_not_apply_hard_exclusion():
    compiled = query.qfilter({}, "transição entre a Lei 8.666/1993 e a Lei 14.133/2021")
    assert compiled is None


class TransactionClient:
    def __init__(self):
        self.events = []
        self.old = SimpleNamespace(
            id="old",
            vector={"dense": [0.1], "sparse": models.SparseVector(indices=[0], values=[1.0])},
            payload={"doc_id": "doc-1", "text": "versao antiga"},
        )

    def scroll(self, **kwargs):
        return [self.old], None

    def delete(self, **kwargs):
        self.events.append(("delete", kwargs.get("points_selector")))

    def upsert(self, **kwargs):
        self.events.append(("upsert", kwargs["points"]))
        if len([event for event in self.events if event[0] == "upsert"]) == 1:
            raise RuntimeError("falha simulada")


def test_document_replacement_rolls_back_when_upsert_fails():
    client = TransactionClient()
    new = SimpleNamespace(id="new", vector={"dense": [0.2]}, payload={"doc_id": "doc-1"})
    try:
        ingest.replace_document_points(client, "doc-1", [new])
    except RuntimeError as exc:
        assert "versão anterior restaurada" in str(exc)
    else:
        raise AssertionError("falha de upsert deveria acionar rollback")
    assert [event[0] for event in client.events] == ["delete", "upsert", "delete", "upsert"]
