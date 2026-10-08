import numpy as np

import dense_embeddings


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

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
