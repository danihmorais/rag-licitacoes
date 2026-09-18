import json
import re
from pathlib import Path
from urllib.parse import urlparse

MODALIDADES = ['Pregão Eletrônico', 'Pregão Presencial', 'Concorrência Eletrônica', 'Concorrência', 'Dispensa Eletrônica', 'Inexigibilidade de Licitação', 'Chamamento Público', 'Credenciamento', 'Leilão']
TIPOS = ['Menor Preço', 'Maior Desconto', 'Melhor Técnica', 'Técnica e Preço', 'Maior Lance', 'Maior Oferta']
PROCESSO_RE = re.compile(r'processo\s*(?:administrativo)?\s*n[ºo°.]*\s*[:\-]?\s*([\d./\-]{4,30})', re.I)
REVISION_RE = re.compile(r'[._](\d{8})\.pdf$', re.I)
SP_NAME_RE = re.compile(r'(?:^|[_\-.])sp(?:[_\-.]|$)', re.I)
FEDERAL_14133_RE = re.compile(r'(?:^|[_\-.])(?:l|lei)?14[ ._\-]?133(?:[_\-.]|$)', re.I)
NORMA_HEADER_RE = re.compile(
    r'(?im)^\s*(?:lei|decreto|decreto-lei|portaria|resolu[cç][aã]o|instru[cç][aã]o\s+normativa|emenda\s+constitucional|lei\s+complementar)'
    r'\s+(?:federal\s+)?n?[ºo°.]*\s*[\d.\-/A-Za-z]*\s*,?\s*de\s+'
    r'(?:\d{1,2}[ºo]?\s+de\s+)?[^\n\d]{3,40}\s+de\s+(20\d{2})\b'
)


def _first(values, text):
    for value in values:
        if re.search(re.escape(value), text, re.I):
            return value
    return None


def _header_value(sample, label):
    match = re.search(rf'(?im)^\s*{re.escape(label)}\s*:\s*(.+)$', sample)
    return match.group(1).strip() if match else None


def _read_sidecar(path):
    sidecar = path.with_suffix('.json')
    if not sidecar.exists():
        return {}
    try:
        values = json.loads(sidecar.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return values if isinstance(values, dict) else {}


def _source(path):
    return _source_with_explicit(path, {})


def _source_with_explicit(path, explicit):
    name = path.name.lower()
    result = {
        'jurisdicao': None, 'esfera': None, 'orgao': None, 'tribunal': None,
        'tipo_documento': None, 'source_role': 'desconhecido', 'authority_level': None,
        'ramo_direito': None, 'normative_rank': None, 'status': 'desconhecido', 'fonte_oficial': None,
        'classificacao_ambigua': False,
        'metadata_ambiguous': False,
    }
    explicit_scope = any(explicit.get(key) not in (None, '') for key in ('jurisdicao', 'esfera', 'orgao', 'tribunal'))
    if explicit_scope:
        return result
    sp_token = bool(SP_NAME_RE.search(name))
    federal_14133 = bool(FEDERAL_14133_RE.search(name)) or bool(re.search(r'lei.?14[ ._\-]?133', name, re.I))
    if sp_token and federal_14133:
        result['classificacao_ambigua'] = True
        result['metadata_ambiguous'] = True
        return result
    if 'tcesp' in name or 'tribunal de contas do estado de são paulo' in name or 'tribunal de contas do estado de sao paulo' in name:
        result.update(jurisdicao='estadual_sp', esfera='estadual', orgao='TCESP', tribunal='TCESP', tipo_documento='jurisprudencia', source_role='jurisprudencia_controle', authority_level=2)
    elif 'tcu' in name:
        result.update(jurisdicao='federal', esfera='federal', orgao='TCU', tribunal='TCU', tipo_documento='jurisprudencia', source_role='jurisprudencia_controle', authority_level=2)
    elif 'stj' in name:
        result.update(jurisdicao='federal', esfera='federal', orgao='STJ', tribunal='STJ', tipo_documento='jurisprudencia', source_role='jurisprudencia', authority_level=2)
    elif 'stf' in name:
        result.update(jurisdicao='federal', esfera='federal', orgao='STF', tribunal='STF', tipo_documento='jurisprudencia', source_role='jurisprudencia', authority_level=2)
    elif 'tcm-sp' in name or 'tcm_sp' in name or 'tcmsP'.casefold() in name:
        result.update(jurisdicao='municipal_sp', esfera='municipal', orgao='TCM-SP', tribunal='TCM-SP', tipo_documento='jurisprudencia', source_role='jurisprudencia_controle', authority_level=2)
    elif 'tjsp' in name:
        result.update(jurisdicao='estadual_sp', esfera='estadual', orgao='TJSP', tribunal='TJSP', tipo_documento='jurisprudencia', source_role='jurisprudencia', authority_level=2)
    elif 'constituicao' in name:
        result.update(jurisdicao='estadual_sp' if 'estadual' in name else 'federal', esfera='estadual' if 'estadual' in name else 'federal', orgao='Constituição', tipo_documento='constituicao', source_role='norma', authority_level=1)
    elif federal_14133:
        result.update(jurisdicao='federal', esfera='federal', orgao='Legislação Federal', tipo_documento='lei', source_role='norma', authority_level=1)
    elif any(x in name for x in ('sustent', 'ambient', 'engenharia', 'obras')):
        result.update(jurisdicao='federal', esfera='federal', orgao='AGU', tipo_documento='guia', source_role='orientacao_oficial', authority_level=3)
    elif sp_token:
        result.update(jurisdicao='estadual_sp', esfera='estadual', orgao='Estado de São Paulo', source_role='norma', authority_level=1)
    elif any(x in name for x in ('lei_', 'decreto_', 'decretolei', 'resolucao_', 'lindb')):
        result.update(jurisdicao='federal', esfera='federal', orgao='Legislação Federal', tipo_documento='norma', source_role='norma', authority_level=1)
    elif 'doutrina' in name:
        result.update(tipo_documento='doutrina', source_role='doutrina', authority_level=4)
    elif any(x in name for x in ('direito_administrativo', 'lindb', 'improbidade')):
        result.update(jurisdicao='federal', esfera='federal', orgao='Legislação Federal', tipo_documento='mapa_fontes', source_role='orientacao_oficial', authority_level=3)
    return result



def _normative_rank(source_role, tipo_documento):
    if source_role != 'norma':
        return None
    tipo = str(tipo_documento or '').casefold()
    if 'constituicao' in tipo:
        return 1
    if tipo in {'lei', 'lei_complementar', 'lei_ordinaria', 'decreto_lei', 'emenda_constitucional'} or tipo.startswith('lei_'):
        return 2
    if tipo == 'decreto' or tipo.startswith('decreto_'):
        return 3
    if tipo in {'instrucao_normativa', 'portaria', 'resolucao', 'deliberacao', 'ato_normativo'}:
        return 4
    return 4


REGIME_CANONICAL = {
    'lei_14133': 'Lei 14.133/2021',
    'lei_8666': 'Lei 8.666/1993',
    'lei_10520': 'Lei 10.520/2002',
    'lei_12462': 'Lei 12.462/2011',
    'jurisprudencia': 'Jurisprudência',
    'transicao': 'Transição legislativa',
    'nao_especificado': 'Não especificado',
}


def _detect_regime(text, source_values):
    source_id = str(source_values.get('source_id') or '').casefold()
    title = str(source_values.get('title') or '').casefold()
    haystack = f'{source_id} {title} {text[:40000]}'
    rules = (
        ('lei_14133', re.compile(r'\blei\s*(?:n[ºo°.]*\s*)?14[.\- ]133\b', re.I)),
        ('lei_8666', re.compile(r'\blei\s*(?:n[ºo°.]*\s*)?8[.\- ]666\b', re.I)),
        ('lei_10520', re.compile(r'\blei\s*(?:n[ºo°.]*\s*)?10[.\- ]520\b', re.I)),
        ('lei_12462', re.compile(r'\blei\s*(?:n[ºo°.]*\s*)?12[.\- ]462\b', re.I)),
    )
    explicit = source_values.get('regime_juridico') or source_values.get('regime')
    if explicit:
        explicit_norm = str(explicit).strip().casefold()
        for key, label in REGIME_CANONICAL.items():
            if explicit_norm in {key, label.casefold()}:
                return key, label
        return str(explicit).strip(), str(explicit).strip()
    detected = [key for key, pattern in rules if pattern.search(haystack)]
    if len(detected) > 1:
        return 'transicao', REGIME_CANONICAL['transicao']
    if detected:
        key = detected[0]
        return key, REGIME_CANONICAL[key]
    if source_values.get('tipo_documento') == 'jurisprudencia' or source_values.get('source_role') in {'jurisprudencia', 'jurisprudencia_controle'}:
        return 'jurisprudencia', REGIME_CANONICAL['jurisprudencia']
    return 'nao_especificado', REGIME_CANONICAL['nao_especificado']


def embedding_metadata_prefix(metadata):
    regime = metadata.get('norma_canonica') or metadata.get('regime_juridico') or REGIME_CANONICAL['nao_especificado']
    status = metadata.get('status') or 'desconhecido'
    esfera = metadata.get('esfera') or 'desconhecida'
    jurisdicao = metadata.get('jurisdicao') or 'desconhecida'
    return (
        f'[REGIME: {regime} | STATUS: {status} | ESFERA: {esfera} | '
        f'JURISDIÇÃO: {jurisdicao}]'
    )

def extract_metadata(text, pdf_path):
    path = Path(pdf_path)
    sample = text[:30000]
    sidecar_values = _read_sidecar(path)
    source_values = _source_with_explicit(path, sidecar_values)
    metadata = {
        'municipio': None, 'modalidade': _first(MODALIDADES, sample), 'ano': None,
        'processo': None, 'tipo': _first(TIPOS, sample), 'data_versao': None,
        'data_publicacao': None, 'data_vigencia': None, 'revogado': None,
        'norma_alteradora': None, 'norm_numero': None, 'norm_ano': None,
        'effective_from': None, 'effective_to': None, 'retrieved_at': None,
        'ramo_direito': None, 'fonte_host': None,
        'regime_juridico': None, 'norma_canonica': None,
        **source_values,
    }
    tribunal = _header_value(sample, 'TRIBUNAL')
    if tribunal and not sidecar_values.get('tribunal'):
        metadata['tribunal'] = tribunal
        metadata['orgao'] = tribunal
        metadata['source_role'] = 'jurisprudencia_controle' if tribunal in {'TCU', 'TCESP'} else 'jurisprudencia'
        metadata['tipo_documento'] = 'jurisprudencia'
        metadata['authority_level'] = {'STF': 2, 'STJ': 2, 'TCU': 2, 'TCESP': 2, 'TJSP': 2, 'TCM-SP': 2}.get(tribunal, 4)
        metadata['status'] = 'jurisprudencia'
        metadata['jurisdicao'] = 'municipal_sp' if tribunal == 'TCM-SP' else ('estadual_sp' if tribunal in {'TCESP', 'TJSP'} else 'federal')
        metadata['esfera'] = 'municipal' if metadata['jurisdicao'] == 'municipal_sp' else ('estadual' if metadata['jurisdicao'] == 'estadual_sp' else 'federal')
    processo_header = _header_value(sample, 'PROCESSO')
    if processo_header and not sidecar_values.get('processo'):
        metadata['processo'] = processo_header
    for label, key in (('DECISÃO/ACÓRDÃO', 'numero_decisao'), ('RELATOR', 'relator'), ('DATA DO JULGAMENTO/SESSÃO', 'data_julgamento')):
        value = _header_value(sample, label)
        if value and not sidecar_values.get(key):
            metadata[key] = value
    match = PROCESSO_RE.search(sample)
    if match and not metadata.get('processo'):
        metadata['processo'] = match.group(1).strip(' .-')
    year_match = NORMA_HEADER_RE.search(sample[:12000])
    if year_match:
        year = int(year_match.group(1))
        metadata['ano'] = year
        metadata['norm_ano'] = year
    revision_match = REVISION_RE.search(path.name)
    if revision_match:
        metadata['data_versao'] = f'{revision_match.group(1)[4:]}-{revision_match.group(1)[2:4]}-{revision_match.group(1)[:2]}'
    for key, value in sidecar_values.items():
        if value not in (None, ''):
            metadata[key] = value
    tribunal = str(metadata.get('tribunal') or '').upper()
    if tribunal:
        inferred_authority = {'STF': 2, 'STJ': 2, 'TCU': 2, 'TCESP': 2, 'TJSP': 2, 'TCM-SP': 2}.get(tribunal)
        if inferred_authority is not None:
            metadata['authority_level'] = inferred_authority
        if tribunal == 'TCM-SP':
            metadata['jurisdicao'], metadata['esfera'] = 'municipal_sp', 'municipal'
        else:
            metadata['jurisdicao'] = 'estadual_sp' if tribunal in {'TCESP', 'TJSP'} else 'federal'
            metadata['esfera'] = 'estadual' if metadata['jurisdicao'] == 'estadual_sp' else 'federal'
    if metadata.get('classificacao_ambigua'):
        metadata['metadata_ambiguous'] = True
    regime_key, regime_label = _detect_regime(sample, {**source_values, **metadata})
    metadata['regime_juridico'] = regime_key
    metadata['norma_canonica'] = regime_label
    if metadata.get('normative_rank') is None:
        metadata['normative_rank'] = _normative_rank(metadata.get('source_role'), metadata.get('tipo_documento'))
    if metadata.get('fonte_oficial'):
        metadata['fonte_host'] = urlparse(str(metadata['fonte_oficial'])).netloc
    return metadata
