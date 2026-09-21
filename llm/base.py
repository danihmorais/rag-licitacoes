from abc import ABC, abstractmethod

import requests


class LLMError(RuntimeError):
    """Erro base normalizado dos provedores de LLM."""


class LLMTimeoutError(LLMError):
    """Timeout de rede ou do provedor."""


class LLMQuotaError(LLMError):
    """Limite de cota, rate limit ou capacidade temporariamente excedida."""


class LLMNetworkError(LLMError):
    """Falha de conectividade com o provedor."""


class LLMProviderError(LLMError):
    """Falha funcional ou resposta inválida do provedor."""


def map_provider_exception(exc, provider, response=None):
    status = getattr(response, 'status_code', None)
    if isinstance(exc, requests.Timeout):
        return LLMTimeoutError(f'{provider}: timeout ao consultar o provedor.') 
    if status == 429:
        return LLMQuotaError(f'{provider}: limite de requisições/cota excedido.')
    if status == 408:
        return LLMTimeoutError(f'{provider}: requisição expirou (HTTP 408).')
    if isinstance(exc, requests.ConnectionError):
        return LLMNetworkError(f'{provider}: falha de conexão: {exc}')
    if isinstance(exc, requests.RequestException):
        return LLMNetworkError(f'{provider}: falha HTTP: {exc}')
    return LLMProviderError(f'{provider}: {exc}')


def raise_provider_error(exc, provider, response=None):
    mapped = map_provider_exception(exc, provider, response)
    raise mapped from exc


class LLMProvider(ABC):
    """Interface estável entre o RAG e qualquer modelo de geração."""

    def __init__(self, model: str, temperature: float, timeout: int):
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError
