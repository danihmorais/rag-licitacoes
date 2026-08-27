import json,config
class IndexCompatibilityError(RuntimeError):pass
def current_manifest():return {'index_version':config.INDEX_VERSION,'collection_name':config.COLLECTION_NAME,'dense_model':config.DENSE_MODEL,'dense_dim':config.DENSE_DIM,'sparse_model':config.SPARSE_MODEL,'rerank_model':config.RERANK_MODEL,'chunk_size':config.CHUNK_SIZE,'chunk_overlap':config.CHUNK_OVERLAP,'max_context_chars':config.MAX_CONTEXT_CHARS,'schema':'unit_id/chunk_index/page_span/source_role/status'}
def read_manifest():return json.loads(config.INDEX_MANIFEST_PATH.read_text(encoding='utf-8')) if config.INDEX_MANIFEST_PATH.exists() else None
def write_manifest():config.INDEX_MANIFEST_PATH.write_text(json.dumps(current_manifest(),ensure_ascii=False,indent=2),encoding='utf-8')
def validate_manifest():
 s=read_manifest()
 if s is None:raise IndexCompatibilityError('O índice existe, mas não há index_manifest.json. Reindexe o banco.')
 e=current_manifest(); d={k:(s.get(k),v) for k,v in e.items() if s.get(k)!=v}
 if d:raise IndexCompatibilityError('Configuração incompatível com o índice: '+', '.join(f'{k}: índice={a!r}, configuração={b!r}' for k,(a,b) in d.items())+'. Reindexe o banco.')
