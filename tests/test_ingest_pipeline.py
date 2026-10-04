from pathlib import Path


def test_ingest_precomputes_semantic_chunks_before_gpu_models():
    source = (Path(__file__).parents[1] / "ingest.py").read_text(encoding="utf-8")
    semantic_provider = source.index("get_llm_provider('semantic_chunking')")
    cpu_tokenizer = source.index("get_cpu_tokenizer()")
    phase_two = source.index("Fase 2/2: carregando modelos de embeddings/reranker na GPU.")
    gpu_dense = source.index("TextEmbedding(model_name=config.DENSE_MODEL")
    precomputed_argument = source.index("precomputed_chunks=semantic_precomputed.get(document.name)")

    assert semantic_provider < phase_two
    assert cpu_tokenizer < phase_two
    assert gpu_dense > phase_two
    assert precomputed_argument > phase_two
    assert "CACHE_VERSION = 5" in source
