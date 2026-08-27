import re
import sys
from qdrant_client import QdrantClient, models
from fastembed import TextEmbedding, SparseTextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
import config
from index_manifest import IndexCompatibilityError, validate_manifest
from llm.base import LLMError
from llm.factory import get_llm_provider

SYSTEM_PROMPT = """Você é um assistente especializado em licitações e contratos administrativos brasileiros.
Responda exclusivamente com base no contexto recuperado abaixo. Não invente fatos, artigos,
decisões, números ou conclusões jurídicas que não estejam sustentados pelo contexto.

Regras:
1. Diferencie claramente norma federal, norma estadual de São Paulo e jurisprudência.
2. Dê preferência à norma mais diretamente aplicável ao caso perguntado.
3. Quando houver conflito entre fontes, não escolha silenciosamente: explique a existência do conflito.
4. Cite sempre a fonte e a página; quando houver artigo/súmula/enunciado, cite também a referência.
5. Se o contexto não sustentar a resposta, diga explicitamente que a informação não foi encontrada
   nos documentos indexados.

Contexto:
{context}
"""
FILTER_RE = re.compile(r"@(\w+)=([^\s@]+)")


def parse_filters(raw_question):
    filters = dict(FILTER_RE.findall(raw_question))
    return FILTER_RE.sub("", raw_question).strip(), filters


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
    return TextEmbedding(model_name=config.DENSE_MODEL), SparseTextEmbedding(model_name=config.SPARSE_MODEL), TextCrossEncoder(model_name=config.RERANK_MODEL)


def hybrid_search(client, dense_model, sparse_model, question, qfilter):
    dense_vec = list(dense_model.embed(["query: " + question]))[0]
    sparse_vec = list(sparse_model.embed([question]))[0]
    results = client.query_points(
        collection_name=config.COLLECTION_NAME,
        prefetch=[
            models.Prefetch(query=dense_vec.tolist(), using="dense", limit=config.CANDIDATES_K, filter=qfilter),
            models.Prefetch(query=models.SparseVector(indices=sparse_vec.indices.tolist(), values=sparse_vec.values.tolist()), using="sparse", limit=config.CANDIDATES_K, filter=qfilter),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF), limit=config.CANDIDATES_K,
    )
    return results.points


def _unit_key(point):
    payload = point.payload
    if payload.get("unit_ref"):
        return (payload.get("source"), payload.get("unit_kind"), payload.get("unit_ref"))
    return (payload.get("source"), payload.get("unit_kind"), payload.get("page"), payload.get("text"))


def rerank(reranker, question, points):
    if not points:
        return []
    scores = list(reranker.rerank(question, [p.payload["text"] for p in points]))
    ranked = sorted(zip(points, scores), key=lambda item: item[1], reverse=True)
    selected, seen = [], set()
    for point, _score in ranked:
        key = _unit_key(point)
        if key in seen:
            continue
        seen.add(key)
        selected.append(point)
        if len(selected) >= config.FINAL_K:
            break
    return selected


def format_context(points):
    parts, seen_units = [], set()
    total_chars = 0
    for point in points:
        payload = point.payload
        full_text = payload.get("full_unit_text") or payload["text"]
        unit_ref = payload.get("unit_ref")
        dedup_key = (payload.get("source"), payload.get("unit_kind"), unit_ref, full_text)
        if dedup_key in seen_units:
            continue
        page = payload.get("page")
        page_end = payload.get("page_end") or page
        page_label = f"p. {page}" if page == page_end else f"pp. {page}-{page_end}"
        ref_label = f", {unit_ref}" if unit_ref else ""
        part = f"[{payload['source']}, {page_label}{ref_label}]\n{full_text}"
        if total_chars + len(part) > config.MAX_CONTEXT_CHARS:
            break
        seen_units.add(dedup_key)
        parts.append(part)
        total_chars += len(part)
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
    print(f"\nRAG de licitações pronto.\nLLM ativo: {config.LLM_PROVIDER} / {config.LLM_MODEL}")
    print("Filtros: @campo=valor. Digite 'sair' para encerrar.\n")
    while True:
        raw = input("> ").strip()
        if raw.lower() in ("sair", "exit", "quit"):
            break
        if not raw:
            continue
        try:
            question, filters = parse_filters(raw)
            if not question:
                raise ValueError("Digite a pergunta depois dos filtros.")
            candidates = hybrid_search(client, dense_model, sparse_model, question, build_qdrant_filter(filters))
        except Exception as exc:
            print(f"\nErro na busca: {exc}\n")
            continue
        if not candidates:
            print("\nNenhum trecho encontrado.\n")
            continue
        top_chunks = rerank(reranker, question, candidates)
        try:
            answer = llm.generate(system_prompt=SYSTEM_PROMPT.format(context=format_context(top_chunks)), user_prompt=question)
        except LLMError as exc:
            print(f"\nErro no LLM: {exc}\n")
            continue
        print(f"\n{answer}\n")
        for point in top_chunks:
            payload = point.payload
            page = payload.get("page")
            page_end = payload.get("page_end") or page
            page_label = f"p. {page}" if page == page_end else f"pp. {page}-{page_end}"
            ref_label = f" — {payload['unit_ref']}" if payload.get("unit_ref") else ""
            print(f"Fonte: {payload['source']} ({page_label}{ref_label})")
        print()


if __name__ == "__main__":
    main()
