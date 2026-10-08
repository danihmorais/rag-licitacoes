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

    @staticmethod
    def _is_token_limit_error(detail):
        message = str(detail).casefold()
        return "token" in message and "limit" in message and (
            "exceed" in message or "too many" in message or "long" in message
        )

    @staticmethod
    def _split_text(text):
        """Divide texto longo em duas partes e reaplica a instrução do modelo."""
        prefix = ""
        for candidate in (config.DENSE_DOCUMENT_PREFIX, config.DENSE_QUERY_PREFIX):
            if candidate and text.startswith(candidate):
                prefix = candidate
                text = text[len(candidate):]
                break

        if len(text) < 2:
            return None

        midpoint = len(text) // 2
        boundaries = [
            text.rfind(" ", 1, midpoint + 1),
            text.find(" ", midpoint),
            text.rfind("\n", 1, midpoint + 1),
            text.find("\n", midpoint),
        ]
        candidates = [position for position in boundaries if 0 < position < len(text)]
        split_at = min(candidates, key=lambda position: abs(position - midpoint)) if candidates else midpoint

        left = text[:split_at].strip()
        right = text[split_at:].strip()
        if not left or not right:
            split_at = midpoint
            left, right = text[:split_at].strip(), text[split_at:].strip()
        if not left or not right:
            return None

        return [prefix + left, prefix + right]

    def _embed_oversized_text(self, text, detail):
        pieces = self._split_text(text)
        if not pieces:
            raise RuntimeError(
                "O Unsloth Studio rejeitou uma entrada curta demais para dividir; "
                f"limite informado pelo endpoint: {detail}"
            )

        vectors = self._embed_batch(pieces)
        weights = np.asarray([len(piece) for piece in pieces], dtype=np.float32)
        vector = np.average(vectors, axis=0, weights=weights)
        norm = float(np.linalg.norm(vector))
        if not np.all(np.isfinite(vector)) or not math.isfinite(norm) or norm == 0.0:
            raise RuntimeError("Não foi possível combinar embeddings de uma entrada dividida.")
        # Mantém uma única representação por chunk original, normalizada para distância cosseno.
        return (vector / norm).astype(np.float32, copy=False).reshape(1, -1)

    def _embed_batch(self, batch):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = self._session.post(
                f"{self.base_url}/embeddings",
                json={
                    "input": batch,
                    "model": self.model,
                    "encoding_format": "float",
                },
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Falha ao chamar embeddings no Unsloth Studio em {self.base_url}: {exc}"
            ) from exc

        if response.status_code >= 400:
            detail = response.text.strip().replace("\n", " ")[:1000]
            if self._is_token_limit_error(detail):
                if len(batch) > 1:
                    middle = len(batch) // 2
                    return np.vstack((
                        self._embed_batch(batch[:middle]),
                        self._embed_batch(batch[middle:]),
                    ))
                return self._embed_oversized_text(batch[0], detail)
            raise RuntimeError(
                f"Unsloth Studio /v1/embeddings respondeu HTTP {response.status_code}: {detail}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Unsloth Studio /v1/embeddings retornou uma resposta que não é JSON."
            ) from exc

        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(batch):
            raise RuntimeError(
                "Resposta de embeddings inválida: quantidade de vetores "
                f"{len(data) if isinstance(data, list) else 0} != {len(batch)}."
            )

        try:
            ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise RuntimeError("Resposta de embeddings contém índices inválidos.") from exc

        output = []
        for item in ordered:
            vector = item.get("embedding")
            if not isinstance(vector, list) or len(vector) != config.DENSE_DIM:
                actual = len(vector) if isinstance(vector, list) else 0
                raise RuntimeError(
                    f"Embedding recebido com dimensão {actual}; "
                    f"configuração exige {config.DENSE_DIM}."
                )
            values = np.asarray(vector, dtype=np.float32)
            norm = float(np.linalg.norm(values))
            if not np.all(np.isfinite(values)) or not math.isfinite(norm):
                raise RuntimeError("Embedding recebido contém valores não finitos.")
            if norm == 0.0:
                raise RuntimeError("Embedding recebido é um vetor nulo.")
            output.append(values)

        return np.vstack(output).astype(np.float32, copy=False)

    def embed(self, texts):
        texts = list(texts)
        if not texts:
            return np.empty((0, config.DENSE_DIM), dtype=np.float32)

        output = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            output.append(self._embed_batch(batch))
        return np.vstack(output).astype(np.float32, copy=False)


class _FastEmbedDense:
    def __init__(self):
        from fastembed import TextEmbedding

        self.model = TextEmbedding(
            model_name=config.DENSE_MODEL,
            max_length=config.DENSE_MAX_TOKENS,
            providers=list(config.FASTEMBED_PROVIDERS),
        )

    @property
    def tokenizer(self):
        return getattr(getattr(self.model, "model", None), "tokenizer", None)

    def embed(self, texts):
        return np.asarray(list(self.model.embed(texts)), dtype=np.float32)


def create_dense_embedding():
    """Cria o embedding denso selecionado pelo .env.

    Sem RAG_DENSE_MODEL (ou com o próprio E5 explícito), mantém o caminho FastEmbed.
    Com outro modelo, consulta o endpoint OpenAI-compatible do Unsloth Studio.
    Falhas do Studio não fazem fallback automático para o E5: misturar espaços vetoriais
    em uma mesma execução/índice seria inseguro. Entradas rejeitadas somente por tamanho
    são divididas e combinadas, para não abortar a ingestão por um limite do servidor.
    """
    if config.DENSE_BACKEND == "unsloth_openai":
        return UnslothOpenAIEmbedding()
    return _FastEmbedDense()
