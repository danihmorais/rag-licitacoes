from __future__ import annotations
from config import SETTINGS
from .openai_compatible import OpenAICompatibleLLM

def create_llm(provider: str | None = None):
    provider = (provider or "openai").lower()
    if provider in {"openai", "openai_compatible", "unsloth", "ollama"}:
        return OpenAICompatibleLLM()
    raise ValueError(f"Provider não suportado: {provider}")
