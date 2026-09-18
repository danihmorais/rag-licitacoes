import os

import pytest
import requests


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    if os.getenv("RAG_ALLOW_NETWORK_TESTS", "0").strip().lower() in {"1", "true", "yes"}:
        return
    def blocked_request(self, method, url, *args, **kwargs):
        raise AssertionError(
            f"Rede externa desabilitada na suíte de testes: {method} {url}"
        )
    monkeypatch.setattr(requests.sessions.Session, "request", blocked_request)
