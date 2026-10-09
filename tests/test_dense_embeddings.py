import numpy as np

import dense_embeddings


class FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


def test_unsloth_embedding_batches_and_orders(monkeypatch):
    client = dense_embeddings.UnslothOpenAIEmbedding()
    client.batch_size = 2
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json, headers, timeout))
        batch = json["input"]
        data = [
            {"index": index, "embedding": [float(index + 1)] * dense_embeddings.config.DENSE_DIM}
            for index in reversed(range(len(batch)))
        ]
        return FakeResponse({"data": data})

    monkeypatch.setattr(client._session, "post", fake_post)
    vectors = client.embed(["a", "b", "c"])

    assert len(calls) == 2
    assert calls[0][1]["model"] == dense_embeddings.config.DENSE_MODEL
    assert calls[0][1]["encoding_format"] == "float"
    assert vectors.shape == (3, dense_embeddings.config.DENSE_DIM)
    assert np.all(vectors[0] == 1.0)
    assert np.all(vectors[1] == 2.0)
    assert np.all(vectors[2] == 1.0)


def test_unsloth_embedding_rejects_wrong_dimension(monkeypatch):
    client = dense_embeddings.UnslothOpenAIEmbedding()

    def fake_post(url, *, json, headers, timeout):
        return FakeResponse({"data": [{"index": 0, "embedding": [0.0]}]})

    monkeypatch.setattr(client._session, "post", fake_post)
    try:
        client.embed(["x"])
    except RuntimeError as exc:
        assert "dimensão" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")



def test_unsloth_embedding_recovers_from_studio_token_limit(monkeypatch):
    client = dense_embeddings.UnslothOpenAIEmbedding()
    client.batch_size = 8
    max_chars = 90
    attempted_lengths = []
    successful_lengths = []

    def fake_post(url, *, json, headers, timeout):
        batch = json["input"]
        attempted_lengths.extend(len(text) for text in batch)
        if any(len(text) > max_chars for text in batch):
            return FakeResponse(
                {"error": {"message": "input exceeds the 510-token limit"}},
                status_code=400,
                text="input exceeds the 510-token limit of unsloth/embeddinggemma-2.",
            )
        successful_lengths.extend(len(text) for text in batch)
        return FakeResponse({
            "data": [
                {"index": index, "embedding": [1.0 + index] * dense_embeddings.config.DENSE_DIM}
                for index in range(len(batch))
            ]
        })

    monkeypatch.setattr(client._session, "post", fake_post)
    long_text = dense_embeddings.config.DENSE_DOCUMENT_PREFIX + (
        "Contratação pública exige planejamento, justificativa e pesquisa de preços. " * 20
    )
    vectors = client.embed(["consulta curta", long_text])

    assert vectors.shape == (2, dense_embeddings.config.DENSE_DIM)
    assert max(attempted_lengths) > max_chars
    assert successful_lengths
    assert max(successful_lengths) <= max_chars
    assert np.isclose(np.linalg.norm(vectors[1]), 1.0)


def test_embeddinggemma_studio_limit_overrides_stale_env_value():
    config = dense_embeddings.config
    assert config.effective_dense_max_tokens(
        "unsloth/embeddinggemma-2",
        "unsloth_openai",
        8192,
    ) == config.DENSE_STUDIO_MAX_TOKENS
    assert config.effective_dense_max_tokens(
        "unsloth/embeddinggemma-2",
        "unsloth_openai",
        128,
    ) == 128
    assert config.effective_dense_max_tokens(
        "intfloat/multilingual-e5-large",
        "fastembed",
        512,
    ) == 512


def test_embeddinggemma_studio_limit_is_configurable(monkeypatch):
    config = dense_embeddings.config
    monkeypatch.setitem(config._DENSE_MODEL_API_TOKEN_LIMITS, "unsloth/embeddinggemma-2", 1000)

    assert config.effective_dense_max_tokens(
        "unsloth/embeddinggemma-2",
        "unsloth_openai",
        8192,
    ) == 1000
