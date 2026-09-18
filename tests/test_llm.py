import pytest
import requests

from llm.base import LLMQuotaError, LLMTimeoutError
from llm.ollama import OllamaProvider
from llm.openai_compatible import OpenAICompatibleProvider


class FakeResponse:
    status_code = 200
    text = ''

    def raise_for_status(self):
        return None

    def json(self):
        return {'choices': [{'message': {'content': [{'text': 'Resposta '}, {'text': 'jurídica.'}]}}]}


def test_openai_compatible_extracts_list_content_and_max_tokens(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured['url'] = url
        captured['json'] = kwargs['json']
        return FakeResponse()

    monkeypatch.setattr('llm.openai_compatible.requests.post', fake_post)
    provider = OpenAICompatibleProvider('http://example.test/v1', '', 'local', 0.1, 30, 256)
    answer = provider.generate('system', 'question')
    assert answer == 'Resposta jurídica.'
    assert captured['url'] == 'http://example.test/v1/chat/completions'
    assert captured['json']['max_tokens'] == 256


def test_ollama_sends_configured_context_window(monkeypatch):
    captured = {}

    class FakeOllamaResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "ok"}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        return FakeOllamaResponse()

    monkeypatch.setattr("llm.ollama.requests.post", fake_post)
    provider = OllamaProvider("http://example.test", "model", 0.1, 30, num_ctx=16384)
    assert provider.generate("system", "user") == "ok"
    assert captured["json"]["options"]["num_ctx"] == 16384


def test_openai_compatible_maps_timeout(monkeypatch):
    def fake_post(*args, **kwargs):
        raise requests.Timeout("timed out")

    monkeypatch.setattr("llm.openai_compatible.requests.post", fake_post)
    provider = OpenAICompatibleProvider("http://example.test/v1", "", "local", 0.1, 1)
    with pytest.raises(LLMTimeoutError):
        provider.generate("system", "question")


def test_openai_compatible_maps_rate_limit(monkeypatch):
    class FakeRateLimitResponse:
        status_code = 429
        text = "rate limited"

        def raise_for_status(self):
            raise requests.HTTPError("429")

    monkeypatch.setattr("llm.openai_compatible.requests.post", lambda *args, **kwargs: FakeRateLimitResponse())
    provider = OpenAICompatibleProvider("http://example.test/v1", "", "local", 0.1, 1)
    with pytest.raises(LLMQuotaError):
        provider.generate("system", "question")
