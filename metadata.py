import json
import re
from pathlib import Path
from urllib.parse import urlparse

MODALIDADES = ['Pregão Eletrônico', 'Pregão Presencial', 'Concorrência Eletrônica', 'Concorrência', 'Dispensa Eletrônica', 'Inexigibilidade de Licitação', 'Chamamento Público', 'Credenciamento', 'Leilão']
TIPOS = ['Menor Preço', 'Maior Desconto', 'Melhor Técnica', 'Técnica e Preço', 'Maior Lance', 'Maior Oferta']
PROCESSO_RE = re.compile(r'processo\s*(?:administrativo)?\s*n[ºo°.]*\s*[:\-]?\s*([\d./\-]{4,30})', re.I)
REVISION_RE = re.compile(r'[._](\d{8})\.pdf$', re.I)
SP_NAME_RE = re.compile(r'(?:^|[_\-.])sp(?:[_\-.]|$)', re.I)
NORMA_YEAR_RE = re.compile(
    r'\b(?:lei|decreto|decreto-lei|portaria|resolu[cç][aã]o|instru[cç][aã]o\s+normativa|emenda\s+constitucional|lei\s+complementar)'
    r'\b[^\n]{0,220}?\bde\s+(?:\d{1,2}[ºo]?\s+de\s+[^\d\n]{3,30}\s+de\s+)?(20\d{2})\b',
    re.I,
)


def _first(values, text):
    for value in values:
        if re.search(re.escape(value), text, re.I):
            return value
    return None


def _header_value(sample, label):
    match = re.search(rf'(?im)^\s*{re.escape(label)}\s*:\s*(.+)$', sample)
    return match.group(1).strip() if match else None


def _source(path):
    name = path.name.lower()
    result = {
        'jurisdicao': None, 'esfera': None, 'orgao': None, 'tribunal': None,
        'tipo_documento': None, 'source_role': 'desconhecido', 'authority_level': None,
        'status': 'desconhecido', 'fonte_oficial': None,
    }
    if 'tcesp' in name or 'tribunal de contas do estado de são paulo' in name or 'tribunal de contas do estado de sao paulo' in name:
        result.update(jurisdicao='estadual_sp', esfera='estadual', orgao='TCESP', tribunal='TCESP', tipo_documento='jurisprudencia', source_role='jurisprudencia_controle', authority_level=4)
    elif 'tcu' in name:
        result.update(jurisdicao='federal', esfera='federal', orgao='TCU', tribunal='TCU', tipo_documento='jurisprudencia', source_role='jurisprudencia_controle', authority_level=3)
    elif 'stj' in name:
        result.update(jurisdicao='federal', esfera='federal', orgao='STJ', tribunal='STJ', tipo_documento='jurisprudencia', source_role='jurisprudencia', authority_level=3)
    elif 'stf' in name:
        result.update(jurisdicao='federal', esfera='federal', orgao='STF', tribunal='STF', tipo_documento='jurisprudencia', source_role='jurisprudencia', authority_level=2)
    elif 'tjsp' in name or 'tjsp' in name.replace('-', ''):
        result.update(jurisdicao='estadual_sp', esfera='estadual', orgao='TJSP', tribunal='TJSP', tipo_documento='jurisprudencia', source_role='jurisprudencia', authority_level=4)
    elif 'constituicao' in name:
        result.update(jurisdicao='estadual_sp' if 'estadual' in name else 'federal', esfera='estadual' if 'estadual' in name else 'federal', orgao='Constituição', tipo_documento='constituicao', source_role='norma', authority_level=1)
    elif SP_NAME_RE.search(name):
        result.update(jurisdicao='estadual_sp', esfera='estadual', orgao='Estado de São Paulo', source_role='norma', authority_level=1)
    elif re.search(r'l\.?\s*14[ ._\-]?133|lei.?14[ ._\-]?133', name):
        result.update(jurisdicao='federal', esfera='federal', orgao='Legislação Federal', tipo_documento='lei', source_role='norma', authority_level=1)
    elif any(x in name for x in ('lei_', 'decreto_', 'decretolei', 'resolucao_', 'lindb')):
        result.update(jurisdicao='federal', esfera='federal', orgao='Legislação Federal', tipo_documento='norma', source_role='norma', authority_level=1)
    elif any(x in name for x in ('sustent', 'ambient', 'engenharia', 'obras')):
        result.update(jurisdicao='federal', esfera='federal', orgao='AGU', tipo_documento='guia', source_role='orientacao_oficial', authority_level=3)
    elif 'doutrina' in name:
        result.update(tipo_documento='doutrina', source_role='doutrina', authority_level=5)
    elif any(x in name for x in ('direito_administrativo', 'lindb', 'improbidade')):
        result.update(jurisdicao='federal', esfera='federal', orgao='Legislação Federal', tipo_documento='mapa_fontes', source_role='orientacao_oficial', authority_level=3)
    return result


def extract_metadata(text, pdf_path):
    path = Path(pdf_path)
    sample = text[:30000]
    metadata = {
        'municipio': None, 'modalidade': _first(MODALIDADES, sample), 'ano': None,
        'processo': None, 'tipo': _first(TIPOS, sample), 'data_versao': None,
        'data_publicacao': None, 'data_vigencia': None, 'revogado': None,
        'norma_alteradora': None, 'norm_numero': None, 'norm_ano': None,
        'effective_from': None, 'effective_to': None, 'retrieved_at': None,
        'fonte_host': None, **_source(path),
    }
    tribunal = _header_value(sample, 'TRIBUNAL')
    if tribunal:
        metadata['tribunal'] = tribunal
        metadata['orgao'] = tribunal
        metadata['source_role'] = 'jurisprudencia_controle' if tribunal in {'TCU', 'TCESP'} else 'jurisprudencia'
        metadata['tipo_documento'] = 'jurisprudencia'
        metadata['authority_level'] = {
            'STF': 2,
            'STJ': 3,
            'TCU': 3,
            'TCESP': 4,
            'TJSP': 4,
        }.get(tribunal, 4)
        metadata['status'] = 'jurisprudencia'
        metadata['jurisdicao'] = 'estadual_sp' if tribunal in {'TCESP', 'TJSP'} else 'federal'
        metadata['esfera'] = 'estadual' if metadata['jurisdicao'] == 'estadual_sp' else 'federal'
    processo_header = _header_value(sample, 'PROCESSO')
    if processo_header:
        metadata['processo'] = processo_header
    if _header_value(sample, 'DECISÃO/ACÓRDÃO'):
        metadata['numero_decisao'] = _header_value(sample, 'DECISÃO/ACÓRDÃO')
    if _header_value(sample, 'RELATOR'):
        metadata['relator'] = _header_value(sample, 'RELATOR')
    if _header_value(sample, 'DATA DO JULGAMENTO/SESSÃO'):
        metadata['data_julgamento'] = _header_value(sample, 'DATA DO JULGAMENTO/SESSÃO')
    match = PROCESSO_RE.search(sample)
    if match and not metadata.get('processo'):
        metadata['processo'] = match.group(1).strip(' .-')
    year_match = NORMA_YEAR_RE.search(sample[:12000])
    if year_match:
        year = int(year_match.group(1))
        metadata['ano'] = year
        metadata['norm_ano'] = year
    match = REVISION_RE.search(path.name)
    if match:
        metadata['data_versao'] = f'{match.group(1)[4:]}-{match.group(1)[2:4]}-{match.group(1)[:2]}'
    sidecar = path.with_suffix('.json')
    if sidecar.exists():
        try:
            values = json.loads(sidecar.read_text(encoding='utf-8'))
            metadata.update({key: value for key, value in values.items() if value not in (None, '')})
        except (OSError, json.JSONDecodeError):
            pass
    if metadata.get('fonte_oficial'):
        metadata['fonte_host'] = urlparse(str(metadata['fonte_oficial'])).netloc
    return metadata
