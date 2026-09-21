from __future__ import annotations
import argparse,json,re
from collections import defaultdict
from typing import Any
from qdrant_client import QdrantClient
from fastembed import TextEmbedding
from rank_bm25 import BM25Okapi
from config import SETTINGS
from llm.factory import create_llm

ALLOWED_FILTERS={"jurisdicao","esfera","tribunal","ano","source_role","municipio","vigente"}

def _tokens(text:str)->list[str]:
    return re.findall(r"[\wÀ-ÿ]+",text.lower())

def _filter(query:str)->tuple[str,dict[str,str]]:
    f={}
    def repl(m):
        k,v=m.group(1),m.group(2)
        if k in ALLOWED_FILTERS:
            f[k]=v; return " "
        return m.group(0)
    return re.sub(r"@([\w_]+)=([^\s]+)",repl,query).strip(),f

def _matches(payload:dict[str,Any],filters:dict[str,str])->bool:
    for key,wanted in filters.items():
        actual=payload.get(key)
        if key=="ano":
            try:
                if int(actual)!=int(wanted): return False
            except Exception:
                return False
        elif str(actual).lower()!=wanted.lower():
            return False
    return True

def _evidence(payload:dict[str,Any],dense:float,lexical:float)->float:
    authority=float(payload.get("authority_level",9))
    authority_bonus=max(0.0,1-authority/6)*0.12
    role_bonus=0.08 if payload.get("source_role") in {"norma","jurisprudencia","jurisprudencia_controle"} else 0.0
    return 0.62*dense+0.30*lexical+authority_bonus+role_bonus

def _dense(client:QdrantClient,vector,limit:int):
    result=client.query_points(collection_name=SETTINGS.collection,query=vector,using="dense",limit=limit,with_payload=True)
    return list(getattr(result,"points",result))

def _bm25():
    if not SETTINGS.bm25_index.exists(): return None,[]
    try:
        docs=json.loads(SETTINGS.bm25_index.read_text(encoding="utf-8")).get("documents",[])
        return (BM25Okapi([_tokens(x["text"]) for x in docs]),docs) if docs else (None,[])
    except Exception:
        return None,[]

def search(question:str)->list[dict[str,Any]]:
    text,filters=_filter(question)
    vector=list(TextEmbedding(model_name=SETTINGS.embedding_model).embed([text]))[0].tolist()
    client=QdrantClient(url=SETTINGS.qdrant_url)
    dense=[p for p in _dense(client,vector,SETTINGS.dense_k) if _matches(p.payload,filters)]
    bm25,docs=_bm25(); lexical=[]
    if bm25:
        scores=bm25.get_scores(_tokens(text))
        for i in sorted(range(len(scores)),key=lambda i:scores[i],reverse=True)[:SETTINGS.bm25_k]:
            if _matches(docs[i],filters): lexical.append(docs[i])
    lexical_ids={str(d["id"]) for d in lexical}; merged=defaultdict(float); items={}
    for rank,p in enumerate(dense,1):
        pid=str(p.id); merged[pid]+=1/(SETTINGS.rrf_k+rank); items[pid]=p
    for rank,d in enumerate(lexical,1):
        pid=str(d["id"]); merged[pid]+=1/(SETTINGS.rrf_k+rank); items.setdefault(pid,d)
    out=[]
    for pid,item in items.items():
        payload=dict(item.payload if hasattr(item,"payload") else item)
        payload["_rrf_score"]=merged[pid]
        payload["_evidence_score"]=_evidence(payload,float(getattr(item,"score",0)),1.0 if pid in lexical_ids else 0.0)
        if payload["_evidence_score"]>=SETTINGS.min_evidence_score: out.append(payload)
    out.sort(key=lambda x:(-x["_evidence_score"],x.get("authority_level",9),x.get("source","")))
    return out[:SETTINGS.final_k]

def expand_context(points:list[dict[str,Any]])->list[dict[str,Any]]:
    by=defaultdict(list)
    for p in points: by[(p.get("source",""),p.get("unit_id",""))].append(p)
    result=[]; seen=set()
    for p in points:
        for x in by[(p.get("source",""),p.get("unit_id",""))]:
            key=(x.get("source"),x.get("unit_id"),x.get("chunk_index"))
            if key not in seen: seen.add(key); result.append(x)
    return result

def context_with_sources(points:list[dict[str,Any]])->str:
    result=[]; total=0
    for i,p in enumerate(points,1):
        text=str(p.get("text","")).strip()
        if not text: continue
        page,end=p.get("page"),p.get("page_end")
        location=f"p.{page}" if page==end or end is None else f"pp.{page}-{end}"
        block=f"[F{i}] {p.get('source','?')} | {location} | {p.get('unit_ref') or p.get('unit_id') or ''}\n{text}\n"
        if total+len(block)>SETTINGS.max_context_chars: continue
        result.append(block); total+=len(block)
    return "\n".join(result)

def ask(question:str,provider:str="openai")->str:
    points=search(question)
    if not points:
        return "Não foi localizada evidência suficiente no corpus indexado para responder com segurança."
    return create_llm(provider).chat(question,context_with_sources(expand_context(points)))

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("question",nargs="+")
    p.add_argument("--no-llm",action="store_true")
    a=p.parse_args(); q=" ".join(a.question)
    print(json.dumps(search(q),ensure_ascii=False,indent=2) if a.no_llm else ask(q))
    return 0

if __name__=="__main__": raise SystemExit(main())
