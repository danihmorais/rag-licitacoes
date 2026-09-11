import json

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
