def test_qdrant_server_is_the_default_backend():
    import config

    assert config.QDRANT_URL == "http://127.0.0.1:6333"
    assert config.QDRANT_PREFER_GRPC is True


def test_qdrant_client_uses_server_configuration(monkeypatch):
    import config

    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(__import__("sys").modules, "qdrant_client", type(
        "QdrantModule",
        (),
        {"QdrantClient": FakeClient},
    ))

    config.create_qdrant_client()

    assert captured["url"] == config.QDRANT_URL
    assert captured["prefer_grpc"] is config.QDRANT_PREFER_GRPC
    assert captured["timeout"] == config.QDRANT_TIMEOUT
    assert captured["api_key"] is None or captured["api_key"] == config.QDRANT_API_KEY
