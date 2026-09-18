from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config
from .schema import JurisprudenciaRecord

DEFAULT_QUERY = 'licitação'
TRIBUNALS = ('tcu', 'tcesp', 'stj', 'stf', 'tcm-sp', 'tjsp')
HEADERS = {
    'User-Agent': 'rag-licitacoes-jurisprudencia/2.0 (+https://github.com/danihmorais/rag-licitacoes)',
    'Accept': 'text/html,application/xhtml+xml,application/json,application/pdf;q=0.9,*/*;q=0.8',
}


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=1.5,
        status_forcelist=(408, 425, 429, 500, 502, 503, 504),
        allowed_methods=frozenset({'GET', 'POST', 'HEAD'}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    session.headers.update(HEADERS)
    return session


def clean_text(value: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(value or '')).strip()


def page_text(raw: bytes) -> str:
    soup = BeautifulSoup(raw, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'nav', 'header', 'footer', 'form', 'aside']):
        tag.decompose()
    return '\n'.join(line.strip() for line in soup.get_text('\n').splitlines() if clean_text(line))


def pdf_text(data: bytes) -> str:
    config.SOURCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix='.jurisprudencia_',
            suffix='.pdf',
            dir=config.SOURCE_CACHE_DIR,
            delete=False,
        ) as handle:
            handle.write(data)
            temp_name = handle.name
        return '\n\f\n'.join(page.extract_text() or '' for page in PdfReader(temp_name).pages).strip()
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def fetch(session: requests.Session, url: str, *, method: str = 'GET', **kwargs: Any):
    response = session.request(method, url, timeout=(20, 90), allow_redirects=True, **kwargs)
    response.raise_for_status()
    content_type = (response.headers.get('content-type') or '').lower()
    final = response.url
    if 'application/pdf' in content_type or final.lower().split('?', 1)[0].endswith('.pdf') or response.content.startswith(b'%PDF'):
        return 'pdf', final, response.content
    response.encoding = response.apparent_encoding or response.encoding
    return 'html', final, response.content


def _first_value(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ''):
            return str(value).strip()
    return ''


def _as_list(*values: str) -> list[str]:
    return [value for value in (clean_text(v) for v in values) if value]


def _query_terms(query: str) -> list[str]:
    return list(dict.fromkeys(
        term for term in re.findall(r'[\wÀ-ÿ]+', query.casefold())
        if len(term) >= 3
    ))


def _query_matches(query: str, *fields: str) -> bool:
    terms = _query_terms(query)
    if not terms:
        return True
    haystack = clean_text(' '.join(fields)).casefold()
    hits = sum(term in haystack for term in terms)
    required = len(terms) if len(terms) <= 2 else max(2, (len(terms) + 1) // 2)
    return hits >= required


def _find_query_field(form: BeautifulSoup, keywords: tuple[str, ...]):
    for label in form.find_all('label'):
        label_text = clean_text(label.get_text(' ', strip=True)).casefold()
        if not any(keyword in label_text for keyword in keywords):
            continue
        target = str(label.get('for') or '').strip()
        if target:
            field = form.find(id=target)
            if field is not None and field.name in {'input', 'textarea'}:
                return field
        parent = label.parent
        if parent is not None:
            field = parent.find(['input', 'textarea'])
            if field is not None:
                return field
    for field in form.find_all(['input', 'textarea']):
        descriptor = (
            str(field.get('name') or '') + ' ' +
            str(field.get('id') or '') + ' ' +
            str(field.get('placeholder') or '')
        ).casefold()
        if any(keyword in descriptor for keyword in keywords):
            if str(field.get('type') or 'text').lower() not in {'submit', 'button', 'reset', 'hidden'}:
                return field
    return None


def _form_data(form: BeautifulSoup, query: str, keywords: tuple[str, ...]) -> tuple[str, str, dict[str, str]] | None:
    query_field = _find_query_field(form, keywords)
    if query_field is None:
        return None
    data: dict[str, str] = {}
    for field in form.find_all(['input', 'select', 'textarea']):
        name = str(field.get('name') or '').strip()
        if not name:
            continue
        if field.name == 'input':
            field_type = str(field.get('type') or 'text').lower()
            if field_type in {'submit', 'button', 'reset', 'image', 'file'}:
                continue
            if field_type in {'checkbox', 'radio'} and not field.has_attr('checked'):
                continue
            data[name] = str(field.get('value') or '')
        elif field.name == 'select':
            option = field.find('option', selected=True) or field.find('option')
            data[name] = str(option.get('value') if option else '')
        else:
            data[name] = str(field.get_text() or '')
    query_name = str(query_field.get('name') or '').strip()
    if not query_name:
        return None
    data[query_name] = query
    action = str(form.get('action') or '').strip()
    method = str(form.get('method') or 'get').lower()
    return action, method, data


def _extract_pdf_links(raw: bytes, base_url: str) -> list[str]:
    soup = BeautifulSoup(raw, 'html.parser')
    links = []
    seen = set()
    for anchor in soup.find_all('a', href=True):
        href = urljoin(base_url, str(anchor['href']).strip()).split('#', 1)[0]
        label = clean_text(anchor.get_text(' ', strip=True)).casefold()
        parsed = urlparse(href)
        looks_pdf = (
            parsed.path.casefold().endswith('.pdf')
            or '/arqs_juri/pdf/' in parsed.path.casefold()
            or 'pdf' in parsed.path.casefold()
            or 'inteiro' in label
        )
        if not looks_pdf or parsed.scheme not in {'http', 'https'} or href in seen:
            continue
        seen.add(href)
        links.append(href)
    return links


def _extract_ementa(text: str) -> str | None:
    if not text:
        return None
    match = re.search(
        r'(?is)\bEMENTA\b\s*[:\-]?\s*(.+?)(?=\n\s*(?:ACÓRDÃO|ACORDAO|RELATÓRIO|RELATORIO|VOTO|DISPOSITIVO)\b|\Z)',
        text,
    )
    return clean_text(match.group(1)) if match else None


def _label_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf'(?im)^\s*{re.escape(label)}\s*[:\-]?\s*(.+)$', text)
        if match:
            return clean_text(match.group(1))
    return None


def _extract_process(text: str, url: str = '') -> str:
    patterns = (
        r'\b\d{1,7}-\d{2}\.20\d{2}\.8\.26\.\d{4}\b',
        r'\b(?:REsp|AREsp|AgInt no REsp|AgRg no REsp|RMS|MS|HC|RHC|AgInt|EDcl)\s+[\d.]+(?:/[A-Z]{2})?',
        r'\b\d{1,7}/989/\d{2}\b',
        r'\b\d{1,7}[\d.]+/[A-Z]{2}\b',
        r'\b\d{1,7}/\d{1,7}/\d{2,4}\b',
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return clean_text(match.group(0))
    query_value = re.search(r'(?:^|&)livre=([^&]+)', urlparse(url).query, re.I)
    return query_value.group(1) if query_value else ''


def _detail_enrichment(session: requests.Session, url: str, *, with_content: bool):
    kind, final, raw = fetch(session, url)
    if kind != 'html':
        return '', final, ''
    detail_text = page_text(raw)
    content = ''
    if with_content:
        pdfs = _extract_pdf_links(raw, final)
        chunks = []
        for pdf_url in pdfs[:3]:
            try:
                pdf_kind, pdf_final, pdf_raw = fetch(session, pdf_url)
                if pdf_kind == 'pdf':
                    chunks.append(f'FONTE: {pdf_final}\n{pdf_text(pdf_raw)}')
            except Exception as exc:
                print(f'aviso: PDF de inteiro teor indisponível em {pdf_url}: {type(exc).__name__}: {exc}')
        content = '\n\n---\n\n'.join(chunk for chunk in chunks if chunk.strip())
        if not content:
            content = detail_text
    return detail_text, final, content


class JurisprudenciaAdapter(ABC):
    tribunal: str

    def __init__(self, session: requests.Session) -> None:
        self.session = session

    @abstractmethod
    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        raise NotImplementedError


class TCUAdapter(JurisprudenciaAdapter):
    tribunal = 'TCU'
    endpoint = 'https://dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos'

    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        records = []
        start = 0
        page_size = min(max(limit * 4, 50), 100)
        while len(records) < limit and start < 10000:
            response = self.session.get(
                self.endpoint,
                params={'inicio': start, 'quantidade': page_size},
                timeout=(20, 90),
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload
            if isinstance(payload, dict):
                for key in ('data', 'items', 'acordaos', 'resultados'):
                    if isinstance(payload.get(key), list):
                        rows = payload[key]
                        break
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                title = _first_value(row, 'titulo', 'sumario', 'ementa')
                area = _first_value(row, 'area')
                tema = _first_value(row, 'tema')
                subtema = _first_value(row, 'subtema')
                if not _query_matches(query, title, area, tema, subtema):
                    continue
                number = _first_value(row, 'numeroAcordao', 'numeroDecisao')
                process = _first_value(row, 'numeroProcessoFormatado', 'numeroProcesso', 'processo') or _first_value(row, 'key') or number
                record = JurisprudenciaRecord(
                    tribunal='TCU',
                    numero_processo=process,
                    orgao_julgador=_first_value(row, 'colegiado'),
                    relator=_first_value(row, 'relator'),
                    data=_first_value(row, 'dataSessao', 'dataSessaoFormatada'),
                    ementa=_first_value(row, 'sumario', 'ementa', 'titulo'),
                    assunto=_as_list(area, tema, subtema),
                    url_oficial=_first_value(row, 'urlAcordao', 'urlArquivo', 'urlArquivoPDF'),
                    tipo_decisao=_first_value(row, 'tipo') or 'Acórdão',
                    numero_decisao=number,
                    origem='TCU — dados abertos de acórdãos',
                    situacao=_first_value(row, 'situacao'),
                )
                if with_content:
                    pdf_url = _first_value(row, 'urlArquivoPDF', 'urlArquivo')
                    if pdf_url:
                        try:
                            pdf_kind, final, raw = fetch(self.session, pdf_url)
                            if pdf_kind == 'pdf':
                                record.inteiro_teor = pdf_text(raw)
                                record.url_oficial = final
                        except Exception as exc:
                            print(f'aviso: inteiro teor TCU indisponível para {number}: {type(exc).__name__}: {exc}')
                records.append(record)
                if len(records) >= limit:
                    break
            if len(rows) < page_size:
                break
            start += len(rows)
        return records


class TCESPAdapter(JurisprudenciaAdapter):
    tribunal = 'TCESP'
    endpoint = 'https://www.tce.sp.gov.br/jurisprudencia/pesquisar'

    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        records = []
        offset = 0
        page_size = 10
        seen_processes = set()
        while len(records) < limit and offset < 1000:
            params = {
                'acao': 'Executa',
                'offset': offset,
                'dataAutuacaoFim': '',
                'dataAutuacaoInicio': '',
                'exercicio': '',
                'processo': '',
                'quantTrechos': 3,
                'tipoBuscaTxt': 'Documento',
                'tipoDocumento': '',
                '_auditor': 1,
                '_materia': 1,
                '_relator': 1,
                'txtExp': '',
                'txtNenhPalvs': '',
                'txtNumFim': '',
                'txtNumIni': '',
                'txtQqUma': '',
                'txtTdPalvs': query,
            }
            response = self.session.get(self.endpoint, params=params, timeout=(20, 90))
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            table = next(
                (
                    table for table in soup.find_all('table')
                    if 'N° Proc.' in clean_text(table.get_text(' ', strip=True)) or 'Nº Proc.' in clean_text(table.get_text(' ', strip=True))
                ),
                None,
            )
            if table is None:
                raise RuntimeError(
                    'Estrutura da pesquisa TCESP alterada: tabela de resultados com coluna '
                    'N° Proc./Nº Proc. não foi encontrada.'
                )
            found_on_page = 0
            expect_excerpt = False
            for row in table.find_all('tr'):
                cells = [clean_text(cell.get_text(' ', strip=True)) for cell in row.find_all(['th', 'td'])]
                if not cells:
                    continue
                joined = ' | '.join(cells)
                if expect_excerpt and records:
                    excerpt = joined
                    if excerpt:
                        records[-1].ementa = excerpt
                    expect_excerpt = False
                    continue
                if 'trechos localizados' in joined.casefold():
                    expect_excerpt = True
                    continue
                if len(cells) < 7 or not re.search(r'\d{2}/\d{2}/\d{4}', cells[2]):
                    continue
                detail_anchor = next(
                    (anchor for anchor in row.find_all('a', href=True)
                     if '/jurisprudencia/exibir' in str(anchor['href'])),
                    None,
                )
                detail_url = urljoin(response.url, str(detail_anchor['href'])) if detail_anchor else response.url
                process = cells[1]
                if process in seen_processes or not _query_matches(query, *cells):
                    continue
                seen_processes.add(process)
                record = JurisprudenciaRecord(
                    tribunal='TCESP',
                    numero_processo=process,
                    data_autuacao=cells[2],
                    ementa=cells[6],
                    assunto=_as_list(cells[5], cells[6]),
                    tipo_decisao=cells[0] or 'Jurisprudência',
                    origem='TCESP — Pesquisa de Jurisprudência',
                    url_oficial=detail_url,
                    partes=_as_list(cells[3], cells[4]),
                )
                if detail or with_content:
                    try:
                        detail_text, final, content = _detail_enrichment(
                            self.session,
                            detail_url,
                            with_content=with_content,
                        )
                        record.url_oficial = final
                        record.relator = _label_value(detail_text, ('Relator', 'RELATOR'))
                        record.data_publicacao = _label_value(detail_text, ('Data de Publicação', 'Data da Publicação'))
                        record.ementa = _extract_ementa(content or detail_text) or record.ementa
                        if with_content and content:
                            record.inteiro_teor = content
                    except Exception as exc:
                        print(f'aviso: detalhe TCESP indisponível para {process}: {type(exc).__name__}: {exc}')
                records.append(record)
                found_on_page += 1
            if found_on_page == 0:
                break
            offset += page_size
        return records


class STJAdapter(JurisprudenciaAdapter):
    tribunal = 'STJ'
    endpoint = 'https://scon.stj.jus.br/SCON/pesquisar.jsp'

    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        params = {
            'acao': 'pesquisar',
            'novaConsulta': 'true',
            'i': 1,
            'b': 'ACOR',
            'livre': query,
            'thesaurus': 'JURIDICO',
            'tp': 'P',
            'tipo_visualizacao': 'RESUMO',
        }
        response = self.session.get(self.endpoint, params=params, timeout=(20, 90))
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        page_descriptor = clean_text(soup.get_text(' ', strip=True)).casefold()
        if 'pesquisa de jurisprudência' not in page_descriptor and 'pesquisa jurisprudencial' not in page_descriptor:
            raise RuntimeError('Estrutura do SCON/STJ não reconhecida: área de pesquisa jurisprudencial não encontrada.')
        records = []
        seen = set()
        for anchor in soup.find_all('a', href=True):
            absolute = urljoin(response.url, str(anchor['href']))
            label = clean_text(anchor.get_text(' ', strip=True))
            if '/SCON/jurisprudencia/doc.jsp' not in absolute or not label or absolute in seen:
                continue
            seen.add(absolute)
            detail_text = ''
            content = ''
            if detail or with_content:
                try:
                    detail_text, final, content = _detail_enrichment(self.session, absolute, with_content=with_content)
                    absolute = final
                except Exception as exc:
                    print(f'aviso: detalhe STJ indisponível: {type(exc).__name__}: {exc}')
            source_text = content or detail_text
            records.append(
                JurisprudenciaRecord(
                    tribunal='STJ',
                    numero_processo=_extract_process(label, absolute) or _extract_process(source_text, absolute) or label,
                    relator=_label_value(source_text, ('RELATOR', 'Relator')),
                    data=_label_value(source_text, ('DATA DO JULGAMENTO', 'Data do julgamento', 'JULGAMENTO')),
                    orgao_julgador=_label_value(source_text, ('ÓRGÃO JULGADOR', 'ORGAO JULGADOR', 'Órgão Julgador')),
                    ementa=_extract_ementa(source_text) or label,
                    assunto=['licitações/contratos'] if 'licit' in clean_text(label).casefold() else [],
                    url_oficial=absolute,
                    tipo_decisao=_label_value(source_text, ('TIPO', 'Tipo')) or 'Acórdão',
                    origem='STJ — SCON',
                    inteiro_teor=content or None,
                )
            )
            if len(records) >= limit:
                break
        return records


class STFAdapter(JurisprudenciaAdapter):
    tribunal = 'STF'
    endpoint = 'https://jurisprudencia.stf.jus.br/pages/search'

    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        params = {
            'base': 'acordaos',
            'pesquisa_inteiro_teor': 'true',
            'sinonimo': 'true',
            'plural': 'true',
            'radicais': 'false',
            'buscaExata': 'false',
            'page': 1,
            'pageSize': min(max(limit * 2, 25), 100),
            'queryString': query,
            'sort': 'date',
            'sortBy': 'desc',
        }
        kind, final, raw = fetch(self.session, self.endpoint, method='GET', params=params)
        if kind != 'html':
            raise RuntimeError('Pesquisa do STF retornou uma resposta não HTML inesperada.')
        soup = BeautifulSoup(raw, 'html.parser')
        records = []
        seen = set()
        for anchor in soup.find_all('a', href=True):
            absolute = urljoin(final, str(anchor['href']).strip())
            parsed = urlparse(absolute)
            label = clean_text(anchor.get_text(' ', strip=True))
            if parsed.netloc.lower() != 'jurisprudencia.stf.jus.br' or not re.match(r'^/pages/search/.+/(?:true|false)$', parsed.path, re.I):
                continue
            if not label and anchor.parent is not None:
                label = clean_text(anchor.parent.get_text(' ', strip=True))
            if not label or absolute in seen:
                continue
            seen.add(absolute)
            detail_text = ''
            content = ''
            if detail or with_content:
                try:
                    detail_text, detail_final, content = _detail_enrichment(self.session, absolute, with_content=with_content)
                    absolute = detail_final
                except Exception as exc:
                    print(f'aviso: detalhe STF indisponível: {type(exc).__name__}: {exc}')
            source_text = content or detail_text
            process = _extract_process(label, absolute) or _extract_process(source_text, absolute) or label
            records.append(
                JurisprudenciaRecord(
                    tribunal='STF',
                    numero_processo=process,
                    relator=_label_value(source_text, ('RELATOR', 'Relator')),
                    data=_label_value(source_text, ('DATA DO JULGAMENTO', 'Data do julgamento', 'Julgamento')),
                    orgao_julgador=_label_value(source_text, ('ÓRGÃO JULGADOR', 'ORGAO JULGADOR', 'Órgão julgador')),
                    ementa=_extract_ementa(source_text) or label,
                    assunto=['controle constitucional'] if any(token in clean_text(source_text + ' ' + label).casefold() for token in ('constitucional', 'repercussão geral', 'repercussao geral')) else [],
                    url_oficial=absolute,
                    tipo_decisao='Acórdão',
                    origem='STF — Jurisprudência Oficial',
                    inteiro_teor=content or None,
                )
            )
            if len(records) >= limit:
                break
        return records


class TCMSPAdapter(JurisprudenciaAdapter):
    tribunal = 'TCM-SP'
    endpoint = 'https://jurisprudencia.tcm.sp.gov.br/Acordao/Index'

    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        kind, final, raw = fetch(self.session, self.endpoint)
        if kind != 'html':
            raise RuntimeError('Página de pesquisa do TCM-SP retornou uma resposta não HTML inesperada.')
        soup = BeautifulSoup(raw, 'html.parser')
        result_raw = raw
        result_url = final
        form = next(
            (
                form for form in soup.find_all('form')
                if any(
                    token in clean_text(form.get_text(' ', strip=True)).casefold()
                    for token in ('pesquisa', 'ementa', 'palavra', 'acórdão', 'acordao')
                )
            ),
            None,
        )
        if form is None:
            raise RuntimeError('Formulário de pesquisa do TCM-SP não foi encontrado na página oficial.')
        payload = _form_data(form, query, ('pesquisa', 'ementa', 'palavra', 'termo', 'livre', 'acord'))
        if payload is None:
            raise RuntimeError('Campo de pesquisa do TCM-SP não foi encontrado no formulário oficial.')
        action, method, data = payload
        action = urljoin(final, action or final)
        try:
            kind, result_url, result_raw = fetch(
                self.session,
                action,
                method='POST' if method == 'post' else 'GET',
                data=data if method == 'post' else None,
                params=data if method != 'post' else None,
            )
        except Exception as exc:
            raise RuntimeError(f'Consulta TCM-SP pelo formulário falhou: {type(exc).__name__}: {exc}') from exc
        if kind != 'html':
            raise RuntimeError('Pesquisa do TCM-SP retornou uma resposta não HTML inesperada.')
        soup = BeautifulSoup(result_raw, 'html.parser')
        records = []
        seen = set()
        for anchor in soup.find_all('a', href=True):
            absolute = urljoin(result_url, str(anchor['href'])).split('#', 1)[0]
            parsed = urlparse(absolute)
            if parsed.netloc.lower() != urlparse(result_url).netloc.lower():
                continue
            path = parsed.path.casefold()
            if '/acordao/' not in path and '/sumula' not in path:
                continue
            label = clean_text(anchor.get_text(' ', strip=True))
            container = anchor.find_parent(['tr', 'li', 'article', 'section', 'div'])
            container_text = clean_text(container.get_text(' ', strip=True)) if container else label
            label = label or container_text[:500]
            if not label or absolute in seen or not _query_matches(query, label, container_text):
                continue
            process = _extract_process(container_text, absolute) or _extract_process(label, absolute)
            if not process:
                sumula = re.search(r'\bS[ÚU]MULA\s*N?[ºO.]?\s*(\d+)\b', container_text, re.I)
                process = f'Súmula {sumula.group(1)}' if sumula else ''
            if not process:
                continue
            seen.add(absolute)
            detail_text = ''
            content = ''
            relator = None
            data = None
            ementa = label
            if detail or with_content:
                try:
                    detail_text, detail_final, content = _detail_enrichment(self.session, absolute, with_content=with_content)
                    absolute = detail_final
                    relator = _label_value(detail_text, ('RELATOR', 'Relator'))
                    data = _label_value(detail_text, ('DATA DO JULGAMENTO', 'Data do julgamento', 'SESSÃO'))
                    ementa = _extract_ementa(content or detail_text) or ementa
                except Exception as exc:
                    print(f'aviso: detalhe TCM-SP indisponível para {process}: {type(exc).__name__}: {exc}')
            records.append(
                JurisprudenciaRecord(
                    tribunal='TCM-SP',
                    numero_processo=process,
                    relator=relator,
                    data=data,
                    ementa=ementa,
                    assunto=_as_list('licitações/contratos', 'controle municipal'),
                    url_oficial=absolute,
                    tipo_decisao='Súmula' if process.casefold().startswith('súmula') else 'Acórdão',
                    origem='TCM-SP — Jurisprudência Oficial',
                    inteiro_teor=content or None,
                )
            )
            if len(records) >= limit:
                break
        return records


class TJSPAdapter(JurisprudenciaAdapter):
    tribunal = 'TJSP'
    endpoint = 'https://esaj.tjsp.jus.br/cjsg/consultaCompleta.do'
    result_endpoint = 'https://esaj.tjsp.jus.br/cjsg/resultadoCompleta.do'

    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        kind, final, raw = fetch(self.session, self.endpoint)
        if kind != 'html':
            return []
        soup = BeautifulSoup(raw, 'html.parser')
        form = _find_query_form(soup, ('pesquisa livre', 'pesquisa', 'livre'))
        if form is None:
            raise RuntimeError('formulário de Pesquisa Livre do TJSP não foi encontrado')
        payload = _form_data(form, query, ('pesquisa livre', 'livre', 'pesquisa'))
        if payload is None:
            raise RuntimeError('campo Pesquisa Livre do TJSP não foi encontrado')
        action, method, data = payload
        action = urljoin(final, action or self.result_endpoint)
        kind, result_url, result_raw = fetch(
            self.session,
            action,
            method='POST' if method == 'post' else 'GET',
            data=data if method == 'post' else None,
            params=data if method != 'post' else None,
        )
        if kind != 'html':
            raise RuntimeError('Pesquisa do TJSP retornou uma resposta não HTML inesperada.')
        soup = BeautifulSoup(result_raw, 'html.parser')
        records = []
        seen = set()
        for row in soup.find_all(['tr', 'article', 'li']):
            row_text = clean_text(row.get_text(' ', strip=True))
            if len(row_text) < 30 or not _query_matches(query, row_text):
                continue
            anchors = row.find_all('a', href=True)
            pdf_url = next(
                (
                    urljoin(result_url, str(anchor['href']).strip())
                    for anchor in anchors
                    if 'getarquivo.do' in str(anchor['href']).casefold()
                ),
                '',
            )
            detail_url = next(
                (
                    urljoin(result_url, str(anchor['href']).strip())
                    for anchor in anchors
                    if '/cjsg/' in str(anchor['href']).casefold()
                    and 'consultaCompleta.do' not in str(anchor['href']).casefold()
                    and 'resultadoCompleta.do' not in str(anchor['href']).casefold()
                    and 'getarquivo.do' not in str(anchor['href']).casefold()
                ),
                '',
            )
            target = pdf_url or detail_url or result_url
            process = _extract_process(row_text, target)
            if not process and pdf_url:
                process = _extract_process(row_text)
            if not process:
                continue
            key = (process, pdf_url or detail_url)
            if key in seen:
                continue
            seen.add(key)
            ementa = row_text[:4000]
            relator = _label_value(row_text, ('Relator', 'Relator(a)'))
            data = _label_value(row_text, ('Data do julgamento', 'Data do Julgamento', 'Data de julgamento'))
            orgao = _label_value(row_text, ('Órgão julgador', 'Órgão Julgador', 'Orgão julgador'))
            inteiro_teor = None
            official_url = detail_url or pdf_url or result_url
            if detail or with_content:
                try:
                    if pdf_url and with_content:
                        pdf_kind, pdf_final, pdf_raw = fetch(self.session, pdf_url)
                        if pdf_kind == 'pdf':
                            inteiro_teor = pdf_text(pdf_raw)
                            official_url = pdf_final
                            ementa = _extract_ementa(inteiro_teor) or ementa
                    elif detail_url:
                        detail_text, detail_final, content = _detail_enrichment(
                            self.session,
                            detail_url,
                            with_content=with_content,
                        )
                        official_url = detail_final
                        relator = _label_value(detail_text, ('RELATOR', 'Relator', 'Relator(a)')) or relator
                        data = _label_value(detail_text, ('DATA DO JULGAMENTO', 'Data do julgamento')) or data
                        orgao = _label_value(detail_text, ('ÓRGÃO JULGADOR', 'Órgão julgador')) or orgao
                        ementa = _extract_ementa(content or detail_text) or ementa
                        inteiro_teor = content or None
                except Exception as exc:
                    print(f'aviso: detalhe TJSP indisponível para {process}: {type(exc).__name__}: {exc}')
            records.append(
                JurisprudenciaRecord(
                    tribunal='TJSP',
                    numero_processo=process,
                    orgao_julgador=orgao,
                    relator=relator,
                    data=data,
                    ementa=ementa,
                    url_oficial=official_url,
                    tipo_decisao='Acórdão',
                    origem='TJSP — e-SAJ Jurisprudência',
                    inteiro_teor=inteiro_teor,
                )
            )
            if len(records) >= limit:
                break
        return records


def _find_query_form(soup: BeautifulSoup, keywords: tuple[str, ...]):
    candidates = []
    for form in soup.find_all('form'):
        descriptor = clean_text(form.get_text(' ', strip=True)).casefold()
        fields = clean_text(
            ' '.join(
                str(field.get('name') or '') + ' ' + str(field.get('id') or '') + ' ' + str(field.get('placeholder') or '')
                for field in form.find_all(['input', 'textarea'])
            )
        ).casefold()
        if any(keyword in descriptor or keyword in fields for keyword in keywords):
            candidates.append(form)
    return candidates[0] if candidates else None


def _discover_form(soup: BeautifulSoup):
    return _find_query_form(soup, ('jurisprud', 'pesquisa'))


def adapters(session):
    return {
        'tcu': TCUAdapter(session),
        'tcesp': TCESPAdapter(session),
        'stj': STJAdapter(session),
        'stf': STFAdapter(session),
        'tcm-sp': TCMSPAdapter(session),
        'tjsp': TJSPAdapter(session),
    }


def save_record(record: JurisprudenciaRecord, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    record.validate()
    record.retrieved_at = record.retrieved_at or datetime.now(timezone.utc).isoformat()
    record.version_sha256 = record.version_sha256 or record.calculate_version_sha256()
    source_id = {
        'TCU': 'tcu-jurisprudencia',
        'TCESP': 'tcesp-jurisprudencia',
        'STJ': 'stj-jurisprudencia-estruturada',
        'STF': 'stf-jurisprudencia-estruturada',
        'TCM-SP': 'tcm-sp-jurisprudencia',
        'TJSP': 'tjsp-jurisprudencia-estruturada',
    }.get(record.tribunal, f'{record.tribunal.lower()}-jurisprudencia')
    basename = f'jurisprudencia__{record.tribunal.lower()}__{record.document_key}__{record.version_sha256[:10]}'
    text_path = output_dir / f'{basename}.txt'
    json_path = output_dir / f'{basename}.json'
    text_path.write_text(record.to_index_text(), encoding='utf-8')
    metadata = {
        **record.to_dict(),
        'document_id': basename,
        'source_id': source_id,
        'parent_source_id': source_id,
        'source_role': 'jurisprudencia_controle' if record.tribunal in {'TCU', 'TCESP', 'TCM-SP'} else 'jurisprudencia',
        'jurisdicao': 'municipal_sp' if record.tribunal == 'TCM-SP' else ('estadual_sp' if record.tribunal in {'TCESP', 'TJSP'} else 'federal'),
        'esfera': 'municipal' if record.tribunal == 'TCM-SP' else ('estadual' if record.tribunal in {'TCESP', 'TJSP'} else 'federal'),
        'orgao': record.tribunal,
        'tribunal': record.tribunal,
        'tipo_documento': 'jurisprudencia',
        'authority_level': 2,
        'normative_rank': None,
        'status': 'jurisprudencia',
        'fonte_oficial': record.url_oficial,
        'fonte_host': urlparse(record.url_oficial).netloc if record.url_oficial else None,
        'version_sha256': record.version_sha256,
    }
    json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return text_path


def collect(
    tribunals,
    query,
    limit,
    *,
    detail=False,
    with_content=False,
    output_dir=None,
    persist=True,
    strict=False,
) -> list[JurisprudenciaRecord]:
    output_dir = output_dir or (config.SOURCE_CACHE_DIR / 'jurisprudencia')
    session = make_session()
    source_adapters = adapters(session)
    output = []
    failures = []
    for tribunal in tribunals:
        if tribunal not in source_adapters:
            raise ValueError(f'Tribunal não suportado: {tribunal}')
        try:
            records = source_adapters[tribunal].search(
                query,
                limit,
                detail=detail,
                with_content=with_content,
            )
        except Exception as exc:
            message = f'{type(exc).__name__}: {exc}'
            print(f'FAIL {tribunal}: {message}')
            failures.append((tribunal, message))
            continue
        for record in records:
            if persist:
                save_record(record, output_dir)
            output.append(record)
        print(f'OK {tribunal}: {len(records)} registros para {query!r}')
    if strict and failures:
        details = '; '.join(f'{tribunal}: {message}' for tribunal, message in failures)
        raise RuntimeError('Falhas de coleta jurisprudencial: ' + details)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description='Coleta jurisprudência oficial em formato estruturado para o RAG.')
    parser.add_argument('--tribunais', default=','.join(TRIBUNALS))
    parser.add_argument('--query', default=DEFAULT_QUERY)
    parser.add_argument('--limit', type=int, default=25)
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--with-content', action='store_true')
    parser.add_argument('--strict', action='store_true', help='Falha se algum tribunal solicitado não retornar registros.')
    parser.add_argument('--output-dir', type=Path, default=None)
    args = parser.parse_args()
    tribunals = tuple(item.strip().lower() for item in args.tribunais.split(',') if item.strip())
    unknown = [item for item in tribunals if item not in TRIBUNALS]
    if unknown:
        parser.error('tribunais inválidos: ' + ', '.join(unknown))
    config.ensure_directories()
    counts = {}
    failed = []
    output_dir = args.output_dir or (config.SOURCE_CACHE_DIR / 'jurisprudencia')
    session = make_session()
    source_adapters = adapters(session)
    for tribunal in tribunals:
        try:
            records = source_adapters[tribunal].search(args.query, max(1, args.limit), detail=args.detail, with_content=args.with_content)
        except Exception as exc:
            print(f'FAIL {tribunal}: {type(exc).__name__}: {exc}')
            failed.append(tribunal)
            counts[tribunal] = 0
            continue
        counts[tribunal] = len(records)
        for record in records:
            save_record(record, output_dir)
        print(f'OK {tribunal}: {len(records)} registros para {args.query!r}')
        if not records:
            failed.append(tribunal)
    print(f'Tribunais: {len([value for value in counts.values() if value > 0])}/{len(counts)} com registros')
    print('Registros:', sum(counts.values()))
    if args.strict and failed:
        print('Falhas jurisprudenciais bloqueantes:', ', '.join(failed))
        return 1
    return 0 if sum(counts.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
