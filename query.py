import re
import sys

from qdrant_client import QdrantClient, models
from fastembed import TextEmbedding, SparseTextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

import config
from index_manifest import IndexCompatibilityError, validate_manifest
from llm.base import LLMError
from llm.factory import get_llm_provider

SYSTEM_PROMPT = """Você é um assistente que responde perguntas sobre editais e documentos de licitação
com base APENAS no contexto abaixo. Não invente informações. Se a resposta não estiver sustentada
pelo contexto, diga explicitamente que não encontrou essa informação nos documentos indexados.
Ao responder, cite o arquivo e a página quando possível.

Contexto:
{context}
"""

FILTER_RE = re.compile(r"@(\w+)=([^\s@]+)")


def parse_filters(raw_question):
    filters = dict(FILTER_RE.findall(raw_question))
    question = FILTER_RE.sub("", raw_question).strip()
    return question, filters


def build_qdrant_filter(filters):
    if not filters:
        return None
    conditions = []
    for key, value in filters.items():
        if key == "ano":
            try:
                value = int(value)
            except ValueError as exc:
                raise ValueError("O filtro @ano precisa ser numérico.") from exc
        conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    return models.Filter(must=conditions)


def load_models():
    dense_model = TextEmbedding(model_name=config.DENSE_MODEL)
    sparse_model = SparseTextEmbedding(model_name=config.SPARSE_MODEL)
    reranker = TextCrossEncoder(model_name=config.RERANK_MODEL)
    return dense_model, sparse_model, reranker


def hybrid_search(client, dense_model, sparse_model, question, qfilter):
    dense_vec = list(dense_model.embed(["query: " + question]))[0]
    sparse_vec = list(sparse_model.embed([question]))[0]

    results = client.query_points(
        collection_name=config.COLLECTION_NAME,
        prefetch=[
            models.Prefetch(
                query=dense_vec.tolist(),
                using="dense",
                limit=config.CANDIDATES_K,
                filter=qfilter,
            ),
            models.Prefetch(
                query=models.SparseVector(
                    indices=sparse_vec.indices.tolist(),
                    values=sparse_vec.values.tolist(),
                ),
                using="sparse",
                limit=config.CANDIDATES_K,
                filter=qfilter,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=config.CANDIDATES_K,
    )
    return results.points


def rerank(reranker, question, points):
    if not points:
        return []
    documents = [p.payload["text"] for p in points]
    scores = list(reranker.rerank(question, documents))
    ranked = sorted(zip(points, scores), key=lambda x: x[1], reverse=True)
    return [p for p, _ in ranked[:config.FINAL_K]]


def format_context(points):
    parts = []
    for p in points:
        payload = p.payload
        parts.append(f"[{payload['source']}, página {payload['page']}]\n{payload['text']}")
    return "\n\n---\n\n".join(parts)


def main():
    if not config.QDRANT_PATH.exists():
        print("Índice não encontrado. Rode 'python ingest.py' primeiro.")
        sys.exit(1)

    try:
        validate_manifest()
    except (IndexCompatibilityError, FileNotFoundError, ValueError) as exc:
        print(f"ERRO DE COMPATIBILIDADE DO ÍNDICE: {exc}")
        sys.exit(1)

    print("Carregando modelos de recuperação (embeddings + reranker)...")
    dense_model, sparse_model, reranker = load_models()
    client = QdrantClient(path=str(config.QDRANT_PATH))
    llm = get_llm_provider()

    print("\nRAG de licitações pronto.")
    print(f"LLM ativo: {config.LLM_PROVIDER} / {config.LLM_MODEL}")
    print("Dica: filtre por metadado com @campo=valor, ex: @municipio=Urânia @ano=2026 qual o prazo?")
    print("Digite 'sair' para encerrar.\n")

    while True:
        raw = input("> ").strip()
        if raw.lower() in ("sair", "exit", "quit"):
            break
        if not raw:
            continue

        try:
            question, filters = parse_filters(raw)
            qfilter = build_qdrant_filter(filters)
            candidates = hybrid_search(client, dense_model, sparse_model, question, qfilter)
        except Exception as exc:
            print(f"\nErro na busca: {exc}\n")
            continue

        if not candidates:
            print("\nNenhum trecho encontrado (confira os filtros ou se os PDFs foram indexados).\n")
            continue

        top_chunks = rerank(reranker, question, candidates)
        context = format_context(top_chunks)
        system_prompt = SYSTEM_PROMPT.format(context=context)

        print("\nConsultando o modelo...")
        try:
            answer = llm.generate(system_prompt=system_prompt, user_prompt=question)
        except LLMError as exc:
            print(f"\nErro no LLM: {exc}\n")
            continue

        print(f"\n{answer}\n")
        sources = sorted({p.payload["source"] for p in top_chunks})
        print(f"Fontes: {', '.join(sources)}\n")


if __name__ == "__main__":
    main()
