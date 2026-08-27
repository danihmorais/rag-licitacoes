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

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'db' / 'source_cache'
HEADERS = {'User-Agent': 'rag-licitacoes-source-sync/1.0', 'Accept': 'text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8'}
LEGAL_RE = re.compile(r'\b(?:Art\.?|Artigo|CAPÍTULO|TÍTULO|SEÇÃO|SUBSEÇÃO|ANEXO|S[ÚU]MULA|LEI|DECRETO|RESOLUÇÃO|PORTARIA)\b', re.I)

# Fontes oficiais. Legislação primária vem primeiro; jurisprudência/orientação é explicitamente classificada.
SOURCES = [
 {'id':'cf1988','title':'Constituição Federal de 1988','urls':['https://www2.camara.leg.br/legin/fed/consti/1988/constituicao-1988-5-outubro-1988-322142-normaatualizada-pl.html','https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Constituição Federal','tipo_documento':'constituicao','source_role':'norma','authority_level':1,'required':True},
 {'id':'lei14133','title':'Lei nº 14.133/2021 — Licitações e Contratos Administrativos','urls':['https://www2.camara.leg.br/legin/fed/lei/2021/lei-14133-1-abril-2021-791222-normaatualizada-pl.html','https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1,'required':True},
 {'id':'decreto12807','title':'Decreto nº 12.807/2025 — valores da Lei nº 14.133/2021','urls':['https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/d12807.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Presidência da República','tipo_documento':'decreto','source_role':'norma','authority_level':1,'required':True},
 {'id':'lindb','title':'Decreto-Lei nº 4.657/1942 — LINDB','urls':['https://www.planalto.gov.br/ccivil_03/decreto-lei/del4657compilado.htm','https://www2.camara.leg.br/legin/fed/declei/1940-1949/decreto-lei-4657-4-setembro-1942-414417-normaatualizada-pe.html'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'decreto_lei','source_role':'norma','authority_level':1,'required':True},
 {'id':'lei9784','title':'Lei nº 9.784/1999 — Processo Administrativo Federal','urls':['https://www2.camara.leg.br/legin/fed/lei/1999/lei-9784-29-janeiro-1999-322239-normaatualizada-pl.html','https://www.planalto.gov.br/ccivil_03/leis/l9784.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1,'required':True},
 {'id':'lei8429','title':'Lei nº 8.429/1992 — Improbidade Administrativa','urls':['https://www2.camara.leg.br/legin/fed/lei/1992/lei-8429-2-junho-1992-357452-normaatualizada-pl.html','https://www.planalto.gov.br/ccivil_03/leis/l8429.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'lei12846','title':'Lei nº 12.846/2013 — Lei Anticorrupção','urls':['https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12846.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'decreto11129','title':'Decreto nº 11.129/2022 — Lei Anticorrupção','urls':['https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/decreto/d11129.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Presidência da República','tipo_documento':'decreto','source_role':'norma','authority_level':1},
 {'id':'lei12527','title':'Lei nº 12.527/2011 — Lei de Acesso à Informação','urls':['https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'lei13709','title':'Lei nº 13.709/2018 — LGPD','urls':['https://www2.camara.leg.br/legin/fed/lei/2018/lei-13709-14-agosto-2018-787077-normaatualizada-pl.html','https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'lei13303','title':'Lei nº 13.303/2016 — Empresas Estatais','urls':['https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2016/lei/l13303.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'lei8987','title':'Lei nº 8.987/1995 — Concessões e Permissões','urls':['https://www.planalto.gov.br/ccivil_03/leis/l8987cons.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'lei11079','title':'Lei nº 11.079/2004 — PPPs','urls':['https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l11079.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'lrf','title':'Lei Complementar nº 101/2000 — Responsabilidade Fiscal','urls':['https://www2.camara.leg.br/legin/fed/leicom/2000/leicomplementar-101-4-maio-2000-351480-normaatualizada-pl.html','https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp101.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei_complementar','source_role':'norma','authority_level':1},
 {'id':'lei4320','title':'Lei nº 4.320/1964 — Direito Financeiro','urls':['https://www.planalto.gov.br/ccivil_03/leis/l4320compilado.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'lei6938','title':'Lei nº 6.938/1981 — Política Nacional do Meio Ambiente','urls':['https://www.planalto.gov.br/ccivil_03/leis/l6938compilada.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'lei12305','title':'Lei nº 12.305/2010 — Resíduos Sólidos','urls':['https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2010/lei/l12305.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'lei9605','title':'Lei nº 9.605/1998 — Crimes Ambientais','urls':['https://www.planalto.gov.br/ccivil_03/leis/l9605.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'lei13146','title':'Lei nº 13.146/2015 — Estatuto da Pessoa com Deficiência','urls':['https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13146.htm'],'jurisdicao':'federal','esfera':'federal','orgao':'Legislação Federal','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'pncp','title':'PNCP — legislação e atos oficiais','urls':['https://www.gov.br/pncp/pt-br/pncp/legislacao/leis'],'jurisdicao':'federal','esfera':'federal','orgao':'PNCP','tipo_documento':'portal_oficial','source_role':'orientacao_oficial','authority_level':3},
 {'id':'compras','title':'Compras.gov.br — legislação de contratações públicas','urls':['https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao'],'jurisdicao':'federal','esfera':'federal','orgao':'Compras.gov.br','tipo_documento':'portal_oficial','source_role':'orientacao_oficial','authority_level':3},
 {'id':'compras-in','title':'Compras.gov.br — Instruções Normativas','urls':['https://www.gov.br/compras/pt-br/acesso-a-informacao/legislacao/instrucoes-normativas'],'jurisdicao':'federal','esfera':'federal','orgao':'Compras.gov.br','tipo_documento':'instrucao_normativa','source_role':'norma','authority_level':1},
 {'id':'agu','title':'AGU — modelos de Licitações e Contratos da Lei nº 14.133/2021','urls':['https://www.gov.br/agu/pt-br/composicao/cgu/cgu/modelos/licitacoesecontratos/14133'],'jurisdicao':'federal','esfera':'federal','orgao':'AGU','tipo_documento':'modelo_orientacao','source_role':'orientacao_oficial','authority_level':3,'follow_links':True},
 {'id':'tcu','title':'TCU — Licitações e Contratos: orientações e jurisprudência','urls':['https://portal.tcu.gov.br/publicacoes-institucionais/cartilha-manual-ou-tutorial/licitacoes-e'],'jurisdicao':'federal','esfera':'federal','orgao':'TCU','tribunal':'TCU','tipo_documento':'manual','source_role':'jurisprudencia_controle','authority_level':2,'follow_links':True},
 {'id':'tcesp','title':'TCESP — Súmulas e Boletim de Jurisprudência','urls':['https://www.tce.sp.gov.br/boletim-de-jurisprudencia/sumulas'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'TCESP','tribunal':'TCESP','tipo_documento':'sumula','source_role':'jurisprudencia_controle','authority_level':2,'required':True},
 {'id':'sp-const','title':'Constituição do Estado de São Paulo — texto atualizado','urls':['https://www.al.sp.gov.br/repositorio/legislacao/constituicao/1989/compilacao-constituicao-0-05.10.1989.html'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP','tipo_documento':'constituicao_estadual','source_role':'norma','authority_level':1,'required':True},
 {'id':'sp-lei10177','title':'Lei SP nº 10.177/1998 — Processo Administrativo','urls':['https://www.al.sp.gov.br/repositorio/legislacao/lei/1998/compilacao-lei-10177-30.12.1998.html'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP','tipo_documento':'lei','source_role':'norma','authority_level':1,'required':True},
 {'id':'sp-lc709','title':'LC SP nº 709/1993 — Lei Orgânica do TCESP','urls':['https://www.al.sp.gov.br/norma/?id=16279'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP/TCESP','tipo_documento':'lei_complementar','source_role':'norma','authority_level':1,'required':True},
 {'id':'sp-lei6544','title':'Lei SP nº 6.544/1989 — licitações e contratos','urls':['https://www.al.sp.gov.br/repositorio/legislacao/lei/1989/compilacao-lei-6544-22.11.1989.html'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP','tipo_documento':'lei','source_role':'norma','authority_level':1},
 {'id':'sp-compras','title':'Compras SP — legislação e regulamentação','urls':['https://compras.sp.gov.br/legislacao/'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'Compras SP','tipo_documento':'portal_oficial','source_role':'orientacao_oficial','authority_level':3,'required':True},
 {'id':'sp-pca','title':'Decreto SP nº 67.689/2023 — Plano de Contratações Anual','urls':['https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67689-03.05.2023.html'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP','tipo_documento':'decreto','source_role':'norma','authority_level':1,'required':True},
 {'id':'sp-precos','title':'Decreto SP nº 67.888/2023 — pesquisa de preços','urls':['https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67888-17.08.2023.html'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP','tipo_documento':'decreto','source_role':'norma','authority_level':1,'required':True},
 {'id':'sp-etp','title':'Decreto SP nº 68.017/2023 — Estudo Técnico Preliminar','urls':['https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68017-11.10.2023.html'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP','tipo_documento':'decreto','source_role':'norma','authority_level':1,'required':True},
 {'id':'sp-tr','title':'Decreto SP nº 68.185/2023 — Termo de Referência','urls':['https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68185-11.12.2023.html'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP','tipo_documento':'decreto','source_role':'norma','authority_level':1,'required':True},
 {'id':'sp-agentes','title':'Decreto SP nº 68.220/2023 — agentes, gestores e fiscais','urls':['https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68220-15.12.2023.html'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP','tipo_documento':'decreto','source_role':'norma','authority_level':1,'required':True},
 {'id':'sp-direta','title':'Decreto SP nº 68.304/2024 — contratação direta eletrônica','urls':['https://www.al.sp.gov.br/repositorio/legislacao/decreto/2024/decreto-68304-09.01.2024.html'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP','tipo_documento':'decreto','source_role':'norma','authority_level':1,'required':True},
 {'id':'sp-leilao','title':'Decreto SP nº 68.422/2024 — leilão eletrônico','urls':['https://www.al.sp.gov.br/repositorio/legislacao/decreto/2024/decreto-68422-02.04.2024.html'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP','tipo_documento':'decreto','source_role':'norma','authority_level':1,'required':True},
 {'id':'sp-par','title':'Decreto SP nº 69.588/2025 — responsabilização de pessoas jurídicas','urls':['https://www.al.sp.gov.br/repositorio/legislacao/decreto/2025/decreto-69588-09.06.2025.html'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP','tipo_documento':'decreto','source_role':'norma','authority_level':1},
 {'id':'sp-integridade','title':'Decreto SP nº 69.861/2025 — programas de integridade','urls':['https://www.al.sp.gov.br/repositorio/legislacao/decreto/2025/decreto-69861-11.09.2025.html'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'ALESP','tipo_documento':'decreto','source_role':'norma','authority_level':1},
 {'id':'sp-marketplace','title':'Resolução SGGD nº 34/2026 — Marketplace.SP e credenciamento','urls':['https://compras.sp.gov.br/resolucao-sggd-no-34-de-29-de-julho-de-2026/'],'jurisdicao':'estadual_sp','esfera':'estadual','orgao':'Compras SP','tipo_documento':'resolucao','source_role':'norma','authority_level':1}
]


def make_session():
    s = requests.Session()
    retry = Retry(total=5, connect=5, read=5, status=5, backoff_factor=1.5, status_forcelist=(408,429,500,502,503,504), allowed_methods=frozenset({'GET','HEAD'}), respect_retry_after_header=True)
    s.mount('https://', HTTPAdapter(max_retries=retry)); s.mount('http://', HTTPAdapter(max_retries=retry)); s.headers.update(HEADERS)
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
        if line and len(line)<=10000: lines.append(line)
    return '\n'.join(lines)


def pdf_text(data):
    CACHE.mkdir(parents=True, exist_ok=True); path=CACHE/'.tmp.pdf'; path.write_bytes(data)
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
    if source.get('source_role')=='norma' and (not LEGAL_RE.search(text) or (source.get('tipo_documento')!='resolucao' and text.lower().count('art')<2)):
        raise RuntimeError('conteúdo não aparenta ser íntegra normativa')


def write_cache(source,final,kind,raw,text):
    CACHE.mkdir(parents=True, exist_ok=True); sid=source['id']
    (CACHE/f'{sid}.txt').write_text(text.strip()+'\n', encoding='utf-8')
    meta={'source_id':sid,'title':source['title'],'jurisdicao':source.get('jurisdicao'),'esfera':source.get('esfera'),'orgao':source.get('orgao'),'tribunal':source.get('tribunal'),'tipo_documento':source.get('tipo_documento'),'source_role':source.get('source_role','desconhecido'),'authority_level':source.get('authority_level'),'status':'vigente' if source.get('source_role')=='norma' else 'orientativo','fonte_oficial':final,'fonte_host':urlparse(final).netloc,'retrieved_at':datetime.now(timezone.utc).isoformat(),'data_versao':datetime.now(timezone.utc).strftime('%Y-%m-%d'),'source_kind':kind,'sha256':hashlib.sha256(raw).hexdigest()}
    (CACHE/f'{sid}.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def sync_one(session,source,check=False):
    last=''
    for url in source.get('urls',[]):
        try:
            kind,final,raw,text=fetch(session,url); validate(source,text)
            if not check: write_cache(source,final,kind,raw,text)
            return True,f"OK {source['id']} via {final} ({kind}, {len(text)} chars)"
        except Exception as exc: last=f'{type(exc).__name__}: {exc}'
    return False,f"FAIL {source['id']}: {last}"


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true'); parser.add_argument('--required-only',action='store_true'); args=parser.parse_args()
    sources=[s for s in SOURCES if not args.required_only or s.get('required')]; session=make_session(); failures=[]; ok=0
    for source in sources:
        good,message=sync_one(session,source,args.check); print(message); ok += int(good)
        if not good: failures.append(source['id'])
    print(f'Fontes: {ok}/{len(sources)} OK')
    if failures: print('Falhas:', ', '.join(failures))
    return 1 if args.required_only and failures else 0

if __name__=='__main__': raise SystemExit(main())
