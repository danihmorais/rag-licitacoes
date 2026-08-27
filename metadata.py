import json,re
from pathlib import Path
from urllib.parse import urlparse

MODALIDADES=['Pregão Eletrônico','Pregão Presencial','Concorrência Eletrônica','Concorrência','Dispensa Eletrônica','Inexigibilidade de Licitação','Chamamento Público','Credenciamento','Leilão']
TIPOS=['Menor Preço','Maior Desconto','Melhor Técnica','Técnica e Preço','Maior Lance','Maior Oferta']
PROCESSO_RE=re.compile(r'processo\s*(?:administrativo)?\s*n[ºo°.]*\s*[:\-]?\s*([\d./\-]{4,30})',re.I)
ANO_RE=re.compile(r'\b(20\d{2})\b')
REVISION_RE=re.compile(r'[._](\d{8})\.pdf$',re.I)


def _first(xs,text):
    for x in xs:
        if re.search(re.escape(x),text,re.I): return x


def _source(p):
    n=p.name.lower()
    r={'jurisdicao':None,'esfera':None,'orgao':None,'tribunal':None,'tipo_documento':None,'source_role':'desconhecido','authority_level':None,'status':'desconhecido','fonte_oficial':None}
    if 'tcesp' in n or 'tribunal de contas do estado de são paulo' in n or 'tribunal de contas do estado de sao paulo' in n:
        r.update(jurisdicao='estadual_sp',esfera='estadual',orgao='TCESP',tribunal='TCESP',tipo_documento='jurisprudencia',source_role='jurisprudencia_controle',authority_level=2)
    elif 'tcu' in n:
        r.update(jurisdicao='federal',esfera='federal',orgao='TCU',tribunal='TCU',tipo_documento='jurisprudencia',source_role='jurisprudencia_controle',authority_level=2)
    elif 'stj' in n:
        r.update(jurisdicao='federal',esfera='federal',orgao='STJ',tribunal='STJ',tipo_documento='jurisprudencia',source_role='jurisprudencia',authority_level=2)
    elif 'constituicao' in n:
        r.update(jurisdicao='federal' if 'estadual' not in n else 'estadual_sp',esfera='federal' if 'estadual' not in n else 'estadual',orgao='Constituição',tipo_documento='constituicao',source_role='norma',authority_level=1)
    elif re.search(r'l\.?\s*14[ ._\-]?133|lei.?14[ ._\-]?133',n):
        r.update(jurisdicao='federal',esfera='federal',orgao='Legislação Federal',tipo_documento='lei',source_role='norma',authority_level=1)
    elif any(x in n for x in ('lei_','decreto_','decretolei','resolucao_','lin db'.replace(' ',''))):
        r.update(tipo_documento='norma',source_role='norma',authority_level=1)
    elif 'sustent' in n or 'ambient' in n or 'engenharia' in n or 'obras' in n:
        r.update(jurisdicao='federal',esfera='federal',orgao='AGU',tipo_documento='guia',source_role='orientacao_oficial',authority_level=3)
    elif 'doutrina' in n:
        r.update(tipo_documento='doutrina',source_role='doutrina',authority_level=4)
    elif 'direito_administrativo' in n or 'lindb' in n or 'improbidade' in n:
        r.update(jurisdicao='federal',esfera='federal',orgao='Legislação Federal',tipo_documento='mapa_fontes',source_role='orientacao_oficial',authority_level=3)
    return r


def extract_metadata(text,pdf_path):
    p=Path(pdf_path); sample=text[:20000]
    m={'municipio':None,'modalidade':_first(MODALIDADES,sample),'ano':None,'processo':None,'tipo':_first(TIPOS,sample),'data_versao':None,'data_publicacao':None,'data_vigencia':None,'revogado':None,'norma_alteradora':None,'norm_numero':None,'norm_ano':None,'effective_from':None,'effective_to':None,'retrieved_at':None,'fonte_host':None,**_source(p)}
    x=PROCESSO_RE.search(sample)
    if x:m['processo']=x.group(1).strip(' .-')
    y=ANO_RE.findall(sample)
    if y:m['ano']=int(y[0]);m['norm_ano']=int(y[0])
    x=REVISION_RE.search(p.name)
    if x:m['data_versao']=f'{x.group(1)[4:]}-{x.group(1)[2:4]}-{x.group(1)[:2]}'
    side=p.with_suffix('.json')
    if side.exists():
        try:m.update({k:v for k,v in json.loads(side.read_text(encoding='utf-8')).items() if v not in (None,'')})
        except (OSError,json.JSONDecodeError):pass
    if m.get('fonte_oficial'):m['fonte_host']=urlparse(str(m['fonte_oficial'])).netloc
    return m
