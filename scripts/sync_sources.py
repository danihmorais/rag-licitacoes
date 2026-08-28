from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from scripts.sources import SOURCES
except ModuleNotFoundError:
    from sources import SOURCES

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'db' / 'source_cache'
HEADERS = {'User-Agent': 'rag-licitacoes-source-sync/2.0 (+https://github.com/danihmorais/rag-licitacoes)', 'Accept': 'text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8'}
LEGAL_RE = re.compile(r'\b(?:Art\.?|Artigo|CAPÍTULO|TÍTULO|SEÇÃO|SUBSEÇÃO|ANEXO|S[ÚU]MULA|LEI|DECRETO|RESOLUÇÃO|PORTARIA)\b', re.I)
NOISE = {'[Input]', '[Button: Pesquisar]', 'expand_more', 'collapse'}


def make_session():
    s = requests.Session()
    retry = Retry(total=5, connect=5, read=5, status=5, backoff_factor=1.5, status_forcelist=(408,429,500,502,503,504), allowed_methods=frozenset({'GET','HEAD'}), respect_retry_after_header=True)
    adapter = HTTPAdapter(max_retries=retry); s.mount('https://', adapter); s.mount('http://', adapter); s.headers.update(HEADERS)
    return s


def clean_html(raw):
    soup = BeautifulSoup(raw, 'html.parser')
    for tag in soup(['script','style','noscript','nav','header','footer','form','aside']): tag.decompose()
    for tag in soup.find_all(style=True):
        if 'line-through' in tag.get('style','').replace(' ','').lower(): tag.decompose()
    root = soup.find('main') or soup.find(id=re.compile(r'conteudo|content|corpo', re.I)) or soup.body or soup
    lines=[]
    for line in root.get_text('\n', strip=True).splitlines():
        line=html.unescape(re.sub(r'\s+',' ',line)).strip()
        if line and line not in NOISE and len(line)<=10000: lines.append(line)
    return '\n'.join(lines)


def pdf_text(data):
    CACHE.mkdir(parents=True, exist_ok=True); path=CACHE/'.sync_tmp.pdf'; path.write_bytes(data)
    try: return '\n\f\n'.join(page.extract_text() or '' for page in PdfReader(str(path)).pages)
    finally: path.unlink(missing_ok=True)


def fetch(session,url):
    response=session.get(url, timeout=(20,90), allow_redirects=True); response.raise_for_status()
    raw=response.content; final=response.url; ctype=(response.headers.get('content-type') or '').lower()
    is_pdf='application/pdf' in ctype or final.lower().split('?',1)[0].endswith('.pdf') or raw.startswith(b'%PDF')
    if is_pdf: return 'pdf', final, raw, pdf_text(raw)
    response.encoding=response.apparent_encoding or response.encoding
    return 'html', final, raw, clean_html(response.text)


def validate(source,text):
    if len(text.strip()) < 800: raise RuntimeError(f'conteúdo insuficiente: {len(text)} caracteres')
    if source.get('source_role') == 'norma':
        if not LEGAL_RE.search(text): raise RuntimeError('conteúdo não aparenta ser íntegra normativa')
        if source.get('tipo_documento') not in {'resolucao','portal_oficial'} and text.lower().count('art') < 2: raise RuntimeError('conteúdo normativo suspeito/incompleto')


def slug(value):
    value=re.sub(r'[^0-9A-Za-zÀ-ÿ]+','_',value,flags=re.UNICODE).strip('_'); return re.sub(r'_+','_',value)[:120] or 'documento'


def discover_links(raw_html,base_url,source):
    soup=BeautifulSoup(raw_html,'html.parser'); patterns=[re.compile(p,re.I) for p in source.get('follow_patterns',())]; host=urlparse(base_url).netloc.lower(); out=[]; seen=set()
    for a in soup.find_all('a',href=True):
        absolute=urljoin(base_url,str(a['href']).strip()).split('#',1)[0]; parsed=urlparse(absolute)
        if parsed.scheme not in {'http','https'} or (not source.get('allow_cross_host') and parsed.netloc.lower()!=host): continue
        label=a.get_text(' ',strip=True); hay=f'{absolute} {label}'
        if patterns and not any(p.search(hay) for p in patterns): continue
        if absolute in seen: continue
        seen.add(absolute); out.append((absolute,label or absolute.rsplit('/',1)[-1]))
        if len(out)>=int(source.get('max_follow',12)): break
    return out


def write_cache(source,final,kind,raw,text,document_id,title):
    CACHE.mkdir(parents=True,exist_ok=True); base=slug(document_id)
    (CACHE/f'{base}.txt').write_text(text.strip()+'\n',encoding='utf-8')
    meta={'source_id':source['id'],'document_id':base,'parent_source_id':source['id'],'title':title,'jurisdicao':source.get('jurisdicao'),'esfera':source.get('esfera'),'orgao':source.get('orgao'),'tribunal':source.get('tribunal'),'tipo_documento':source.get('tipo_documento'),'source_role':source.get('source_role','desconhecido'),'authority_level':source.get('authority_level'),'status':source.get('status') or 'orientativo','revogado':source.get('revogado',False),'data_publicacao':source.get('data_publicacao'),'data_vigencia':source.get('data_vigencia'),'effective_from':source.get('effective_from'),'effective_to':source.get('effective_to'),'norma_alteradora':source.get('norma_alteradora'),'fonte_oficial':final,'fonte_host':urlparse(final).netloc,'retrieved_at':datetime.now(timezone.utc).isoformat(),'data_versao':source.get('data_versao'),'source_kind':kind,'sha256':hashlib.sha256(raw).hexdigest()}
    (CACHE/f'{base}.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def sync_one(session,source,check=False,follow_links=True):
    last=''
    for url in source.get('urls',[]):
        try:
            kind,final,raw,text=fetch(session,url); validate(source,text)
            if not check: write_cache(source,final,kind,raw,text,source['id'],source['title'])
            linked_ok=linked_total=0
            if follow_links and source.get('follow_links') and kind=='html':
                for link_url,link_title in discover_links(raw,final,source):
                    linked_total += 1
                    try:
                        lk,lf,lr,lt=fetch(session,link_url); validate(source,lt); linked_ok += 1
                        if not check:
                            did=f"{source['id']}__{slug(link_title)}__{hashlib.sha1(lf.encode()).hexdigest()[:10]}"
                            write_cache(source,lf,lk,lr,lt,did,link_title)
                    except Exception as exc: print(f'  aviso: link {link_url} falhou: {type(exc).__name__}: {exc}')
            suffix=f', PDFs linkados {linked_ok}/{linked_total}' if linked_total else ''
            return True,f"OK {source['id']} via {final} ({kind}, {len(text)} chars{suffix})"
        except Exception as exc: last=f'{type(exc).__name__}: {exc}'
    return False,f"FAIL {source['id']}: {last}"


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true'); parser.add_argument('--required-only',action='store_true'); parser.add_argument('--no-follow-links',action='store_true'); args=parser.parse_args()
    sources=[s for s in SOURCES if not args.required_only or s.get('required')]; session=make_session(); failures=[]; ok=0
    for source in sources:
        good,message=sync_one(session,source,check=args.check,follow_links=not args.no_follow_links and not args.check); print(message); ok += int(good)
        if not good: failures.append(source['id'])
    print(f'Fontes: {ok}/{len(sources)} OK')
    if failures: print('Falhas:',', '.join(failures))
    return 1 if failures and args.required_only else 0

if __name__=='__main__': raise SystemExit(main())
