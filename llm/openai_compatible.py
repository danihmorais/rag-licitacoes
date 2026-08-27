import requests
from .base import LLMError, LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    """Adapter para endpoints OpenAI-compatible /v1/chat/completions."""
    def __init__(self, base_url, api_key, model, temperature, timeout):
        super().__init__(model, temperature, timeout)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def generate(self, system_prompt, user_prompt):
        payload = {"model": self.model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "temperature": self.temperature}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise LLMError(f"Falha no provedor OpenAI-compatible ({self.base_url}): {exc}") from exc
        except ValueError as exc:
            raise LLMError("O provedor retornou uma resposta JSON inválida.") from exc
        try:
            answer = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Resposta inesperada do provedor OpenAI-compatible.") from exc
        if isinstance(answer, list):
            answer = "".join(part.get("text", "") for part in answer if isinstance(part, dict))
        if not answer:
            raise LLMError("O provedor não retornou conteúdo na resposta.")
        return str(answer).strip()
