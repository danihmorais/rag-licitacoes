import requests

from .base import LLMError, LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, host: str, model: str, temperature: float, timeout: int):
        super().__init__(model, temperature, timeout)
        self.host = host.rstrip("/")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise LLMError(
                f"Não foi possível consultar o Ollama em {self.host}: {exc}"
            ) from exc
        except ValueError as exc:
            raise LLMError("O Ollama retornou uma resposta JSON inválida.") from exc

        answer = data.get("response")
        if not answer:
            raise LLMError("O Ollama não retornou o campo 'response'.")
        return answer.strip()
