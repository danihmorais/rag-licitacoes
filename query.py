import re,sys
from qdrant_client import QdrantClient,models
from fastembed import TextEmbedding,SparseTextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
import config
from index_manifest import validate_manifest,IndexCompatibilityError
from llm.factory import get_llm_provider
from llm.base import LLMError
SYSTEM_PROMPT='''Você é um assistente especializado em licitações e contratos administrativos brasileiros, com foco em São Paulo. Responda exclusivamente com base no contexto recuperado. Diferencie norma federal, norma estadual, jurisprudência, orientação oficial e doutrina. Respeite status/vigência. Nunca trate jurisprudência, guia ou doutrina como lei. Toda afirmação jurídica relevante deve indicar [F#] existente no contexto. Cite fonte e página. Se o contexto não sustentar a resposta, diga que não foi encontrado nos documentos indexados.\n\nContexto:\n{context}'''
FILTER_RE=re.compile(r'@(\w+)=([^\s@]+)')
def parse_filters(raw):return FILTER_RE.sub('',raw).strip(),dict(FILTER_RE.findall(raw))
def qfilter(fs):
 if not fs:return None
 cs=[]
 for k,v in fs.items():
  if k=='ano':v=int(v)
  cs.append(models.FieldCondition(key=k,match=models.MatchValue(value=v)))
 return models.Filter(must=cs)
def ek():return {'providers':config.FASTEMBED_PROVIDERS} if config.FASTEMBED_PROVIDERS else {}
def hybrid(c,d,s,q,f):
 dv=list(d.embed(['query: '+q]))[0];sv=list(s.embed([q]))[0]
 r=c.query_points(collection_name=config.COLLECTION_NAME,prefetch=[models.Prefetch(query=dv.tolist(),using='dense',limit=config.CANDIDATES_K,filter=f),models.Prefetch(query=models.SparseVector(indices=sv.indices.tolist(),values=sv.values.tolist()),using='sparse',limit=config.CANDIDATES_K,filter=f)],query=models.FusionQuery(fusion=models.Fusion.RRF),limit=config.CANDIDATES_K)
 return r.points
def rerank(rr,q,pts):
 if not pts:return []
 scores=list(rr.rerank(q,[p.payload['text'] for p in pts]));ranked=sorted(zip(pts,scores),key=lambda z:z[1],reverse=True);out=[];counts={}
 for p,_ in ranked:
  k=(p.payload.get('source'),p.payload.get('unit_id'));n=counts.get(k,0)
  if n>=2:continue
  counts[k]=n+1;out.append(p)
  if len(out)>=config.FINAL_K:break
 return out
def context(pts):
 parts=[];total=0
 for i,p in enumerate(pts,1):
  x=p.payload;t=x.get('full_unit_text') or x['text'];pg=x.get('page');pe=x.get('page_end') or pg;pl=f'p. {pg}' if pg==pe else f'pp. {pg}-{pe}';ref=f", {x['unit_ref']}" if x.get('unit_ref') else '';part=f"[F{i}] {x['source']}, {pl}{ref} | papel={x.get('source_role','desconhecido')} | status={x.get('status','desconhecido')}\n{t}"
  if total+len(part)>config.MAX_CONTEXT_CHARS:break
  parts.append(part);total+=len(part)
 return '\n\n---\n\n'.join(parts)
def main():
 if not config.QDRANT_PATH.exists():print('Índice não encontrado. Rode python ingest.py.');sys.exit(1)
 try:validate_manifest()
 except (IndexCompatibilityError,FileNotFoundError,ValueError) as e:print('ERRO DE COMPATIBILIDADE:',e);sys.exit(1)
 d=TextEmbedding(model_name=config.DENSE_MODEL,**ek());s=SparseTextEmbedding(model_name=config.SPARSE_MODEL,**ek());rr=TextCrossEncoder(model_name=config.RERANK_MODEL);c=QdrantClient(path=str(config.QDRANT_PATH));llm=get_llm_provider();print(f'RAG pronto. LLM: {config.LLM_PROVIDER}/{config.LLM_MODEL}')
 while True:
  raw=input('> ').strip()
  if raw.lower() in ('sair','exit','quit'):break
  if not raw:continue
  try:q,fs=parse_filters(raw);pts=rerank(rr,q,hybrid(c,d,s,q,qfilter(fs)));answer=llm.generate(system_prompt=SYSTEM_PROMPT.format(context=context(pts)),user_prompt=q)
  except Exception as e:print('Erro:',e);continue
  print('\n'+answer+'\n');print('Fontes recuperadas:');
  for i,p in enumerate(pts,1):print(f"[F{i}] {p.payload['source']} (p. {p.payload.get('page')})")
if __name__=='__main__':main()
