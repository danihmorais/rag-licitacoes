from __future__ import annotations

from .openai_compatible import OpenAICompatibleLLM

def create_llm(provider: str | None = None):
    name = (provider or "openai").lower()
    if name in {"openai", "openai_compatible", "unsloth"}:
        return OpenAICompatibleLLM()
    if name == "ollama":
        from .ollama import OllamaLLM
        return OllamaLLM()
    if name == "gemini":
        from .gemini import GeminiLLM
        return GeminiLLM()
    raise ValueError(f"Provider não suportado: {provider}")
