import sys,uuid
from pypdf import PdfReader
from qdrant_client import QdrantClient,models
from fastembed import TextEmbedding,SparseTextEmbedding
import config
from chunking import build_structural_chunks
from index_manifest import read_manifest,write_manifest
from metadata import extract_metadata
PAGE_BREAK='\f'
def load_pdfs():
 p=sorted(config.PDFS_DIR.glob('*.pdf'))
 if not p:print(f'Nenhum PDF encontrado em {config.PDFS_DIR}.');sys.exit(1)
 return p
def extract_pages(p):return [x.extract_text() or '' for x in PdfReader(str(p)).pages]
def _starts(pages):
 out=[];o=0
 for t in pages:out.append(o);o+=len(t)+1
 return out
def _page(off,starts):
 n=1
 for i,s in enumerate(starts,1):
  if s<=off:n=i
  else:break
 return n
def build_chunks(pdf,pages):
 full=PAGE_BREAK.join(pages); meta=extract_metadata(full,pdf); starts=_starts(pages); out=[]
 for x in build_structural_chunks(full,config.CHUNK_SIZE,config.CHUNK_OVERLAP):
  if not x['text'].strip():continue
  s=x['start'];e=s+len(x['text']);out.append({'text':x['text'],'full_unit_text':x['full_unit_text'],'unit_kind':x['unit_kind'],'unit_ref':x['unit_ref'],'unit_id':x['unit_id'],'chunk_index':x['chunk_index'],'unit_length':x['unit_length'],'source':pdf.name,'page':_page(s,starts),'page_end':_page(max(s,e-1),starts),**meta})
 return out
def _ek():return {'providers':config.FASTEMBED_PROVIDERS} if config.FASTEMBED_PROVIDERS else {}
def ensure_collection(c):
 if not c.collection_exists(config.COLLECTION_NAME):c.create_collection(collection_name=config.COLLECTION_NAME,vectors_config={'dense':models.VectorParams(size=config.DENSE_DIM,distance=models.Distance.COSINE)},sparse_vectors_config={'sparse':models.SparseVectorParams()})
def delete_doc(c,name):c.delete(collection_name=config.COLLECTION_NAME,points_selector=models.FilterSelector(filter=models.Filter(must=[models.FieldCondition(key='source',match=models.MatchValue(value=name))])))
def main():
 config.ensure_directories(); files=load_pdfs(); c=QdrantClient(path=str(config.QDRANT_PATH)); manifest=read_manifest()
 if manifest is not None:
  from index_manifest import validate_manifest
  validate_manifest()
 elif c.collection_exists(config.COLLECTION_NAME) and c.count(config.COLLECTION_NAME).count:raise RuntimeError('Índice sem manifest. Remova db/qdrant e reindexe.')
 dense=TextEmbedding(model_name=config.DENSE_MODEL,**_ek()); sparse=SparseTextEmbedding(model_name=config.SPARSE_MODEL,**_ek()); ensure_collection(c)
 for f in files:
  pages=extract_pages(f); chunks=build_chunks(f,pages)
  if not chunks:print('Aviso: sem texto em',f.name);continue
  dv=list(dense.embed(['passage: '+x['text'] for x in chunks])); sv=list(sparse.embed([x['text'] for x in chunks])); delete_doc(c,f.name); pts=[]
  for i,x in enumerate(chunks):pts.append(models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL,f"{f.name}|{x['unit_id']}|{x['chunk_index']}|{x['text']}")),vector={'dense':dv[i].tolist(),'sparse':models.SparseVector(indices=sv[i].indices.tolist(),values=sv[i].values.tolist())},payload=x))
  c.upsert(collection_name=config.COLLECTION_NAME,points=pts);print(f'Indexado: {f.name} ({len(pts)} chunks)')
 write_manifest();print('Total:',c.count(config.COLLECTION_NAME).count)
if __name__=='__main__':main()
