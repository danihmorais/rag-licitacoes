import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from chunking import build_structural_chunks
from query import build_retrieval_plan, expand_context, hybrid, rerank, validate_generated_answer


class FixtureTokenizer:
    def no_truncation(self):
        pass

    def encode(self, text):
        return SimpleNamespace(ids=text.split())


class _Vector(list):
    def tolist(self):
        return list(self)


class _SparseVector:
    def __init__(self):
        self.indices = _Vector([0])
        self.values = _Vector([1.0])


class _FixtureDense:
    def embed(self, texts):
        for text in texts:
            normalized = str(text).casefold()
            yield _Vector([1.0, 0.0, 0.0] if 'normas gerais' in normalized else [0.0, 1.0, 0.0])


class _FixtureSparse:
    def embed(self, texts):
        return [_SparseVector() for _ in texts]


class _FixtureReranker:
    def rerank(self, query, texts):
        return [8.0 if 'normas gerais' in str(text).casefold() else -8.0 for text in texts]


def test_real_fixture_lei_14133_preserves_article_sequence_and_unit_ids():
    fixture = Path(__file__).resolve().parent / "fixtures" / "legal_act.txt"
    text = fixture.read_text(encoding="utf-8")
    chunks = build_structural_chunks(text, max_size=2000, overlap=150, tokenizer=None)
    articles = [item["unit_ref"] for item in chunks if item["unit_kind"] == "artigo"]
    unit_ids = [item["unit_id"] for item in chunks if item["unit_kind"] == "artigo"]

    assert articles[:4] == ["Art. 1º", "Art. 2º", "Art. 3º", "Art. 4º"]
    assert articles[-1] == "Art. 8º"
    assert len(articles) == 8
    assert len(set(unit_ids)) == len(unit_ids)


def test_official_legal_excerpts_are_hashed_structural_fixtures():
    fixture = Path(__file__).resolve().parent / "fixtures" / "legal_real_excerpts.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    sources = payload["sources"]

    assert len(sources) == 10
    assert sum(source["role"] == "norma" for source in sources) == 5
    assert sum(source["role"] == "alteradora" for source in sources) == 5

    for source in sources:
        text = source["text"]
        assert source["official_url"].startswith("https://www.planalto.gov.br/")
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == source["sha256"]

        chunks = build_structural_chunks(text, 512, 0, tokenizer=FixtureTokenizer())
        assert chunks, source["source_id"]
        for chunk in chunks:
            start = chunk["source_start"]
            end = chunk["source_end"]
            assert text[start:end] == chunk["source_text"], source["source_id"]

        if source["role"] == "alteradora":
            amendment_chunks = [chunk for chunk in chunks if chunk.get("amendment")]
            assert amendment_chunks, source["source_id"]
            assert any(chunk.get("target_devices") for chunk in amendment_chunks), source["source_id"]


def test_retrieval_plan_builds_the_qdrant_contract_for_real_queries():
    plan = build_retrieval_plan("quais são as regras da Lei 14.133/2021 e da Lei 8.666/1993?")

    assert plan["is_transition"] is True
    assert plan["regime_hint"] == "lei_14133"
    assert plan["mandatory_sources"] == ["lei14133", "tcu-manual-licitacoes"]
    assert plan["qdrant_filter"] is None
    assert "Lei 14.133/2021" in plan["retrieval_query"]
    assert "Lei 8.666/1993" in plan["retrieval_query"]
    assert plan["filtered_for_current_only"] is False


def test_qdrant_server_e2e_from_official_fixture(tmp_path, monkeypatch):
    """Exercises source extraction through evidence validation against Qdrant Server.

    The encoders are deliberately deterministic test doubles.  Qdrant itself remains
    real, so this catches server schema, payload, upsert, hybrid retrieval, reranking,
    context expansion, and evidence-gate regressions without downloading a model.
    """
    if os.getenv('RAG_E2E_QDRANT') != '1':
        pytest.skip('requires RAG_E2E_QDRANT=1 and a Qdrant Server')

    import config
    import ingest
    from qdrant_client import models

    fixture = Path(__file__).resolve().parent / 'fixtures' / 'legal_real_excerpts.json'
    records = json.loads(fixture.read_text(encoding='utf-8'))['sources']
    source = next(item for item in records if item['source_id'] == 'lei14133')
    document = tmp_path / 'lei14133.txt'
    document.write_text(source['text'], encoding='utf-8')
    document.with_suffix('.json').write_text(
        json.dumps({
            'source_id': source['source_id'],
            'title': source['title'],
            'fonte_oficial': source['official_url'],
            'status': 'vigente',
            'jurisdicao': 'federal',
        }),
        encoding='utf-8',
    )

    collection = f'licitacoes-e2e-{uuid.uuid4().hex}'
    monkeypatch.setattr(config, 'COLLECTION_NAME', collection)
    monkeypatch.setattr(config, 'DENSE_DIM', 3)
    monkeypatch.setattr(config, 'DENSE_MAX_TOKENS', 512)
    monkeypatch.setattr(config, 'CHUNK_SIZE', 256)
    monkeypatch.setattr(config, 'CHUNK_OVERLAP', 0)
    monkeypatch.setattr(config, 'QDRANT_PREFER_GRPC', False)
    monkeypatch.setattr(config, 'CANDIDATES_K', 10)
    monkeypatch.setattr(config, 'FINAL_K', 3)
    monkeypatch.setattr(config, 'MIN_EVIDENCE_SCORE', 0.0)

    client = config.create_qdrant_client()
    try:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        ingest.ensure_collection(client)

        page_records = ingest.extract_page_records(document)
        chunks = ingest.build_chunks(
            document,
            [item['text'] for item in page_records],
            page_records=page_records,
            tokenizer=FixtureTokenizer(),
        )
        assert chunks
        assert all(chunk['document_regime'] == 'lei_14133' for chunk in chunks)
        assert all(chunk['source_text'] for chunk in chunks)
        assert all(chunk['device_id'] for chunk in chunks)

        dense = _FixtureDense()
        sparse = _FixtureSparse()
        dense_vectors = list(dense.embed([chunk['embedding_text'] for chunk in chunks]))
        sparse_vectors = list(sparse.embed([chunk['page_content'] for chunk in chunks]))
        points = [
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector={
                    'dense': dense_vector.tolist(),
                    'sparse': models.SparseVector(
                        indices=sparse_vector.indices.tolist(),
                        values=sparse_vector.values.tolist(),
                    ),
                },
                payload=chunk,
            )
            for chunk, dense_vector, sparse_vector in zip(chunks, dense_vectors, sparse_vectors)
        ]
        ingest.upsert_points(client, points)

        plan = build_retrieval_plan('Quais normas gerais de licitação a Lei 14.133 estabelece?')
        retrieved = hybrid(client, dense, sparse, plan['query'], plan['qdrant_filter'])
        assert retrieved
        ranked = rerank(_FixtureReranker(), plan['query'], retrieved, limit=3)
        assert ranked
        expanded = expand_context(client, ranked)
        assert expanded
        assert expanded[0].payload['source_id'] == 'lei14133'
        assert expanded[0].payload['document_regime'] == 'lei_14133'
        assert expanded[0].payload['source_text'] == source['text'][
            expanded[0].payload['source_start']:expanded[0].payload['source_end']
        ]
        validate_generated_answer(
            'Esta Lei estabelece normas gerais de licitação e contratação. [F1]',
            expanded,
        )
    finally:
        if client.collection_exists(collection):
            client.delete_collection(collection)
