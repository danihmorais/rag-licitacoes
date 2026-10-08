import requests

import config
from .base import LLMProvider, LLMProviderError, raise_provider_error


class OllamaProvider(LLMProvider):
    def __init__(self, host: str, model: str, temperature: float, timeout: int, num_ctx: int | None = None, max_tokens: int | None = None):
        super().__init__(model, temperature, timeout)
        self.host = host.rstrip("/")
        self.num_ctx = int(num_ctx or config.OLLAMA_NUM_CTX)
        self.max_tokens = int(config.LLM_MAX_TOKENS if max_tokens is None else max_tokens)
        if self.num_ctx < 4096:
            raise ValueError("num_ctx do Ollama deve ser >= 4096.")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens do Ollama deve ser maior que zero.")

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "keep_alive": config.OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
                "num_predict": self.max_tokens if max_tokens is None else int(max_tokens),
            },
        }
        response = None
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise_provider_error(exc, "Ollama", response)
        except ValueError as exc:
            raise LLMProviderError("Ollama retornou JSON inválido.") from exc

        answer = data.get("response")
        if not answer:
            raise LLMProviderError("O Ollama não retornou o campo 'response'.")
        return answer.strip()
