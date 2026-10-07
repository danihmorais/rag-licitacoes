import os
import re
import uuid
from pathlib import Path

import pytest

import config
import ingest
import query
from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from qdrant_client import models


RUN_REAL_E2E = os.getenv('RAG_RUN_REAL_MODEL_E2E', '0').strip().lower() in {
    '1', 'true', 'yes', 'on'
}


@pytest.mark.skipif(
    not RUN_REAL_E2E,
    reason='E2E com modelos reais desabilitado; use RAG_RUN_REAL_MODEL_E2E=1.',
)
def test_real_models_round_trip_through_qdrant_and_evidence_gate(tmp_path: Path):
    client = config.create_qdrant_client()
    try:
        client.get_collections()
    except Exception as exc:
        pytest.fail(f'Qdrant Server indisponível em {config.QDRANT_URL}: {exc}')

    fixture = Path(__file__).resolve().parent / 'fixtures' / 'legal_act.txt'
    document = tmp_path / 'lei14133.txt'
    source_text = fixture.read_text(encoding='utf-8')
    document.write_text(source_text, encoding='utf-8')

    dense = TextEmbedding(
        model_name=config.DENSE_MODEL,
        max_length=config.DENSE_MAX_TOKENS,
        **query.embedding_kwargs(),
    )
    sparse = SparseTextEmbedding(
        model_name=config.SPARSE_MODEL,
        **query.embedding_kwargs(),
    )
    reranker = TextCrossEncoder(
        model_name=config.RERANK_MODEL,
        **query.embedding_kwargs(),
    )
    tokenizer = getattr(getattr(dense, 'model', None), 'tokenizer', None)
    assert tokenizer is not None, 'Tokenizer real do embedding não ficou disponível.'

    chunks = ingest.build_chunks(document, [source_text], tokenizer=tokenizer)
    assert chunks
    dense_vectors = list(dense.embed([chunk['embedding_text'] for chunk in chunks]))
    sparse_vectors = list(sparse.embed([chunk['page_content'] for chunk in chunks]))

    collection = f'real-e2e-{uuid.uuid4().hex}'
    client.create_collection(
        collection_name=collection,
        vectors_config={
            'dense': models.VectorParams(
                size=config.DENSE_DIM,
                distance=models.Distance.COSINE,
            ),
        },
        sparse_vectors_config={'sparse': models.SparseVectorParams()},
    )
    original_collection = config.COLLECTION_NAME
    config.COLLECTION_NAME = collection
    try:
        points = []
        for index, chunk in enumerate(chunks):
            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        'dense': dense_vectors[index].tolist(),
                        'sparse': models.SparseVector(
                            indices=sparse_vectors[index].indices.tolist(),
                            values=sparse_vectors[index].values.tolist(),
                        ),
                    },
                    payload=chunk,
                )
            )
        client.upsert(collection_name=collection, points=points, wait=True)

        query_text = 'Quais são os princípios da licitação?'
        candidates = query.hybrid(client, dense, sparse, query_text, None)
        reranked = query.rerank(reranker, query_text, candidates, limit=3)
        assert reranked

        retrieved_text = str(
            reranked[0].payload.get('source_text')
            or reranked[0].payload.get('text')
            or ''
        ).strip()
        claim = re.split(r'(?<=[.!?])\s+', retrieved_text, maxsplit=1)[0].strip(' .')
        assert claim
        answer = f'{claim}. [F1]'
        assert query.validate_generated_answer(answer, reranked[:1]) is True
    finally:
        config.COLLECTION_NAME = original_collection
        client.delete_collection(collection)
