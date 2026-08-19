import requests

from .base import LLMError, LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    """Adapter for OpenAI-compatible /v1/chat/completions endpoints."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float,
        timeout: int,
    ):
        super().__init__(model, temperature, timeout)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise LLMError(
                "RAG_OPENAI_API_KEY não está configurada para o provedor OpenAI-compatible."
            )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise LLMError(
                f"Falha no provedor OpenAI-compatible ({self.base_url}): {exc}"
            ) from exc
        except ValueError as exc:
            raise LLMError("O provedor retornou uma resposta JSON inválida.") from exc

        try:
            answer = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Resposta inesperada do provedor OpenAI-compatible.") from exc

        if isinstance(answer, list):
            answer = "".join(
                part.get("text", "") for part in answer if isinstance(part, dict)
            )
        if not answer:
            raise LLMError("O provedor não retornou conteúdo na resposta.")
        return str(answer).strip()
