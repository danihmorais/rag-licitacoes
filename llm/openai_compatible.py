import requests

from .base import LLMProvider, LLMProviderError, raise_provider_error


class OpenAICompatibleProvider(LLMProvider):
    """Adapter para endpoints OpenAI-compatible /v1/chat/completions."""

    def __init__(self, base_url, api_key, model, temperature, timeout, max_tokens=0):
        super().__init__(model, temperature, timeout)
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.max_tokens = int(max_tokens or 0)

    def generate(self, system_prompt, user_prompt):
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': self.temperature,
        }
        if self.max_tokens > 0:
            payload['max_tokens'] = self.max_tokens
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        try:
            response = requests.post(
                f'{self.base_url}/chat/completions',
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise_provider_error(exc, f'OpenAI-compatible {self.base_url}', response)
        except ValueError as exc:
            raise LLMProviderError('O provedor retornou uma resposta JSON inválida.') from exc
        try:
            answer = data['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError('Resposta inesperada do provedor OpenAI-compatible.') from exc
        if isinstance(answer, list):
            fragments = []
            for part in answer:
                if not isinstance(part, dict):
                    continue
                text = part.get('text')
                if text is None and isinstance(part.get('content'), str):
                    text = part['content']
                if text:
                    fragments.append(str(text))
            answer = ''.join(fragments)
        if not isinstance(answer, str) or not answer.strip():
            raise LLMProviderError('O provedor não retornou conteúdo textual na resposta.')
        return answer.strip()
