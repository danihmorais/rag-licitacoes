import config

from .base import LLMProvider
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider


def get_llm_provider(purpose: str = 'answer') -> LLMProvider:
    if purpose == 'semantic_chunking':
        provider = config.AI_CHUNKING_PROVIDER.strip().lower()
        model = config.AI_CHUNKING_MODEL
        temperature = config.AI_CHUNKING_TEMPERATURE
        timeout = config.AI_CHUNKING_TIMEOUT
        max_tokens = config.AI_CHUNKING_MAX_TOKENS
    elif purpose == 'answer':
        provider = config.LLM_PROVIDER.strip().lower()
        model = config.LLM_MODEL
        temperature = config.LLM_TEMPERATURE
        timeout = config.LLM_TIMEOUT
        max_tokens = config.LLM_MAX_TOKENS
    else:
        raise ValueError(f'Finalidade de LLM inválida: {purpose!r}.')

    if provider == 'ollama':
        return OllamaProvider(
            host=config.OLLAMA_HOST,
            model=model,
            temperature=temperature,
            timeout=timeout,
            num_ctx=config.OLLAMA_NUM_CTX,
        )

    if provider in {'openai_compatible', 'openai-compatible', 'openrouter'}:
        return OpenAICompatibleProvider(
            base_url=config.OPENAI_COMPATIBLE_BASE_URL,
            api_key=config.OPENAI_COMPATIBLE_API_KEY,
            model=model,
            temperature=temperature,
            timeout=timeout,
            max_tokens=max_tokens,
        )

    if provider == 'gemini':
        return GeminiProvider(
            api_key=config.GEMINI_API_KEY,
            model=model,
            temperature=temperature,
            timeout=timeout,
        )

    raise ValueError(
        f"LLM provider inválido: {provider!r}. "
        "Use 'ollama', 'openai_compatible' ou 'gemini'."
    )
