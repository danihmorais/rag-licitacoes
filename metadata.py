import json
import re
from pathlib import Path
from urllib.parse import urlparse

MODALIDADES = ['Pregão Eletrônico', 'Pregão Presencial', 'Concorrência Eletrônica', 'Concorrência', 'Dispensa Eletrônica', 'Inexigibilidade de Licitação', 'Chamamento Público', 'Credenciamento', 'Leilão']
TIPOS = ['Menor Preço', 'Maior Desconto', 'Melhor Técnica', 'Técnica e Preço', 'Maior Lance', 'Maior Oferta']
PROCESSO_RE = re.compile(r'processo\s*(?:administrativo)?\s*n[ºo°.]*\s*[:\-]?\s*([\d./\-]{4,30})', re.I)
ANO_RE = re.compile(r'\b(20\d{2})\b')
REVISION_RE = re.compile(r'[._](\d{8})\.pdf$', re.I)


def _first(values, text):
    for value in values:
        if re.search(re.escape(value), text, re.I):
            return value
    return None


def _source(path):
    name = path.name.lower()
    result = {
        'jurisdicao': None, 'esfera': None, 'orgao': None, 'tribunal': None,
        'tipo_documento': None, 'source_role': 'desconhecido', 'authority_level': None,
        'status': 'desconhecido', 'fonte_oficial': None,
    }
    if 'tcesp' in name or 'tribunal de contas do estado de são paulo' in name or 'tribunal de contas do estado de sao paulo' in name:
        result.update(jurisdicao='estadual_sp', esfera='estadual', orgao='TCESP', tribunal='TCESP', tipo_documento='jurisprudencia', source_role='jurisprudencia_controle', authority_level=2)
    elif 'tcu' in name:
        result.update(jurisdicao='federal', esfera='federal', orgao='TCU', tribunal='TCU', tipo_documento='jurisprudencia', source_role='jurisprudencia_controle', authority_level=2)
    elif 'stj' in name:
        result.update(jurisdicao='federal', esfera='federal', orgao='STJ', tribunal='STJ', tipo_documento='jurisprudencia', source_role='jurisprudencia', authority_level=2)
    elif 'constituicao' in name:
        result.update(jurisdicao='estadual_sp' if 'estadual' in name else 'federal', esfera='estadual' if 'estadual' in name else 'federal', orgao='Constituição', tipo_documento='constituicao', source_role='norma', authority_level=1)
    elif re.search(r'l\.?\s*14[ ._\-]?133|lei.?14[ ._\-]?133', name):
        result.update(jurisdicao='federal', esfera='federal', orgao='Legislação Federal', tipo_documento='lei', source_role='norma', authority_level=1)
    elif 'sp_' in name or name.startswith('sp'):
        result.update(jurisdicao='estadual_sp', esfera='estadual', orgao='Estado de São Paulo', source_role='norma', authority_level=1)
    elif any(x in name for x in ('lei_', 'decreto_', 'decretolei', 'resolucao_', 'lindb')):
        result.update(jurisdicao='federal', esfera='federal', orgao='Legislação Federal', tipo_documento='norma', source_role='norma', authority_level=1)
    elif any(x in name for x in ('sustent', 'ambient', 'engenharia', 'obras')):
        result.update(jurisdicao='federal', esfera='federal', orgao='AGU', tipo_documento='guia', source_role='orientacao_oficial', authority_level=3)
    elif 'doutrina' in name:
        result.update(tipo_documento='doutrina', source_role='doutrina', authority_level=4)
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
    match = PROCESSO_RE.search(sample)
    if match:
        metadata['processo'] = match.group(1).strip(' .-')
    years = ANO_RE.findall(sample)
    if years:
        metadata['ano'] = int(years[0])
        metadata['norm_ano'] = int(years[0])
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
