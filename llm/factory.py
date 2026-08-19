import config

from .base import LLMProvider
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider


def get_llm_provider() -> LLMProvider:
    provider = config.LLM_PROVIDER.strip().lower()

    if provider == "ollama":
        return OllamaProvider(
            host=config.OLLAMA_HOST,
            model=config.LLM_MODEL,
            temperature=config.LLM_TEMPERATURE,
            timeout=config.LLM_TIMEOUT,
        )

    if provider in {"openai_compatible", "openai-compatible", "openrouter"}:
        return OpenAICompatibleProvider(
            base_url=config.OPENAI_COMPATIBLE_BASE_URL,
            api_key=config.OPENAI_COMPATIBLE_API_KEY,
            model=config.LLM_MODEL,
            temperature=config.LLM_TEMPERATURE,
            timeout=config.LLM_TIMEOUT,
        )

    if provider == "gemini":
        return GeminiProvider(
            api_key=config.GEMINI_API_KEY,
            model=config.LLM_MODEL,
            temperature=config.LLM_TEMPERATURE,
            timeout=config.LLM_TIMEOUT,
        )

    raise ValueError(
        f"LLM_PROVIDER inválido: {config.LLM_PROVIDER!r}. "
        "Use 'ollama', 'openai_compatible' ou 'gemini'."
    )
