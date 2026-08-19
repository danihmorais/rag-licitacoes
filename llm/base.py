from abc import ABC, abstractmethod


class LLMError(RuntimeError):
    """Raised when an LLM provider cannot generate a response."""


class LLMProvider(ABC):
    """Stable interface between the RAG pipeline and any text-generation model."""

    def __init__(self, model: str, temperature: float, timeout: int):
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError
