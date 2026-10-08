import requests

from .base import LLMProvider, LLMProviderError, raise_provider_error


class GeminiProvider(LLMProvider):
    """Minimal Gemini REST adapter; no Google SDK is required."""

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float,
        timeout: int,
        max_tokens: int = 1024,
    ):
        super().__init__(model, temperature, timeout)
        self.api_key = api_key
        self.max_tokens = int(max_tokens)

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
        if not self.api_key:
            raise LLMProviderError("GEMINI_API_KEY não está configurada para o provedor Gemini.")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        params = {"key": self.api_key}
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens if max_tokens is None else int(max_tokens),
            },
        }

        response = None
        try:
            response = requests.post(url, params=params, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise_provider_error(exc, 'Gemini', response)
        except ValueError as exc:
            raise LLMProviderError("O Gemini retornou uma resposta JSON inválida.") from exc

        try:
            parts = data["candidates"][0]["content"]["parts"]
            answer = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("Resposta inesperada do Gemini.") from exc

        if not answer:
            raise LLMProviderError("O Gemini não retornou texto na resposta.")
        return answer.strip()
