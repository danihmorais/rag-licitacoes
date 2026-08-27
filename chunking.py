import re
from langchain_text_splitters import RecursiveCharacterTextSplitter
ARTIGO_RE=re.compile(r'(?m)^\s*(Art(?:igo)?\.?\s*\d+[ºo°]?-?[A-Z]?\.?)\s'); SUMULA_RE=re.compile(r'(?m)^\s*(S[uú]mula\s*n?[ºo°.]*\s*\d+|Enunciado\s*n?[ºo°.]*\s*\d+)\b',re.I)
def _find(text,rx,kind):
 m=list(rx.finditer(text))
 if len(m)<2:return None
 out=[]
 if m[0].start()>0 and text[:m[0].start()].strip():out.append({'kind':'generic','ref':None,'start':0,'text':text[:m[0].start()].strip()})
 for i,x in enumerate(m):
  s=x.start(); e=m[i+1].start() if i+1<len(m) else len(text); t=text[s:e].strip()
  if t:out.append({'kind':kind,'ref':x.group(1).strip(),'start':s,'text':t})
 return out
def _units(text):
 c=[]
 for rx,k in ((ARTIGO_RE,'artigo'),(SUMULA_RE,'sumula')):
  u=_find(text,rx,k)
  if u:c.append((sum(x['kind']==k for x in u),u))
 if c:
  n,u=max(c,key=lambda x:x[0])
  if n>=4:return u
 return [{'kind':'generic','ref':None,'start':0,'text':text}]
def build_structural_chunks(full_text,max_size,overlap):
 sp=RecursiveCharacterTextSplitter(chunk_size=max_size,chunk_overlap=overlap,separators=['\n\n','\n','. ',' ',''])
 out=[]
 for u in _units(full_text):
  full=u['text']; pieces=[full] if len(full)<=max_size else sp.split_text(full); pos=0; uid=f"{u['kind']}:{u.get('ref') or u['start']}"
  for i,p in enumerate(pieces):
   if not p.strip():continue
   found=full.find(p,max(0,pos-overlap)); found=pos if found<0 else found
   out.append({'text':p,'full_unit_text':p if len(full)<=max_size else None,'unit_kind':u['kind'],'unit_ref':u['ref'],'unit_id':uid,'chunk_index':i,'unit_length':len(full),'start':u['start']+found}); pos=found+max(1,len(p)-overlap)
 return out
