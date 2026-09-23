import re
from functools import lru_cache
from typing import Any, Callable

import config
from langchain_text_splitters import RecursiveCharacterTextSplitter

ARTIGO_RE = re.compile(r"^[ \t]*(Art(?:igo)?\.?[ \t]+\d+[ºo°]?(?:-[A-Z])?\.?)" r"(?=\s|$)", re.IGNORECASE | re.MULTILINE)
ARTIGO_INLINE_RE = re.compile(r"(?<![\w])[ \t]*(Art(?:igo)?\.?[ \t]+\d+[ºo°]?(?:-[A-Z])?\.?)" r"(?=\s|$)", re.IGNORECASE)
OCR_STRUCTURE_REPLACEMENTS = ((re.compile(r"\bArtig0\b", re.I), "Artigo"),(re.compile(r"\bArt1go\b", re.I), "Artigo"),(re.compile(r"\bArt1g0\b", re.I), "Artigo"),(re.compile(r"\bParagraf0\b", re.I), "Paragrafo"),(re.compile(r"\bunic0\b", re.I), "unico"),(re.compile(r"\bCAP[IÍ]TUL0\b", re.I), "CAPITULO"),(re.compile(r"\bT[IÍ]TUL0\b", re.I), "TITULO"))

def _ocr_structure_view(text):
    for pattern, replacement in OCR_STRUCTURE_REPLACEMENTS: text = pattern.sub(replacement, text)
    return text

ARTICLE_CITATION_TAIL_RE = re.compile(r"^[ \t]+(?:da|do|das|dos|de)[ \t]+(?:CF|C\.F\.?|Constitui(?:ção|cao)|Lei|C[oó]digo|CPC|CC|CLT|STF|STJ|TCU|TCESP|TJSP)\b", re.I)
SUMULA_RE = re.compile(r"^[ \t]*(S[uú]mula(?:\s+Vinculante)?\s+n?[ºo°.]*\s*\d+|Enunciado\s+n?[ºo°.]*\s*\d+)\b", re.I | re.M)
JURISPRUDENCIA_RE = re.compile(r"^[ \t]*TRIBUNAL:\s*.+$", re.I | re.M)
TEMA_RE = re.compile(r"^[ \t]*(Tema\s+n?[ºo°.]*\s*\d+)\b", re.I | re.M)
HEADER_RE = re.compile(r"^\s*((?:LEI|DECRETO-LEI|DECRETO|PORTARIA|RESOLUÇÃO|RESOLUCAO|INSTRUÇÃO|INSTRUCAO|EMENDA CONSTITUCIONAL|LIVRO|PARTE|TÍTULO|TITULO|CAPÍTULO|CAPITULO|SEÇÃO|SECAO|SUBSEÇÃO|SUBSECAO|ANEXO)\b.*)$", re.I)
PARAGRAFO_RE = r"§\s*\d+[ºo]?(?:-[A-Z])?|§\s*[uú]nico"
ROMAN_RE = r"(?:XXXIX|XXXVIII|XXXVII|XXXVI|XXXV|XXXIV|XXXIII|XXXII|XXXI|XXX|XXIX|XXVIII|XXVII|XXVI|XXV|XXIV|XXIII|XXII|XXI|XX|XIX|XVIII|XVII|XVI|XV|XIV|XIII|XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)"
CHILD_RE = re.compile(rf"(?m)^[ \t]*({PARAGRAFO_RE}|par[aá]graf[o0]\s+[uú]nic[o0](?:\s*[.:])?|{ROMAN_RE}\s*[.)–—-]|[a-z]\s*[.)–—-]|\d+\s*[.)–—-])[ \t]*", re.I)
CHILD_INLINE_RE = re.compile(rf"(?<=[\f.;:])[ \t]+({PARAGRAFO_RE}|par[aá]graf[o0]\s+[uú]nic[o0](?:\s*[.:])?|{ROMAN_RE}\s*[.)–—-]|[a-z]\s*[.)–—-]|\d+\s*[.)–—-])[ \t]*", re.I)

def _find(text, rx, kind):
    matches=list(rx.finditer(text))
    if not matches:return None
    out=[]
    if matches[0].start()>0 and text[:matches[0].start()].strip():out.append({"kind":"generic","ref":None,"start":0,"text":text[:matches[0].start()].strip()})
    for i,m in enumerate(matches):
        start=m.start(); end=matches[i+1].start() if i+1<len(matches) else len(text); value=text[start:end].strip()
        if value:out.append({"kind":kind,"ref":m.group(1).strip(),"start":start,"text":value})
    return out

def _headers_before(text,start):
    levels={}
    level_patterns=(("norma",re.compile(r"^\s*(?:LEI|DECRETO(?:-LEI)?|PORTARIA|RESOLUÇÃO|RESOLUCAO|INSTRUÇÃO|INSTRUCAO|EMENDA CONSTITUCIONAL|CONSTITUIÇÃO|CONSTITUICAO)\b.*$",re.I)),("parte",re.compile(r"^\s*PARTE\b.*$",re.I)),("livro",re.compile(r"^\s*LIVRO\b.*$",re.I)),("titulo",re.compile(r"^\s*T[IÍ]TULO\b.*$",re.I)),("capitulo",re.compile(r"^\s*CAP[IÍ]TULO\b.*$",re.I)),("secao",re.compile(r"^\s*SE[CÇ][AÃ]O\b.*$",re.I)),("subsecao",re.compile(r"^\s*SUBSE[CÇ][AÃ]O\b.*$",re.I)),("anexo",re.compile(r"^\s*ANEXO\b.*$",re.I)))
    for line in _ocr_structure_view(text[:start]).splitlines():
        normalized=re.sub(r"\s+"," ",line).strip()
        for key,pattern in level_patterns:
            if pattern.match(normalized):levels[key]=normalized;break
    return [levels[key] for key,_ in level_patterns if key in levels]

def _merged_marker_matches(text,*regexes):
    matches=[];occupied=[]
    for regex in regexes:
        for candidate in regex.finditer(text):
            if any(candidate.start()<end and candidate.end()>start for start,end in occupied):continue
            matches.append(candidate);occupied.append((candidate.start(),candidate.end()))
    dedup=[]
    for candidate in sorted(matches,key=lambda m:m.start()):
        ref=candidate.group(1).strip().casefold()
        if any(ref==p.group(1).strip().casefold() and abs(candidate.start()-p.start())<=2 for p in dedup[-2:]):continue
        dedup.append(candidate)
    return dedup

def _article_marker_is_real_header(text,match):return not ARTICLE_CITATION_TAIL_RE.match(text[match.end():match.end()+180])
def _is_article_number_inline_child(text,match):
    ref=match.group(1).strip()
    if not re.fullmatch(r"\d+\s*[.)–—-]",ref,re.I):return False
    return bool(re.search(r"Art(?:igo)?\.?\s*$",_ocr_structure_view(text[max(0,match.start()-16):match.start()]),re.I))
def _classify_child(ref):
    if ref.startswith("§") or re.match(r"^par[aá]graf[o0]\s+[uú]nic[o0]",ref,re.I):return "paragrafo"
    if re.fullmatch(rf"{ROMAN_RE}\s*[.)–—-]",ref,re.I):return "inciso"
    if re.fullmatch(r"[a-z]\s*[.)–—-]",ref,re.I):return "alinea"
    return "item"

def _article_children(article_text):
    matches=[m for m in _merged_marker_matches(_ocr_structure_view(article_text),CHILD_RE,CHILD_INLINE_RE) if not _is_article_number_inline_child(article_text,m)]
    if not matches:return article_text.strip(),[]
    caput=article_text[:matches[0].start()].strip();children=[];current_level1=None;current_level2=None
    for i,m in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(article_text);value=article_text[m.start():end].strip();ref=m.group(1).strip()
        if not value:continue
        kind=_classify_child(ref)
        if kind in {"paragrafo","inciso"}:current_level1,current_level2=ref,None;path_tail=[ref]
        elif kind=="alinea":
            if current_level1 is None:continue
            current_level2=ref;path_tail=[current_level1,ref]
        else:path_tail=[x for x in (current_level1,current_level2,ref) if x]
        children.append((kind,ref,value,m.start(),path_tail))
    return caput,children

ABBREVIATION_DOT_RE=re.compile(r"\b(?:art|inc|inciso|par|p|n|no|fls|proc|cf|etc|sr|sra|dr|dra|prof|p[aá]g|pag|vol|ed)\.",re.I)
ABBREVIATION_DOT_SENTINEL="\ue000"
def _protect_abbreviation_dots(text):return ABBREVIATION_DOT_RE.sub(lambda m:m.group(0)[:-1]+ABBREVIATION_DOT_SENTINEL,text)
def _restore_abbreviation_dots(text):return text.replace(ABBREVIATION_DOT_SENTINEL,".")

@lru_cache(maxsize=1)
def _default_tokenizer():
    try:
        from fastembed import TextEmbedding
        model=TextEmbedding(model_name=config.DENSE_MODEL,max_length=config.DENSE_MAX_TOKENS,providers=list(config.FASTEMBED_PROVIDERS))
        tokenizer=getattr(getattr(model,"model",None),"tokenizer",None)
        if tokenizer is not None and hasattr(tokenizer,"no_truncation"):
            tokenizer.no_truncation()
        return tokenizer
    except Exception as exc:
        print(f"Aviso: tokenizer do embedding indisponível no chunking; fallback por caracteres: {exc}");return None

def _token_length_factory(tokenizer:Any|None)->Callable[[str],int]:
    if tokenizer is None:return len
    if hasattr(tokenizer,"no_truncation"):
        tokenizer.no_truncation()
    def length(text):
        try:
            encoded=tokenizer.encode(text);return len(getattr(encoded,"ids",encoded))
        except Exception:
            try:
                encoded=tokenizer.encode_batch([text])[0];return len(getattr(encoded,"ids",encoded))
            except Exception:return len(text)
    return length

def _split_text_spans(text,max_size,overlap,tokenizer=None):
    if max_size<=0:raise ValueError("max_size deve ser maior que zero")
    length_fn=_token_length_factory(tokenizer)
    if length_fn(text)<=max_size:return [(text,0,len(text))]
    effective_overlap=min(overlap,max(0,max_size-1));protected=_protect_abbreviation_dots(text)
    splitter=RecursiveCharacterTextSplitter(chunk_size=max_size,chunk_overlap=effective_overlap,length_function=length_fn,separators=["\n\n","\n",". ","; ",": "," ",""],add_start_index=True)
    spans=[]
    for doc in splitter.create_documents([protected]):
        piece=_restore_abbreviation_dots(doc.page_content);start=int(doc.metadata.get("start_index",0));spans.append((piece,start,start+len(piece)))
    return spans

def _token_count(text,tokenizer=None):return _token_length_factory(tokenizer)(text)
def _truncate_words_to_tokens(text,budget,tokenizer=None):
    if budget<=0:return ""
    if _token_count(text,tokenizer)<=budget:return text
    words=list(re.finditer(r"\S+",text));lo,hi,best=0,len(words),""
    while lo<=hi:
        mid=(lo+hi)//2;candidate=text[:words[mid-1].end()].rstrip() if mid else ""
        if _token_count(candidate,tokenizer)<=budget:best=candidate;lo=mid+1
        else:hi=mid-1
    return best

def _excerpt_caput(caput,budget,tokenizer=None):
    label="CAPUT (trechos inicial e final): "
    if _token_count(caput,tokenizer)<=budget:return caput
    available=max(0,budget-_token_count(label,tokenizer))
    if available<=0:return _truncate_words_to_tokens(label,budget,tokenizer)
    ellipsis=" […] ";payload=max(1,available-_token_count(ellipsis,tokenizer));left_budget=max(1,int(payload*.30));right_budget=max(1,payload-left_budget);left=_truncate_words_to_tokens(caput,left_budget,tokenizer);words=list(re.finditer(r"\S+",caput));lo,hi,best=0,len(words),""
    while lo<=hi:
        mid=(lo+hi)//2;candidate=caput[words[len(words)-mid].start():].lstrip() if mid else ""
        if _token_count(candidate,tokenizer)<=right_budget:best=candidate;lo=mid+1
        else:hi=mid-1
    return _truncate_words_to_tokens((label+left+ellipsis+best).strip(),budget,tokenizer)

def _fit_child_prefix_info(prefix,child_text,max_size,tokenizer=None):
    if _token_count(prefix,tokenizer)+_token_count(child_text,tokenizer)+1<=max_size:return prefix,False
    header,_,caput=prefix.partition("\n");child_tokens=_token_count(child_text,tokenizer);prefix_budget=max(1,max_size-child_tokens-1)
    if _token_count(header,tokenizer)>prefix_budget:return _truncate_words_to_tokens(header,prefix_budget,tokenizer),True
    remaining=max(1,prefix_budget-_token_count(header,tokenizer)-1);return f"{header}\n{_excerpt_caput(caput.rstrip(),remaining,tokenizer)}".strip(),True

def _fit_child_prefix(prefix,child_text,max_size,tokenizer=None):
    fitted,_truncated=_fit_child_prefix_info(prefix,child_text,max_size,tokenizer);return fitted

def _article_units(text):
    matches=[m for m in _merged_marker_matches(_ocr_structure_view(text),ARTIGO_RE,ARTIGO_INLINE_RE) if _article_marker_is_real_header(text,m)]
    if not matches:return None
    units=[]
    for i,m in enumerate(matches):
        start=m.start();end=matches[i+1].start() if i+1<len(matches) else len(text);value=text[start:end].strip()
        if value:units.append({"kind":"artigo","ref":m.group(1).strip(),"start":start,"text":value,"headers":_headers_before(text,start)})
    return units

JURIS_SECTION_RE=re.compile(r"(?im)^[ \t]*(EMENTA|TESE/ENTENDIMENTO|TESE|DECISÃO|DECISAO|INTEIRO TEOR|RELATÓRIO|RELATORIO|VOTO|DISPOSITIVO)\s*:?[ \t]*$")
def _jurisprudencia_units(text):
    matches=list(JURISPRUDENCIA_RE.finditer(text))
    if not matches:return None
    units=[]
    for i,m in enumerate(matches):
        start=m.start();end=matches[i+1].start() if i+1<len(matches) else len(text);value=text[start:end].strip();process=re.search(r"^PROCESSO:\s*(.+)$",value,re.I|re.M);sumula=re.search(r"^S[ÚU]MULA:\s*(.+)$",value,re.I|re.M);ref=process.group(1).strip() if process else sumula.group(1).strip() if sumula else None
        units.append({"kind":"jurisprudencia","ref":ref,"start":start,"text":value,"headers":[]})
    return units or None

def _jurisprudencia_sections(text):
    matches=list(JURIS_SECTION_RE.finditer(text))
    if not matches:return [{"kind":"jurisprudencia","ref":None,"start":0,"text":text.strip(),"section":"inteiro_teor"}] if text.strip() else []
    sections=[];first=matches[0].start()
    if text[:first].strip():sections.append({"kind":"jurisprudencia","ref":None,"start":0,"text":text[:first].strip(),"section":"metadados"})
    for i,m in enumerate(matches):
        start=m.start();end=matches[i+1].start() if i+1<len(matches) else len(text);label=re.sub(r"\s+"," ",m.group(1)).strip().casefold().replace(" ","_");value=text[start:end].strip()
        if value:sections.append({"kind":"jurisprudencia","ref":None,"start":start,"text":value,"section":label})
    return sections

def _units(text):
    juris=_jurisprudencia_units(text)
    if juris:return juris
    articles=_article_units(text)
    if articles:return articles
    sums=_find(text,SUMULA_RE,"sumula")
    if sums:
        for u in sums:u["headers"]=_headers_before(text,u["start"])
        return sums
    temas=_find(text,TEMA_RE,"tema")
    if temas:
        for u in temas:u["headers"]=_headers_before(text,u["start"])
        return temas
    return [{"kind":"generic","ref":None,"start":0,"text":text.strip(),"headers":[]}]

SEMANTIC_SOURCE_ROLES={"jurisprudencia","jurisprudencia_controle","orientacao_oficial","doutrina"}
SEMANTIC_DOCUMENT_TYPES={"jurisprudencia","acordao","decisao","sumula","tema","materia","artigo","noticia","manual","guia","orientacao","portal_oficial","doutrina"}
NORMATIVE_DOCUMENT_TYPES={"norma","lei","lei_ordinaria","lei_complementar","decreto","decreto_lei","portaria","resolucao","instrucao_normativa","ato_normativo","emenda_constitucional","constituicao","constituicao_estadual"}
def _is_normative_document(full_text,metadata=None):
    metadata=metadata or {};role=str(metadata.get("source_role") or "").strip().casefold();typ=str(metadata.get("tipo_documento") or "").strip().casefold()
    if role=="norma" or typ in NORMATIVE_DOCUMENT_TYPES:return True
    return bool(re.search(r"(?im)^\s*(?:LEI\s+(?:COMPLEMENTAR\s+)?n?[ºo°.]*|DECRETO(?:-LEI)?\s+n?[ºo°.]*|PORTARIA\s+n?[ºo°.]*|RESOLU(?:ÇÃO|CAO)\s+n?[ºo°.]*|INSTRU(?:ÇÃO|CAO)\s+NORMATIVA\b|EMENDA\s+CONSTITUCIONAL\b|CONSTITUI(?:ÇÃO|CAO)\b)",full_text[:2000]))
def _should_use_ai_semantic(full_text,metadata=None):
    if not config.AI_CHUNKING_ENABLED or len(full_text.strip())<config.AI_CHUNKING_MIN_CHARS:return False
    metadata=metadata or {};role=str(metadata.get("source_role") or "").strip().casefold();typ=str(metadata.get("tipo_documento") or "").strip().casefold()
    return not _is_normative_document(full_text,metadata) and (role in SEMANTIC_SOURCE_ROLES or typ in SEMANTIC_DOCUMENT_TYPES or bool(JURISPRUDENCIA_RE.search(full_text)) or bool(re.search(r"(?im)^\s*FONTE:\s*.+\n\s*T[IÍ]TULO:\s*.+\n\s*DATA[_ ]PUBLICACAO\s*:",full_text)))
def _build_ai_semantic_chunks(full_text,max_size,metadata,semantic_provider=None,tokenizer=None):
    from llm.semantic_chunker import build_semantic_chunks
    unit_kind=str(metadata.get("tipo_documento") or "").strip() or ("jurisprudencia" if JURISPRUDENCIA_RE.search(full_text) else "materia");unit_ref=str(metadata.get("processo") or metadata.get("source_id") or "").strip() or None
    try:
        if semantic_provider is None:
            from llm.factory import get_llm_provider
            semantic_provider=get_llm_provider()
        return build_semantic_chunks(full_text,max_size,unit_kind=unit_kind,unit_ref=unit_ref,provider=semantic_provider,window_chars=config.AI_CHUNKING_WINDOW_CHARS,min_chars=config.AI_CHUNKING_MIN_CHARS,attempts=config.AI_CHUNKING_ATTEMPTS,prompt_version=config.AI_CHUNKING_PROMPT_VERSION,tokenizer=tokenizer)
    except Exception as exc:
        if config.AI_CHUNKING_REQUIRED and not config.AI_CHUNKING_FALLBACK_TO_STRUCTURAL:raise
        print(f"Aviso: chunking semântico indisponível; fallback estrutural aplicado: {exc}");return None

def build_structural_chunks(full_text,max_size,overlap,*,metadata=None,semantic_provider=None,tokenizer=None):
    if max_size<=0:raise ValueError("max_size deve ser maior que zero")
    if overlap<0 or overlap>=max_size:raise ValueError("overlap deve ser maior ou igual a zero e menor que max_size")
    if tokenizer is None:
        tokenizer=_default_tokenizer()
    elif hasattr(tokenizer,"no_truncation"):
        tokenizer.no_truncation()
    units=_units(full_text)
    juris_units=_jurisprudencia_units(full_text)
    if juris_units:
        semantic_chunks={}
        if _should_use_ai_semantic(full_text,metadata):
            for u in juris_units:
                unit_metadata=dict(metadata or {})
                if u.get("ref"):unit_metadata["processo"]=u["ref"]
                semantic=_build_ai_semantic_chunks(u["text"],max_size,unit_metadata,semantic_provider,tokenizer)
                if semantic is not None:
                    semantic_chunks[u.get("ref") or u["start"]]=semantic
        output=[];ref_counts={}
        for u in juris_units:
            ref=u.get("ref");ref_counts[ref]=ref_counts.get(ref,0)+1
        for u in juris_units:
            ref=u.get("ref")
            unit_key=ref or u["start"]
            unit_id=f"jurisprudencia:{ref or u['start']}"+(f":{u['start']}" if ref and ref_counts[ref]>1 else "")
            labels=semantic_chunks.get(unit_key)
            if labels:
                for semantic in labels:
                    item=dict(semantic)
                    item["page_content"]=item["text"]
                    item["full_unit_text"]=u["text"] if _token_count(u["text"],tokenizer)<=max_size else None
                    item["unit_kind"]="jurisprudencia"
                    item["unit_ref"]=ref
                    item["unit_id"]=unit_id
                    item["chunk_index"]=len(output)
                    item["unit_length"]=len(u["text"])
                    item["start"]=u["start"]+int(semantic.get("start",0))
                    item["page_uncertain"]=False
                    item["hierarchy_headers"]=[]
                    item["hierarchy_path"]=list(item.get("hierarchy_path") or [])
                    item["parent_caput"]=None
                    item["child_index"]=None
                    item["segment_kind"]="semantic"
                    item["segment_ref"]=item.get("semantic_topic") or item.get("segment_ref")
                    item["chunking_method"]="ai_semantic"
                    output.append(item)
                continue
            for section in _jurisprudencia_sections(u["text"]):
                for piece,rel,_end in _split_text_spans(section["text"],max_size,overlap,tokenizer):
                    output.append({"text":piece,"full_unit_text":u["text"] if _token_count(u["text"],tokenizer)<=max_size else None,"page_content":piece,"unit_kind":"jurisprudencia","unit_ref":ref,"unit_id":unit_id,"chunk_index":len(output),"unit_length":len(u["text"]),"start":u["start"]+section["start"]+rel,"page_uncertain":False,"chunking_method":"structural","hierarchy_headers":[],"hierarchy_path":[section["section"]],"parent_caput":None,"segment_kind":section["section"],"segment_ref":section["section"],"child_index":None,"prefix_truncated":False})
        if output:return output
    if _should_use_ai_semantic(full_text,metadata) and not _is_normative_document(full_text,metadata):
        semantic=_build_ai_semantic_chunks(full_text,max_size,metadata,semantic_provider,tokenizer)
        if semantic:return semantic
    output=[];ref_counts={}
    for unit in units:
        ref=unit.get("ref")
        if ref:ref_counts[(unit["kind"],ref)]=ref_counts.get((unit["kind"],ref),0)+1
    for unit in units:
        if not unit["text"].strip():continue
        ref=unit.get("ref");unit_id=f"{unit['kind']}:{ref}" if ref else f"{unit['kind']}:{unit['start']}"+(f":{unit['start']}" if ref and ref_counts.get((unit["kind"],ref),0)>1 else "")
        headers=list(unit.get("headers") or [])
        if unit["kind"]!="artigo":
            for idx,(piece,start,_end) in enumerate(_split_text_spans(unit["text"],max_size,overlap,tokenizer)):
                output.append({"text":piece,"full_unit_text":unit["text"] if _token_count(unit["text"],tokenizer)<=max_size else None,"page_content":piece,"unit_kind":unit["kind"],"unit_ref":ref,"unit_id":unit_id,"chunk_index":idx,"unit_length":len(unit["text"]),"start":unit["start"]+start,"page_uncertain":False,"chunking_method":"structural","hierarchy_headers":headers,"hierarchy_path":headers+([ref] if ref else []),"parent_caput":None,"segment_kind":unit["kind"],"segment_ref":ref,"prefix_truncated":False})
            continue
        caput,children=_article_children(unit["text"])
        article_ref=ref or "Artigo"
        article_header=[*headers,article_ref]
        if not children:
            for idx,(piece,start,_end) in enumerate(_split_text_spans(unit["text"],max_size,overlap,tokenizer)):
                output.append({"text":piece,"full_unit_text":unit["text"] if _token_count(unit["text"],tokenizer)<=max_size else None,"page_content":piece,"unit_kind":"artigo","unit_ref":ref,"unit_id":unit_id,"chunk_index":idx,"unit_length":len(unit["text"]),"start":unit["start"]+start,"page_uncertain":False,"chunking_method":"structural","hierarchy_headers":headers,"hierarchy_path":article_header,"parent_caput":caput,"segment_kind":"caput","segment_ref":None,"prefix_truncated":False})
            continue
        caput_index=0
        for piece,start,_end in _split_text_spans(caput,max_size,overlap,tokenizer):
            output.append({"text":piece,"full_unit_text":caput if _token_count(caput,tokenizer)<=max_size else None,"page_content":piece,"unit_kind":"artigo","unit_ref":ref,"unit_id":unit_id,"chunk_index":caput_index,"unit_length":len(unit["text"]),"start":unit["start"]+start,"page_uncertain":False,"chunking_method":"structural","hierarchy_headers":headers,"hierarchy_path":article_header+["CAPUT"],"parent_caput":caput,"segment_kind":"caput","segment_ref":None,"prefix_truncated":False})
            caput_index+=1
        next_index=max(1,caput_index)
        for child_index,(kind,child_ref,child_text,child_start,path_tail) in enumerate(children):
            child_path=article_header+path_tail
            raw_prefix=" > ".join(child_path)+"\n"+caput
            child_prefix,prefix_truncated=_fit_child_prefix_info(raw_prefix,child_text,max_size,tokenizer)
            child_budget=max(1,max_size-_token_count(child_prefix,tokenizer)-1)
            child_spans=_split_text_spans(child_text,child_budget,overlap,tokenizer)
            for local_index,(piece,relative,_end) in enumerate(child_spans):
                rendered=f"{child_prefix}\n{piece}".strip()
                if _token_count(rendered,tokenizer)>max_size:
                    piece=_truncate_words_to_tokens(piece,max(1,max_size-_token_count(child_prefix+"\n",tokenizer)),tokenizer)
                    rendered=f"{child_prefix}\n{piece}".strip()
                    prefix_truncated=True
                output.append({"text":rendered,"full_unit_text":None,"page_content":rendered,"unit_kind":"artigo","unit_ref":ref,"unit_id":unit_id,"chunk_index":next_index+local_index,"unit_length":len(unit["text"]),"start":unit["start"]+child_start+relative,"page_uncertain":False,"chunking_method":"structural","hierarchy_headers":headers,"hierarchy_path":child_path,"parent_caput":caput,"segment_kind":kind,"segment_ref":child_ref,"child_index":child_index,"prefix_truncated":prefix_truncated})
            next_index+=len(child_spans)
    return output