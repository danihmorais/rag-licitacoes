import math
import re
import sys

from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from qdrant_client import QdrantClient, models

import config
from index_manifest import IndexCompatibilityError, validate_manifest
from llm.factory import get_llm_provider

SYSTEM_PROMPT = '''Você é um assistente especializado em licitações, contratos administrativos e Direito Público brasileiro, com foco em São Paulo.

REGRAS DE AUTORIDADE E TEMPO:
- Responda somente com base no contexto recuperado.
- Priorize norma vigente e fonte oficial. Hierarquia: Constituição/lei/decreto/ato normativo > jurisprudência/controle > orientação oficial > doutrina.
- Nunca trate jurisprudência, manual, guia ou doutrina como se fosse texto legal.
- Respeite jurisdição, esfera, status e vigência. Se houver conflito temporal, prefira a norma vigente para a data perguntada; se a data não estiver clara, informe a limitação.
- Não misture regime federal com estadual paulista sem explicar a aplicação.
- Normas com status "revogado" ou "vacatio_legis" não podem ser apresentadas como regra atualmente vigente sem explicar a condição temporal.

CITAÇÕES:
- Toda afirmação jurídica relevante deve conter [F#].
- Cite fonte, página e dispositivo/unidade quando disponíveis.
- Não invente artigos, incisos, processos, súmulas, datas ou números.
- Se não houver suporte suficiente no contexto, diga expressamente que não foi encontrado suporte nos documentos indexados.

FORMATO:
- Seja objetivo, mas preserve exceções e condições jurídicas relevantes.
- Quando houver mais de uma norma aplicável, explique a relação hierárquica ou complementar entre elas.

Contexto:
{context}'''

FILTER_RE = re.compile(r'@(\w+)=([^\s@]+)')


def parse_filters(raw):
    filters = dict(FILTER_RE.findall(raw)); clean = FILTER_RE.sub('', raw).strip()
    for key in ('ano', 'norm_ano'):
        if key in filters: filters[key] = int(filters[key])
    return clean, filters


def qfilter(filters):
    if not filters: return None
    return models.Filter(must=[models.FieldCondition(key=key, match=models.MatchValue(value=value)) for key, value in filters.items()])


def embedding_kwargs():
    return {'providers': config.FASTEMBED_PROVIDERS} if config.FASTEMBED_PROVIDERS else {}


def hybrid(client, dense, sparse, query, query_filter):
    dense_vector = list(dense.embed(['query: ' + query]))[0]
    sparse_vector = list(sparse.embed([query]))[0]
    return client.query_points(collection_name=config.COLLECTION_NAME,
        prefetch=[models.Prefetch(query=dense_vector.tolist(), using='dense', limit=config.CANDIDATES_K, filter=query_filter),
                  models.Prefetch(query=models.SparseVector(indices=sparse_vector.indices.tolist(), values=sparse_vector.values.tolist()), using='sparse', limit=config.CANDIDATES_K, filter=query_filter)],
        query=models.FusionQuery(fusion=models.Fusion.RRF), limit=config.CANDIDATES_K).points


def evidence_score(raw_score):
    value = float(raw_score)
    if 0.0 <= value <= 1.0: return value
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def rerank(reranker, query, points):
    if not points: return []
    raw_scores = list(reranker.rerank(query, [p.payload['text'] for p in points]))
    scored = []
    for point, raw_score in zip(points, raw_scores):
        point.payload['_rerank_score'] = float(raw_score)
        point.payload['_evidence_score'] = evidence_score(raw_score)
        scored.append(point)
    scored.sort(key=lambda p: p.payload['_evidence_score'], reverse=True)
    output, counts = [], {}
    for point in scored:
        key = (point.payload.get('source'), point.payload.get('unit_id'))
        if counts.get(key, 0) >= 2: continue
        counts[key] = counts.get(key, 0) + 1; output.append(point)
        if len(output) >= config.FINAL_K: break
    if not output or output[0].payload.get('_evidence_score', 0.0) < config.MIN_EVIDENCE_SCORE: return []
    return sorted(output, key=lambda p: (-p.payload.get('_evidence_score', 0.0), p.payload.get('authority_level') or 9))


def context(points):
    parts, total = [], 0
    for index, point in enumerate(points, 1):
        payload = point.payload; text = payload.get('full_unit_text') or payload['text']; page = payload.get('page'); page_end = payload.get('page_end') or page
        page_label = 'p. desconhecida' if page is None else (f'p. {page}' if page == page_end else f'pp. {page}-{page_end}')
        unit_ref = f", {payload['unit_ref']}" if payload.get('unit_ref') else ''
        part = (f"[F{index}] {payload['source']}, {page_label}{unit_ref} | papel={payload.get('source_role','desconhecido')} | "
                f"autoridade={payload.get('authority_level','desconhecida')} | status={payload.get('status','desconhecido')} | "
                f"jurisdicao={payload.get('jurisdicao','desconhecida')} | vigencia={payload.get('effective_from') or payload.get('data_vigencia') or 'desconhecida'} até {payload.get('effective_to') or 'indeterminada'} | "
                f"fonte={payload.get('fonte_oficial') or 'não informada'}\n{text}")
        if total + len(part) > config.MAX_CONTEXT_CHARS: break
        parts.append(part); total += len(part)
    return '\n\n---\n\n'.join(parts)


def answer_query(client, dense, sparse, reranker, llm, raw):
    query, filters = parse_filters(raw)
    if not query: return 'Informe uma pergunta.', []
    points = rerank(reranker, query, hybrid(client, dense, sparse, query, qfilter(filters)))
    if not points: return 'Não encontrei evidência suficientemente relevante nos documentos indexados para responder com segurança.', []
    return llm.generate(system_prompt=SYSTEM_PROMPT.format(context=context(points)), user_prompt=query), points


def main():
    if not config.QDRANT_PATH.exists(): print('Índice não encontrado. Rode python ingest.py.'); sys.exit(1)
    try: validate_manifest()
    except (IndexCompatibilityError, FileNotFoundError, ValueError) as error: print('ERRO DE COMPATIBILIDADE:', error); sys.exit(1)
    dense=TextEmbedding(model_name=config.DENSE_MODEL, **embedding_kwargs()); sparse=SparseTextEmbedding(model_name=config.SPARSE_MODEL, **embedding_kwargs()); reranker=TextCrossEncoder(model_name=config.RERANK_MODEL)
    client=QdrantClient(path=str(config.QDRANT_PATH)); llm=get_llm_provider(); print(f'RAG pronto. LLM: {config.LLM_PROVIDER}/{config.LLM_MODEL}')
    while True:
        raw=input('> ').strip()
        if raw.lower() in ('sair','exit','quit'): break
        if not raw: continue
        try: answer, points=answer_query(client,dense,sparse,reranker,llm,raw)
        except Exception as error: print('Erro:', error); continue
        print('\n'+answer+'\n')
        for index, point in enumerate(points,1): print(f"[F{index}] {point.payload['source']} (p. {point.payload.get('page')}, score={point.payload.get('_evidence_score',0):.3f})")

if __name__=='__main__': main()
