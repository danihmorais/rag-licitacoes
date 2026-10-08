import math

import numpy as np
import requests

import config


class UnslothOpenAIEmbedding:
    """Cliente mínimo para o endpoint OpenAI-compatible /v1/embeddings do Unsloth Studio."""

    def __init__(self):
        self.model = config.DENSE_MODEL
        self.base_url = config.DENSE_API_BASE_URL
        self.api_key = config.DENSE_API_KEY
        self.batch_size = config.DENSE_API_BATCH_SIZE
        self.timeout = config.DENSE_API_TIMEOUT
        self._session = requests.Session()

    def embed(self, texts):
        texts = list(texts)
        if not texts:
            return np.empty((0, config.DENSE_DIM), dtype=np.float32)

        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'

        output = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            try:
                response = self._session.post(
                    f'{self.base_url}/embeddings',
                    json={
                        'input': batch,
                        'model': self.model,
                        'encoding_format': 'float',
                    },
                    headers=headers,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                raise RuntimeError(
                    f'Falha ao chamar embeddings no Unsloth Studio em {self.base_url}: {exc}'
                ) from exc

            if response.status_code >= 400:
                detail = response.text.strip().replace('\n', ' ')[:1000]
                raise RuntimeError(
                    f'Unsloth Studio /v1/embeddings respondeu HTTP {response.status_code}: {detail}'
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError(
                    'Unsloth Studio /v1/embeddings retornou uma resposta que não é JSON.'
                ) from exc

            data = payload.get('data')
            if not isinstance(data, list) or len(data) != len(batch):
                raise RuntimeError(
                    'Resposta de embeddings inválida: quantidade de vetores '
                    f'{len(data) if isinstance(data, list) else 0} != {len(batch)}.'
                )

            try:
                ordered = sorted(data, key=lambda item: int(item.get('index', 0)))
            except (AttributeError, TypeError, ValueError) as exc:
                raise RuntimeError('Resposta de embeddings contém índices inválidos.') from exc

            for item in ordered:
                vector = item.get('embedding')
                if not isinstance(vector, list) or len(vector) != config.DENSE_DIM:
                    actual = len(vector) if isinstance(vector, list) else 0
                    raise RuntimeError(
                        f'Embedding recebido com dimensão {actual}; '
                        f'configuração exige {config.DENSE_DIM}.'
                    )
                values = np.asarray(vector, dtype=np.float32)
                if not np.all(np.isfinite(values)) or not math.isfinite(float(np.linalg.norm(values))):
                    raise RuntimeError('Embedding recebido contém valores não finitos.')
                if float(np.linalg.norm(values)) == 0.0:
                    raise RuntimeError('Embedding recebido é um vetor nulo.')
                output.append(values)

        return np.vstack(output).astype(np.float32, copy=False)


class _FastEmbedDense:
    def __init__(self):
        from fastembed import TextEmbedding

        self.model = TextEmbedding(
            model_name=config.DENSE_MODEL,
            max_length=config.DENSE_MAX_TOKENS,
            providers=list(config.FASTEMBED_PROVIDERS),
        )

    def embed(self, texts):
        return np.asarray(list(self.model.embed(texts)), dtype=np.float32)


def create_dense_embedding():
    """Cria o embedding denso selecionado pelo .env.

    Sem RAG_DENSE_MODEL (ou com o próprio E5 explícito), mantém o caminho FastEmbed.
    Com outro modelo, consulta o endpoint OpenAI-compatible do Unsloth Studio.
    Falhas do Studio não fazem fallback automático para o E5: misturar espaços vetoriais
    em uma mesma execução/índice seria inseguro.
    """
    if config.DENSE_BACKEND == 'unsloth_openai':
        return UnslothOpenAIEmbedding()
    return _FastEmbedDense()
