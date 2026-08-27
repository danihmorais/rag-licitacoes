import re,sys
from qdrant_client import QdrantClient,models
from fastembed import TextEmbedding,SparseTextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
import config
from index_manifest import validate_manifest,IndexCompatibilityError
from llm.factory import get_llm_provider
SYSTEM_PROMPT='''Você é um assistente especializado em licitações, contratos administrativos e Direito Público brasileiro, com foco em São Paulo. Responda somente com base no contexto recuperado. Priorize norma vigente e fonte oficial. Hierarquia: Constituição/lei/decreto/ato normativo > jurisprudência/controle > orientação oficial > doutrina. Nunca trate fonte secundária como lei. Respeite jurisdição, esfera e vigência. Toda afirmação jurídica relevante deve conter [F#]. Cite fonte, página e dispositivo. Não invente artigos, processos, súmulas ou datas. Se não houver suporte suficiente, diga expressamente que não foi encontrado suporte nos documentos indexados.\n\nContexto:\n{context}'''
FILTER_RE=re.compile(r'@(\w+)=([^\s@]+)')
def parse_filters(raw):return FILTER_RE.sub('',raw).strip(),dict(FILTER_RE.findall(raw))
def qfilter(fs):
 if not fs:return None
 cs=[]
 for k,v in fs.items():
  if k in {'ano','norm_ano'}:v=int(v)
  cs.append(models.FieldCondition(key=k,match=models.MatchValue(value=v)))
 return models.Filter(must=cs)
def ek():return {'providers':config.FASTEMBED_PROVIDERS} if config.FASTEMBED_PROVIDERS else {}
def hybrid(c,d,s,q,f):
 dv=list(d.embed(['query: '+q]))[0];sv=list(s.embed([q]))[0]
 return c.query_points(collection_name=config.COLLECTION_NAME,prefetch=[models.Prefetch(query=dv.tolist(),using='dense',limit=config.CANDIDATES_K,filter=f),models.Prefetch(query=models.SparseVector(indices=sv.indices.tolist(),values=sv.values.tolist()),using='sparse',limit=config.CANDIDATES_K,filter=f)],query=models.FusionQuery(fusion=models.Fusion.RRF),limit=config.CANDIDATES_K).points
def rerank(rr,q,pts):
 if not pts:return []
 scores=list(rr.rerank(q,[p.payload['text'] for p in pts]));ranked=sorted(zip(pts,scores),key=lambda z:z[1],reverse=True);out=[];counts={}
 for p,_ in ranked:
  k=(p.payload.get('source'),p.payload.get('unit_id'));n=counts.get(k,0)
  if n>=2:continue
  counts[k]=n+1;out.append(p)
  if len(out)>=config.FINAL_K:break
 roles={'norma':1,'jurisprudencia_controle':2,'jurisprudencia':2,'orientacao_oficial':3,'doutrina':4,'desconhecido':5}
 return sorted(out,key=lambda p:roles.get(p.payload.get('source_role'),5))
def context(pts):
 parts=[];total=0
 for i,p in enumerate(pts,1):
  x=p.payload;t=x.get('full_unit_text') or x['text'];pg=x.get('page');pe=x.get('page_end') or pg;pl=f'p. {pg}' if pg==pe else f'pp. {pg}-{pe}';ref=f", {x['unit_ref']}" if x.get('unit_ref') else ''
  part=f"[F{i}] {x['source']}, {pl}{ref} | papel={x.get('source_role','desconhecido')} | autoridade={x.get('authority_level','desconhecida')} | status={x.get('status','desconhecido')} | jurisdicao={x.get('jurisdicao','desconhecida')}\n{t}"
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
  print('\n'+answer+'\n');print('Fontes recuperadas:')
  for i,p in enumerate(pts,1):print(f"[F{i}] {p.payload['source']} (p. {p.payload.get('page')})")
if __name__=='__main__':main()
