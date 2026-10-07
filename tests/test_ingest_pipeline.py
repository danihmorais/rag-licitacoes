from pathlib import Path


def test_ingest_uses_structural_chunking_without_llm_preprocessing():
    source = (Path(__file__).parents[1] / "ingest.py").read_text(encoding="utf-8")

    assert "get_llm_provider('semantic_chunking')" not in source
    assert "get_cpu_tokenizer()" not in source
    assert "precomputed_chunks" not in source
    assert "AI_CHUNKING" not in source
    assert "Carregando modelos de embeddings/reranker na GPU." in source
    assert "CACHE_VERSION = 1" in source

    gpu_runtime = source.index("config.validate_gpu_runtime()")
    gpu_dense = source.index("TextEmbedding(model_name=config.DENSE_MODEL")
    structural = source.index("build_structural_chunks(")
    assert gpu_dense > structural
    assert gpu_runtime < gpu_dense
