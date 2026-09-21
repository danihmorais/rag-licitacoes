from __future__ import annotations

import argparse
import hashlib
import html
import itertools
import json
import os
import random
import re
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import requests
try:
    import truststore
except ImportError:
    truststore = None
from bs4 import BeautifulSoup
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config
from .schema import JurisprudenciaRecord

DEFAULT_QUERY = 'licitação'
TRIBUNALS = ('tcu', 'tcesp', 'stj', 'stf', 'tjsp')
USER_AGENTS = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/132.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 Version/18.2 Safari/605.1.15',
    'rag-licitacoes-jurisprudencia/3.0 (+https://github.com/danihmorais/rag-licitacoes)',
)
HEADERS = {
    'User-Agent': USER_AGENTS[0],
    'Accept': 'text/html,application/xhtml+xml,application/json,application/pdf;q=0.9,*/*;q=0.8',
}
DEFAULT_HTTP_TIMEOUT = (
    float(os.getenv('RAG_JURISPRUDENCIA_CONNECT_TIMEOUT', '20')),
    float(os.getenv('RAG_JURISPRUDENCIA_READ_TIMEOUT', '90')),
)


class JitterRetry(Retry):
    def get_backoff_time(self):
        base = super().get_backoff_time()
        if base <= 0:
            return 0.0
        return min(self.backoff_max, base) + random.uniform(0.0, min(self.backoff_max, base * 0.25))


class RotatingSession(requests.Session):
    def __init__(self):
        super().__init__()
        self._user_agents = itertools.cycle(USER_AGENTS)

    def request(self, method, url, **kwargs):
        headers = dict(kwargs.pop('headers', {}) or {})
        headers.setdefault('Accept', HEADERS['Accept'])
        headers['User-Agent'] = next(self._user_agents)
        kwargs['headers'] = headers
        kwargs.setdefault('timeout', DEFAULT_HTTP_TIMEOUT)
        return super().request(method, url, **kwargs)


def make_session() -> requests.Session:
    if truststore is not None:
        truststore.inject_into_ssl()
    session = RotatingSession()
    retry = JitterRetry(
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


QUERY_STOPWORDS = {
    'a', 'as', 'o', 'os', 'e', 'de', 'da', 'do', 'das', 'dos',
    'em', 'no', 'na', 'nos', 'nas', 'por', 'para', 'com', 'sem',
    'ao', 'aos', 'à', 'às', 'um', 'uma', 'uns', 'umas', 'lei',
}


def _query_terms(query: str) -> list[str]:
    tokens = re.findall(r'\d{1,4}(?:\.\d{1,4})+(?:/\d{2,4})?|[\wÀ-ÿ]+', query.casefold())
    return list(dict.fromkeys(
        token for token in tokens
        if (not token.isdigit() or len(token) >= 4) and token not in QUERY_STOPWORDS
    ))


def _query_score(query: str, *fields: str) -> int:
    terms = _query_terms(query)
    if not terms:
        return 0
    haystack = clean_text(' '.join(fields)).casefold()
    return sum(
        1
        for term in terms
        if re.search(rf'(?<!\w){re.escape(term)}', haystack, re.I)
    )


def _query_matches(query: str, *fields: str) -> bool:
    terms = _query_terms(query)
    if not terms:
        return True
    hits = _query_score(query, *fields)
    required = len(terms) if len(terms) <= 2 else max(2, (len(terms) + 1) // 2)
    return hits >= required


def _query_variants(query: str) -> tuple[str, ...]:
    original = clean_text(query)
    terms = _query_terms(original)
    variants = [original]
    if len(terms) > 1:
        variants.append(' '.join(terms[:2]))
        variants.extend(terms)
    return tuple(dict.fromkeys(item for item in variants if item))


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
    endpoint = 'https://pesquisa.apps.tcu.gov.br/rest/publico/base/acordao-completo'
    search_endpoint = endpoint + '/documentosResumidos'
    detail_endpoint = endpoint + '/documento'

    @staticmethod
    def _rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ('documentos', 'data', 'items', 'acordaos', 'resultados'):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        nested = payload.get('result')
        if isinstance(nested, dict):
            return TCUAdapter._rows(nested)
        return []

    @staticmethod
    def _record(row: dict[str, Any]) -> JurisprudenciaRecord:
        key = _first_value(row, 'KEY', 'key', 'id')
        number = _first_value(row, 'NUMACORDAO', 'numeroAcordao', 'NUMACORDAOINT', 'numeroDecisao')
        year = _first_value(row, 'ANOACORDAO', 'anoAcordao')
        if number and year and '/' not in number:
            number = f'{number}/{year}'
        process = _first_value(
            row,
            'NUMPROCESSO_FORMATADO',
            'NUMPROCESSOFORMATADO',
            'numeroProcessoFormatado',
            'NUMPROCESSO',
            'numeroProcesso',
            'PROCESSO',
            'processo',
        )
        if not process:
            process = key or number
        return JurisprudenciaRecord(
            tribunal='TCU',
            numero_processo=process,
            orgao_julgador=_first_value(row, 'COLEGIADO', 'colegiado', 'CODCOLEGIADO'),
            relator=_first_value(row, 'RELATOR', 'relator'),
            data=_first_value(row, 'DATASESSAO', 'DTSESSAO', 'dataSessao', 'dataSessaoFormatada'),
            ementa=_first_value(row, 'SUMARIO', 'sumario', 'EMENTA', 'ementa', 'TITULO', 'titulo'),
            tese=_first_value(row, 'TESE', 'tese'),
            decisao=_first_value(row, 'ACORDAO', 'acordao'),
            assunto=_as_list(
                _first_value(row, 'AREA', 'area'),
                _first_value(row, 'TEMA', 'tema'),
                _first_value(row, 'SUBTEMA', 'subtema'),
            ),
            url_oficial=_first_value(row, 'URLACORDAO', 'urlAcordao', 'URL', 'url'),
            tipo_decisao=_first_value(row, 'TIPO', 'tipo') or 'Acórdão',
            numero_decisao=number,
            origem='TCU — Pesquisa de Jurisprudência oficial',
            situacao=_first_value(row, 'SITUACAO', 'situacao'),
        )

    def _detail_content(self, key: str) -> str:
        response = self.session.get(
            self.detail_endpoint,
            params={'termo': key},
            timeout=(20, 90),
        )
        response.raise_for_status()
        rows = self._rows(response.json())
        if not rows:
            return ''
        row = rows[0]
        sections = [
            _first_value(row, 'EMENTA', 'ementa', 'SUMARIO', 'sumario'),
            _first_value(row, 'ACORDAO', 'acordao'),
            _first_value(row, 'RELATORIO', 'relatorio', 'RELATÓRIO', 'relatório'),
            _first_value(row, 'VOTO', 'voto'),
            _first_value(row, 'DISPOSITIVO', 'dispositivo'),
        ]
        return '\n\n'.join(item for item in sections if item.strip())

    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        seen: set[str] = set()
        for variant in _query_variants(query):
            response = self.session.get(
                self.search_endpoint,
                params={
                    'termo': variant,
                    'ordenacao': 'DTRELEVANCIA desc, NUMACORDAOINT desc',
                    'quantidade': max(10, min(100, limit * 5)),
                    'inicio': 0,
                },
                timeout=(20, 90),
            )
            response.raise_for_status()
            payload = response.json()
            rows = self._rows(payload)
            if not rows and isinstance(payload, dict) and payload.get('quantidadeEncontrada') not in (None, 0):
                raise RuntimeError('TCU retornou quantidadeEncontrada mas não forneceu a lista documentos no contrato oficial.')
            records: list[JurisprudenciaRecord] = []
            for row in rows:
                record = self._record(row)
                key = _first_value(row, 'KEY', 'key', 'id') or record.document_key
                if key in seen:
                    continue
                seen.add(key)
                if not record.url_oficial:
                    record.url_oficial = f'{self.endpoint}/{key}' if key else self.endpoint
                if with_content and key:
                    try:
                        content = self._detail_content(key)
                        if content:
                            record.inteiro_teor = content
                    except Exception as exc:
                        print(f'aviso: inteiro teor TCU indisponível para {key}: {type(exc).__name__}: {exc}')
                records.append(record)
                if len(records) >= limit:
                    return records
            if records:
                return records
        raise RuntimeError(f'TCU não retornou resultados estruturados para a consulta {query!r}. Contrato da API oficial possivelmente alterado.')


class TCESPAdapter(JurisprudenciaAdapter):
    tribunal = 'TCESP'
    endpoint = 'https://www.tce.sp.gov.br/jurisprudencia/pesquisar'

    def _browser_records(self, variant: str, limit: int, *, detail: bool, with_content: bool, seen: set[str]) -> list[JurisprudenciaRecord]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError('TCESP exige Playwright para o fallback da pesquisa renderizada.') from exc

        params = [
            ('_tipoBuscaTxt', 'on'), ('_tipoDocumento', '1'), ('tipoDocumento', '2'), ('_relator', '1'), ('_auditor', '1'), ('_materia', '1'),
            ('acao', 'Executa'), ('offset', '0'), ('dataAutuacaoFim', ''), ('dataAutuacaoInicio', ''), ('exercicio', ''),
            ('processo', ''), ('quantTrechos', '3'), ('tipoBuscaTxt', 'Documento'), ('txtExp', ''), ('txtNenhPalvs', ''),
            ('txtNumFim', ''), ('txtNumIni', ''), ('txtQqUma', ''), ('txtTdPalvs', variant),
        ]
        url = f'{self.endpoint}?{urlencode(params)}'
        process_pattern = re.compile(r'^[0-9]+ */ *[0-9]+ */ *[0-9]+$')

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled'],
            )
            try:
                page = browser.new_page(locale='pt-BR', viewport={'width': 1440, 'height': 1100})
                relevant_requests: list[str] = []
                page._rag_relevant_requests = relevant_requests
                def capture_request(request):
                    target = request.url.casefold()
                    if any(token in target for token in ('jurisprud', 'pesquis', 'resultado', 'acord', '.json', 'api/')):
                        relevant_requests.append(f'{request.method} {request.url}')
                page.on('request', capture_request)
                page.on(
                    'response',
                    lambda response: relevant_requests.append(
                        f'RESPONSE {response.status} {response.url}'
                    ) if any(
                        token in response.url.casefold()
                        for token in ('jurisprud', 'pesquis', 'resultado', 'acord', '.json', 'api/')
                    ) else None,
                )
                page.goto(url, wait_until='domcontentloaded', timeout=120000)
                try:
                    page.wait_for_function(
                        "() => document.body && document.body.innerText.includes('Foram encontrados')",
                        timeout=15000,
                    )
                except Exception:
                    page.wait_for_timeout(2500)

                soup = BeautifulSoup(page.content(), 'html.parser')
                records: list[JurisprudenciaRecord] = []
                for process_anchor in soup.find_all('a', href=True):
                    process = clean_text(process_anchor.get_text(' ', strip=True))
                    if not process_pattern.fullmatch(process) or process in seen:
                        continue

                    container = process_anchor.find_parent('tr')
                    if container is None:
                        container = process_anchor.find_parent(['li', 'article', 'td', 'div', 'section'])
                    if container is None:
                        container = process_anchor.parent
                    container_text = clean_text(container.get_text(' ', strip=True)) if container is not None else process
                    date_match = re.search(r'[0-9]{2}/[0-9]{2}/[0-9]{4}', container_text)
                    if date_match is None and container is not None:
                        parent = container
                        for _ in range(4):
                            parent = parent.parent
                            if parent is None:
                                break
                            candidate = clean_text(parent.get_text(' ', strip=True))
                            date_match = re.search(r'[0-9]{2}/[0-9]{2}/[0-9]{4}', candidate)
                            if date_match:
                                container = parent
                                container_text = candidate
                                break
                    if date_match is None:
                        continue

                    detail_anchor = next(
                        (
                            item for item in container.find_all('a', href=True)
                            if '/jurisprudencia/exibir' in str(item.get('href'))
                        ),
                        None,
                    )
                    detail_url = (
                        urljoin(page.url, str(detail_anchor.get('href')))
                        if detail_anchor is not None
                        else urljoin(page.url, str(process_anchor.get('href')))
                    )
                    record = JurisprudenciaRecord(
                        tribunal='TCESP',
                        numero_processo=process,
                        data_autuacao=date_match.group(0),
                        ementa=container_text,
                        assunto=[],
                        tipo_decisao='Jurisprudência',
                        origem='TCESP — Pesquisa de Jurisprudência',
                        url_oficial=detail_url,
                    )
                    if detail or with_content:
                        try:
                            detail_text, final, content = _detail_enrichment(
                                self.session,
                                detail_url,
                                with_content=with_content,
                            )
                            record.url_oficial = final
                            record.relator = _label_value(detail_text, ('Relator', 'RELATOR')) or record.relator
                            record.data_publicacao = _label_value(
                                detail_text,
                                ('Data de Publicação', 'Data da Publicação'),
                            ) or record.data_publicacao
                            record.ementa = _extract_ementa(content or detail_text) or record.ementa
                            if with_content and content:
                                record.inteiro_teor = content
                        except Exception as exc:
                            print(f'aviso: detalhe TCESP indisponível para {process}: {type(exc).__name__}: {exc}')
                    seen.add(process)
                    records.append(record)
                    if len(records) >= limit:
                        return records[:limit]
                if not records:
                    print('TCESP browser diagnostic: nenhum processo localizado no DOM.')
                    print('TCESP browser diagnostic: título:', clean_text(page.title()))
                    print(
                        'TCESP browser diagnostic: URLs relevantes:',
                        ' | '.join(
                            str(item)
                            for item in getattr(page, '_rag_relevant_requests', [])[-40:]
                        ),
                    )
                return records[:limit]
            finally:
                browser.close()

    def _search_once(self, variant: str, limit: int, *, detail: bool, with_content: bool, seen: set[str]) -> list[JurisprudenciaRecord]:
        params = [
            ('_tipoBuscaTxt', 'on'), ('_tipoDocumento', '1'), ('tipoDocumento', '2'), ('_relator', '1'), ('_auditor', '1'), ('_materia', '1'),
            ('acao', 'Executa'), ('offset', '0'), ('dataAutuacaoFim', ''), ('dataAutuacaoInicio', ''), ('exercicio', ''),
            ('processo', ''), ('quantTrechos', '3'), ('tipoBuscaTxt', 'Documento'), ('txtExp', ''), ('txtNenhPalvs', ''),
            ('txtNumFim', ''), ('txtNumIni', ''), ('txtQqUma', ''), ('txtTdPalvs', variant),
        ]
        response = self.session.get(self.endpoint, params=params, timeout=(20, 90))
        response.raise_for_status()
        raw_html = getattr(response, 'text', None) or response.content.decode(
            getattr(response, 'encoding', None) or 'utf-8',
            errors='replace',
        )
        soup = BeautifulSoup(raw_html, 'html.parser')
        visible_text = clean_text(soup.get_text(' ', strip=True))
        total_match = re.search(r'Foram encontrados\s+([\d.]+)\s+registros', visible_text, re.I)
        total = int(total_match.group(1).replace('.', '')) if total_match else None
        records: list[JurisprudenciaRecord] = []

        for row in soup.find_all('tr'):
            cells = row.find_all(['th', 'td'], recursive=False)
            if len(cells) < 7:
                continue
            values = [clean_text(cell.get_text(' ', strip=True)) for cell in cells]
            process_index = next(
                (
                    position for position, value in enumerate(values)
                    if re.search(r'\d+\s*/\s*\d+\s*/\s*\d+', value)
                ),
                None,
            )
            if process_index is None:
                continue
            process = values[process_index]
            if process in seen:
                continue
            date_index = next(
                (
                    position for position, value in enumerate(values)
                    if re.search(r'\d{2}/\d{2}/\d{4}', value)
                ),
                None,
            )
            if date_index is None:
                continue
            date_text = values[date_index]

            next_row = row.find_next_sibling('tr')
            trecho_items = []
            if next_row is not None:
                trecho_items = [
                    clean_text(item.get_text(' ', strip=True))
                    for item in next_row.find_all('li')
                    if clean_text(item.get_text(' ', strip=True))
                ]
            trecho = ' '.join(trecho_items)
            if not trecho:
                excerpt_text = clean_text(next_row.get_text(' ', strip=True)) if next_row is not None else ''
                if excerpt_text and 'trechos localizados' not in excerpt_text.casefold():
                    trecho = excerpt_text

            detail_anchor = next(
                (
                    anchor for anchor in row.find_all('a', href=True)
                    if '/jurisprudencia/exibir' in str(anchor.get('href'))
                ),
                None,
            )
            pdf_anchor = next(
                (
                    anchor for anchor in row.find_all('a', href=True)
                    if urlparse(urljoin(response.url, str(anchor.get('href')))).path.casefold().endswith('.pdf')
                ),
                None,
            )
            process_url = (
                urljoin(response.url, str(detail_anchor.get('href')))
                if detail_anchor is not None
                else response.url
            )
            pdf_url = (
                urljoin(response.url, str(pdf_anchor.get('href')))
                if pdf_anchor is not None
                else ''
            )

            fallback_ementa = values[6] if len(values) > 6 else ''
            record = JurisprudenciaRecord(
                tribunal='TCESP',
                numero_processo=process,
                data_autuacao=date_text,
                ementa=trecho or fallback_ementa,
                assunto=_as_list(
                    values[5] if len(values) > 5 else '',
                    values[6] if len(values) > 6 else '',
                ),
                tipo_decisao=values[0] or 'Jurisprudência',
                origem='TCESP — Pesquisa de Jurisprudência',
                url_oficial=process_url,
                partes=_as_list(
                    values[3] if len(values) > 3 else '',
                    values[4] if len(values) > 4 else '',
                ),
            )
            if pdf_url and record.url_oficial == response.url:
                record.url_oficial = pdf_url
            if detail or with_content:
                try:
                    detail_text, final, content = _detail_enrichment(
                        self.session,
                        process_url,
                        with_content=with_content,
                    )
                    record.url_oficial = final
                    record.relator = _label_value(detail_text, ('Relator', 'RELATOR')) or record.relator
                    record.data_publicacao = _label_value(
                        detail_text,
                        ('Data de Publicação', 'Data da Publicação'),
                    ) or record.data_publicacao
                    record.ementa = _extract_ementa(content or detail_text) or record.ementa
                    if with_content and content:
                        record.inteiro_teor = content
                except Exception as exc:
                    print(f'aviso: detalhe TCESP indisponível para {process}: {type(exc).__name__}: {exc}')
            seen.add(process)
            records.append(record)
            if len(records) >= limit:
                return records[:limit]

        if not records:
            process_pattern = re.compile(r'^\d+\s*/\s*\d+\s*/\s*\d+$')
            for anchor in soup.find_all('a', href=True):
                process = clean_text(anchor.get_text(' ', strip=True))
                if not process_pattern.fullmatch(process) or process in seen:
                    continue

                container = anchor.find_parent('tr')
                if container is None:
                    container = anchor.find_parent(['li', 'article', 'td', 'div', 'section'])
                if container is None:
                    container = anchor.parent
                container_text = clean_text(container.get_text(' ', strip=True)) if container is not None else process

                date_match = re.search(r'\d{2}/\d{2}/\d{4}', container_text)
                if date_match is None and container is not None:
                    parent = container
                    for _ in range(4):
                        parent = parent.parent
                        if parent is None:
                            break
                        candidate = clean_text(parent.get_text(' ', strip=True))
                        date_match = re.search(r'\d{2}/\d{2}/\d{4}', candidate)
                        if date_match:
                            container = parent
                            container_text = candidate
                            break
                if date_match is None:
                    continue

                detail_url = urljoin(response.url, str(anchor.get('href') or ''))
                detail_anchor = next(
                    (
                        item for item in container.find_all('a', href=True)
                        if '/jurisprudencia/exibir' in str(item.get('href'))
                    ),
                    None,
                )
                if detail_anchor is not None:
                    detail_url = urljoin(response.url, str(detail_anchor.get('href')))

                date_text = date_match.group(0)
                trecho = ''
                excerpt = container.find_next_sibling()
                if excerpt is not None:
                    trecho_items = [
                        clean_text(item.get_text(' ', strip=True))
                        for item in excerpt.find_all('li')
                        if clean_text(item.get_text(' ', strip=True))
                    ]
                    trecho = ' '.join(trecho_items)
                if not trecho:
                    trecho_match = re.search(
                        r'Trechos localizados no documento:\s*(.+?)(?=\s*(?:\d+\s*/\s*\d+\s*/\s*\d+|$))',
                        container_text,
                        re.I,
                    )
                    if trecho_match:
                        trecho = clean_text(trecho_match.group(1))

                record = JurisprudenciaRecord(
                    tribunal='TCESP',
                    numero_processo=process,
                    data_autuacao=date_text,
                    ementa=trecho or container_text,
                    assunto=[],
                    tipo_decisao='Jurisprudência',
                    origem='TCESP — Pesquisa de Jurisprudência',
                    url_oficial=detail_url,
                )
                seen.add(process)
                records.append(record)
                if len(records) >= limit:
                    return records[:limit]

        browser_error = None
        if total is not None and total > 0 and not records:
            try:
                browser_records = self._browser_records(
                    variant,
                    limit,
                    detail=detail,
                    with_content=with_content,
                    seen=seen,
                )
            except Exception as exc:
                browser_error = exc
                browser_records = []
            if browser_records:
                return browser_records[:limit]
            detail_message = (
                f'; fallback Playwright falhou: {type(browser_error).__name__}: {browser_error}'
                if browser_error
                else '; fallback Playwright não encontrou links de processos'
            )
            raise RuntimeError(
                f'TCESP informou {total} registros para a consulta {variant!r}, '
                'mas não foi possível localizar uma linha de resultado processável'
                f'{detail_message}.'
            )

        if total is None:
            form = soup.find('form')
            form_text = clean_text(form.get_text(' ', strip=True)).casefold() if form is not None else ''
            form_fields = ' '.join(
                str(field.get('name') or '')
                for field in form.find_all(['input', 'textarea'])
            ).casefold() if form is not None else ''
            if form is None or not ('jurisprudência' in form_text or 'pesquisa' in form_text or 'txttdpalvs' in form_fields):
                raise RuntimeError('Estrutura da pesquisa TCESP alterada: resultados e formulário oficial não foram encontrados.')
        return records[:limit]

    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        seen: set[str] = set()
        for variant in _query_variants(query):
            records = self._search_once(
                variant,
                limit,
                detail=detail,
                with_content=with_content,
                seen=seen,
            )
            if records:
                return records[:limit]
        raise RuntimeError(
            f'TCESP não retornou resultados estruturados para {query!r}; '
            'a página oficial pode ter mudado ou a consulta não encontrou registros.'
        )


class STJAdapter(JurisprudenciaAdapter):
    tribunal = 'STJ'
    endpoint = 'https://dadosabertos.web.stj.jus.br'
    max_months_scanned = 6
    orgao_datasets = {
        'CORTE ESPECIAL': 'espelhos-de-acordaos-corte-especial',
        'PRIMEIRA SECAO': 'espelhos-de-acordaos-primeira-secao',
        'PRIMEIRA TURMA': 'espelhos-de-acordaos-primeira-turma',
        'QUARTA TURMA': 'espelhos-de-acordaos-quarta-turma',
        'QUINTA TURMA': 'espelhos-de-acordaos-quinta-turma',
        'SEGUNDA SECAO': 'espelhos-de-acordaos-segunda-secao',
        'SEGUNDA TURMA': 'espelhos-de-acordaos-segunda-turma',
        'SEXTA TURMA': 'espelhos-de-acordaos-sexta-turma',
        'TERCEIRA SECAO': 'espelhos-de-acordaos-terceira-secao',
        'TERCEIRA TURMA': 'espelhos-de-acordaos-terceira-turma',
    }

    def _json(self, url: str, **params: Any) -> dict | list:
        response = self.session.get(url, params=params, timeout=(20, 90))
        response.raise_for_status()
        return response.json()

    def _resources(self, dataset: str) -> list[dict[str, Any]]:
        payload = self._json(
            f'{self.endpoint}/api/3/action/package_show',
            id=dataset,
        )
        if not isinstance(payload, dict) or not payload.get('success'):
            raise RuntimeError(f'STJ pacote CKAN inválido para {dataset}.')
        resources = (payload.get('result') or {}).get('resources') or []
        if not isinstance(resources, list):
            raise RuntimeError(f'STJ pacote CKAN {dataset} não contém resources.')
        candidates = [
            resource for resource in resources
            if isinstance(resource, dict)
            and (
                str(resource.get('format') or '').upper() == 'JSON'
                or str(resource.get('mimetype') or '').lower() == 'application/json'
            )
            and re.match(r'^\d{8}', str(resource.get('name') or ''))
            and resource.get('url')
        ]
        candidates.sort(key=lambda item: str(item.get('name') or ''), reverse=True)
        return candidates[:self.max_months_scanned]

    @staticmethod
    def _match(query: str, row: dict[str, Any]) -> bool:
        digits = ''.join(ch for ch in query if ch.isdigit())
        if digits and len(digits) >= 6:
            if digits in _first_value(row, 'numeroProcesso', 'numeroRegistro', 'numeroDocumento'):
                return True
        fields = [
            _first_value(row, 'ementa'),
            _first_value(row, 'decisao'),
            _first_value(row, 'teseJuridica'),
            _first_value(row, 'informacoesComplementares'),
            _first_value(row, 'descricaoClasse'),
            _first_value(row, 'siglaClasse'),
            _first_value(row, 'nomeOrgaoJulgador'),
            _first_value(row, 'ministroRelator'),
        ]
        return _query_score(query, *fields) > 0

    @staticmethod
    def _record(row: dict[str, Any], dataset: str, resource_url: str) -> JurisprudenciaRecord:
        process = _first_value(row, 'numeroProcesso', 'numeroRegistro', 'numeroDocumento', 'id')
        ementa = _first_value(row, 'ementa')
        decisao = _first_value(row, 'decisao')
        tese = _first_value(row, 'teseJuridica')
        content = '\n\n'.join(item for item in (ementa, decisao, tese) if item)
        return JurisprudenciaRecord(
            tribunal='STJ',
            numero_processo=process,
            orgao_julgador=_first_value(row, 'nomeOrgaoJulgador'),
            relator=_first_value(row, 'ministroRelator'),
            data=_first_value(row, 'dataDecisao'),
            data_publicacao=_first_value(row, 'dataPublicacao'),
            ementa=ementa,
            tese=tese,
            decisao=decisao,
            inteiro_teor=content or None,
            assunto=_as_list(
                _first_value(row, 'siglaClasse'),
                _first_value(row, 'descricaoClasse'),
            ),
            url_oficial=resource_url,
            tipo_decisao=_first_value(row, 'tipoDeDecisao') or 'Acórdão',
            numero_decisao=_first_value(row, 'numeroDocumento'),
            origem='STJ — Dados Abertos / espelhos de acórdãos',
        )

    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        del detail, with_content
        seen: set[str] = set()
        variants = _query_variants(query)
        for variant in variants:
            for dataset in self.orgao_datasets.values():
                resources = self._resources(dataset)
                for resource in resources:
                    payload = self._json(str(resource['url']))
                    if not isinstance(payload, list):
                        continue
                    for row in payload:
                        if not isinstance(row, dict) or not self._match(variant, row):
                            continue
                        record = self._record(row, dataset, str(resource['url']))
                        key = row.get('id') or record.document_key
                        if key in seen:
                            continue
                        seen.add(str(key))
                        return [record] if limit == 1 else self._collect_remaining(
                            variants,
                            dataset,
                            resource,
                            seen,
                            limit,
                            seed=[record],
                        )
        raise RuntimeError(f'STJ não encontrou registros na base de dados abertos para {query!r} nos últimos {self.max_months_scanned} espelhos mensais.' )

    def _collect_remaining(
        self,
        variants: tuple[str, ...],
        first_dataset: str,
        first_resource: dict[str, Any],
        seen: set[str],
        limit: int,
        *,
        seed: list[JurisprudenciaRecord],
    ) -> list[JurisprudenciaRecord]:
        records = list(seed)
        ordered = list(self.orgao_datasets.items())
        start_index = next(
            (i for i, item in enumerate(ordered) if item[1] == first_dataset),
            0,
        )
        for dataset_name in [item[1] for item in ordered[start_index:]]:
            resources = self._resources(dataset_name)
            for resource in resources:
                if dataset_name == first_dataset and resource.get('url') == first_resource.get('url'):
                    continue
                payload = self._json(str(resource['url']))
                if not isinstance(payload, list):
                    continue
                for variant in variants:
                    for row in payload:
                        if not isinstance(row, dict) or not self._match(variant, row):
                            continue
                        record = self._record(row, dataset_name, str(resource['url']))
                        key = str(row.get('id') or record.document_key)
                        if key in seen:
                            continue
                        seen.add(key)
                        records.append(record)
                        if len(records) >= limit:
                            return records
        return records


class STFAdapter(JurisprudenciaAdapter):
    tribunal = 'STF'
    endpoint = 'https://jurisprudencia.stf.jus.br/api/search/search'
    portal = 'https://jurisprudencia.stf.jus.br/pages/search'

    source_fields = [
        'base', 'id', 'dg_unique', 'titulo', 'ministro_facet', 'procedencia_geografica_completo',
        'procedencia_geografica_uf_sigla', 'processo_codigo_completo',
        'processo_classe_processual_unificada_extenso', 'processo_classe_processual_unificada_sigla',
        'processo_numero', 'julgamento_data', 'publicacao_data', 'relator_processo_nome',
        'relator_acordao_nome', 'relator_decisao_nome', 'revisor_processo_nome', 'presidente_nome',
        'orgao_julgador', 'acordao_ata', 'decisao_texto', 'ementa_texto', 'sumula_texto',
        'ramo_direito', 'partes_lista_texto', 'documental_publicacao_lista_texto',
        'documental_legislacao_citada_texto', 'documental_jurisprudencia_citada_texto',
        'documental_indexacao_texto', 'documental_observacao_texto', 'documental_doutrina_texto',
        'documental_tese_texto', 'documental_tese_tema_texto', 'is_repercussao_geral',
        'is_iac', 'is_questao_ordem', 'is_colac', 'inteiro_teor_url', 'inteiro_teor_texto',
    ]

    text_fields = [
        'acordao_ata.plural', 'documental_doutrina_texto.plural', 'documental_indexacao_texto.plural',
        'documental_jurisprudencia_citada_texto.plural', 'documental_legislacao_citada_texto.plural',
        'documental_observacao_texto.plural', 'documental_tese_texto.plural',
        'documental_tese_tema_texto.plural', 'ementa_texto.plural', 'titulo.plural',
        'decisao_texto.plural', 'sumula_texto.plural', 'ramo_direito.plural',
    ]

    def _body(self, query: str, limit: int, *, include_full_text: bool) -> dict[str, Any]:
        fields = list(self.text_fields)
        if include_full_text:
            fields.append('inteiro_teor_texto.plural')
        query_clause = {
            'query_string': {
                'default_operator': 'AND',
                'fields': fields,
                'query': query,
                'fuzziness': 'AUTO:4,7',
            }
        }
        highlight_fields = [
            'ementa_texto', 'sumula_texto', 'materia_noticia', 'titulo_noticia',
            'resumo_noticia', 'conteudo_noticia', 'acordao_ata', 'decisao_texto',
            'documental_tese_texto', 'documental_tese_tema_texto', 'documental_observacao_texto',
            'documental_indexacao_texto', 'documental_legislacao_citada_texto',
            'documental_jurisprudencia_citada_texto', 'documental_doutrina_texto',
            'partes_lista_texto', 'documental_publicacao_lista_texto',
            'documental_acordao_mesmo_sentido_lista_texto', 'documental_decisao_mesmo_sentido_lista_texto',
            'processo_precedente_texto', 'procedencia_geografica_completo',
        ]
        if include_full_text:
            highlight_fields.append('inteiro_teor_texto')
        highlight = {
            'highlight_query': query_clause,
            'number_of_fragments': 64,
            'fragment_size': 300,
            'order': 'score',
            'pre_tags': ['<em>'],
            'post_tags': ['</em>'],
            'fields': {
                name: {
                    'matched_fields': [f'{name}.plural'],
                    'type': 'fvh',
                }
                for name in highlight_fields
            },
        }
        return {
            'query': {
                'bool': {
                    'filter': [
                        {'term': {'base': 'acordaos'}},
                        query_clause,
                    ],
                    'must': [],
                    'should': [],
                    'must_not': [],
                },
            },
            'post_filter': {'bool': {'must': [{'term': {'base': 'acordaos'}}]}},
            '_source': fields,
            'from': 0,
            'size': max(1, min(limit, 250)),
            'track_total_hits': True,
            'sort': [{'_score': 'desc'}, {'julgamento_data': 'desc'}],
            'highlight': highlight,
        }

    def _browser_search(self, query: str, limit: int, *, with_content: bool) -> list[dict[str, Any]]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError('STF exige Playwright para resolver o desafio AWS WAF; instale playwright e o Chromium.') from exc
        headless = os.getenv('RAG_JURISPRUDENCIA_HEADLESS', '1').strip().lower() not in {'0', 'false', 'no'}
        body = self._body(query, limit, include_full_text=with_content)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=headless,
                args=['--disable-blink-features=AutomationControlled'],
            )
            try:
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    locale='pt-BR',
                    viewport={'width': 1440, 'height': 1100},
                )
                page = context.new_page()
                page.goto(self.portal, wait_until='domcontentloaded', timeout=120000)
                token = None
                for _ in range(60):
                    token = next(
                        (cookie['value'] for cookie in context.cookies() if cookie['name'] == 'aws-waf-token'),
                        None,
                    )
                    if token:
                        break
                    page.wait_for_timeout(1000)
                if not token:
                    raise RuntimeError('STF não emitiu aws-waf-token após abrir o portal; desafio do AWS WAF alterado ou indisponível.')
                for attempt in range(2):
                    result = None
                    for evaluate_attempt in range(4):
                        try:
                            result = page.evaluate(
                                """async ({url, body}) => {
                                    const response = await fetch(url, {
                                        method: 'POST',
                                        headers: {
                                            'content-type': 'application/json',
                                            'accept': 'application/json, text/plain, */*'
                                        },
                                        body: JSON.stringify(body)
                                    });
                                    return {
                                        status: response.status,
                                        waf: response.headers.get('x-amzn-waf-action'),
                                        text: await response.text()
                                    };
                                }""",
                                {'url': self.endpoint, 'body': body},
                            )
                            break
                        except Exception as exc:
                            if 'Execution context was destroyed' not in str(exc):
                                raise
                            page.wait_for_timeout(500)
                            if evaluate_attempt == 3:
                                page.reload(wait_until='domcontentloaded', timeout=120000)
                                page.wait_for_timeout(1000)
                                for _ in range(60):
                                    token = next(
                                        (cookie['value'] for cookie in context.cookies() if cookie['name'] == 'aws-waf-token'),
                                        None,
                                    )
                                    if token:
                                        break
                                    page.wait_for_timeout(500)
                                if not token:
                                    raise RuntimeError('STF não recuperou aws-waf-token após navegação durante a consulta.')
                            continue
                    if int(result.get('status') or 0) in {202, 403, 405}:
                        if attempt == 0:
                            page.reload(wait_until='domcontentloaded', timeout=120000)
                            for _ in range(60):
                                token = next(
                                    (cookie['value'] for cookie in context.cookies() if cookie['name'] == 'aws-waf-token'),
                                    None,
                                )
                                if token:
                                    break
                                page.wait_for_timeout(1000)
                            if not token:
                                raise RuntimeError('STF não renovou aws-waf-token após novo desafio do AWS WAF.')
                            continue
                        raise RuntimeError(f'STF AWS WAF rejeitou a consulta HTTP {result.get("status")}: {result.get("waf") or "challenge"}')
                    if int(result.get('status') or 0) < 200 or int(result.get('status') or 0) >= 300:
                        raise RuntimeError(f'STF API respondeu HTTP {result.get("status")}: {str(result.get("text") or "")[:300]}')
                    try:
                        return json.loads(result.get('text') or '{}')
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(f'STF API devolveu resposta não-JSON: {str(result.get("text") or "")[:300]}') from exc
                raise RuntimeError('STF consulta terminou sem resposta válida.')
            finally:
                context.close()
                browser.close()

    @staticmethod
    def _hits(payload: dict[str, Any]) -> list[dict[str, Any]]:
        result = payload.get('result') if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            result = payload if isinstance(payload, dict) else {}
        hits = ((result.get('hits') or {}).get('hits') or [])
        return [hit.get('_source', {}) for hit in hits if isinstance(hit, dict) and isinstance(hit.get('_source'), dict)]

    @staticmethod
    def _record(source: dict[str, Any], doc_id: str = '') -> JurisprudenciaRecord:
        process = _first_value(
            source,
            'processo_codigo_completo',
            'processo_numero',
            'titulo',
        ) or doc_id
        return JurisprudenciaRecord(
            tribunal='STF',
            numero_processo=process,
            orgao_julgador=_first_value(source, 'orgao_julgador'),
            relator=_first_value(source, 'relator_acordao_nome', 'relator_processo_nome', 'relator_decisao_nome'),
            data=_first_value(source, 'julgamento_data'),
            data_publicacao=_first_value(source, 'publicacao_data'),
            ementa=_first_value(source, 'ementa_texto', 'acordao_ata', 'titulo'),
            tese=_first_value(source, 'documental_tese_texto'),
            decisao=_first_value(source, 'decisao_texto'),
            inteiro_teor=_first_value(source, 'inteiro_teor_texto'),
            assunto=_as_list(
                _first_value(source, 'ramo_direito'),
                _first_value(source, 'processo_classe_processual_unificada_extenso'),
            ),
            url_oficial=f'https://jurisprudencia.stf.jus.br/pages/search/{doc_id}/false' if doc_id else 'https://jurisprudencia.stf.jus.br/pages/search',
            tipo_decisao='Acórdão',
            origem='STF — API oficial de jurisprudência',
        )

    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        del detail
        for variant in _query_variants(query):
            payload = self._browser_search(variant, limit, with_content=with_content)
            hits = self._hits(payload)
            if hits:
                records = []
                raw_result = payload.get('result', payload)
                raw_hits = ((raw_result.get('hits') or {}).get('hits') or []) if isinstance(raw_result, dict) else []
                for hit in raw_hits:
                    if not isinstance(hit, dict):
                        continue
                    record = self._record(hit.get('_source') or {}, str(hit.get('_id') or (hit.get('_source') or {}).get('id') or ''))
                    records.append(record)
                    if len(records) >= limit:
                        return records
                if records:
                    return records
        raise RuntimeError(f'STF API oficial não retornou resultados estruturados para {query!r}.')


class TJSPAdapter(JurisprudenciaAdapter):
    tribunal = 'TJSP'
    endpoint = 'https://esaj.tjsp.jus.br/cjsg/consultaCompleta.do'
    result_endpoint = 'https://esaj.tjsp.jus.br/cjsg/resultadoCompleta.do'

    @staticmethod
    def _check_access_block(raw: bytes) -> None:
        soup = BeautifulSoup(raw, 'html.parser')
        visible = clean_text(soup.get_text(' ', strip=True)).casefold()
        patterns = (
            'não sou um robô',
            'nao sou um robo',
            'verificação de segurança',
            'verificacao de seguranca',
            'captcha',
            'recaptcha',
            'hcaptcha',
            'acesso negado',
            'acesso bloqueado',
            'cf-chl-',
        )
        if any(pattern in visible for pattern in patterns):
            raise RuntimeError('TJSP bloqueou a pesquisa por desafio/captcha/antibot; nenhum contorno automático é feito pelo coletor.')

    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        records: list[JurisprudenciaRecord] = []
        seen: set[tuple[str, str]] = set()
        template = {
            'dados.buscaInteiroTeor': '', 'dados.pesquisarComSinonimos': 'S', 'dados.buscaEmenta': '',
            'dados.nuProcOrigem': '', 'dados.nuRegistro': '', 'agenteSelectedEntitiesList': '',
            'contadoragente': '0', 'contadorMaioragente': '0', 'codigoCr': '', 'codigoTr': '', 'nmAgente': '',
            'juizProlatorSelectedEntitiesList': '', 'contadorjuizProlator': '0', 'contadorMaiorjuizProlator': '0',
            'codigoJuizCr': '', 'codigoJuizTr': '', 'nmJuiz': '', 'classesTreeSelection.values': '',
            'classesTreeSelection.text': '', 'assuntosTreeSelection.values': '', 'assuntosTreeSelection.text': '',
            'comarcaSelectedEntitiesList': '', 'contadorcomarca': '1', 'contadorMaiorcomarca': '1',
            'cdComarca': '', 'nmComarca': '', 'secoesTreeSelection.values': '', 'secoesTreeSelection.text': '',
            'dados.dtJulgamentoInicio': '', 'dados.dtJulgamentoFim': '', 'dados.dtRegistroInicio': '',
            'dados.dtRegistroFim': '', 'dados.ordenacao': 'dtPublicacao', 'dados.origensSelecionadas': 'T',
            'tipoDecisaoSelecionados': 'A',
        }
        for variant in _query_variants(query):
            kind, final, raw = fetch(self.session, self.endpoint)
            if kind != 'html': raise RuntimeError('Consulta Completa do TJSP retornou resposta não HTML.')
            self._check_access_block(raw)
            body = dict(template)
            body['dados.buscaInteiroTeor'] = variant
            kind, post_url, post_raw = fetch(self.session, self.result_endpoint, method='POST', data=body)
            if kind != 'html': raise RuntimeError('POST da pesquisa CJSG do TJSP retornou resposta não HTML.')
            self._check_access_block(post_raw)
            post_soup = BeautifulSoup(post_raw, 'html.parser')
            conversation = post_soup.find('input', {'name': 'conversationId'})
            params = {'tipoDeDecisao': 'A', 'pagina': '1'}
            if conversation is not None and conversation.get('value'): params['conversationId'] = str(conversation.get('value'))
            kind, result_url, result_raw = fetch(self.session, 'https://esaj.tjsp.jus.br/cjsg/trocaDePagina.do', params=params, headers={'Referer': self.result_endpoint})
            if kind != 'html': raise RuntimeError('GET inicial da paginação CJSG do TJSP retornou resposta não HTML.')
            self._check_access_block(result_raw)
            soup = BeautifulSoup(result_raw, 'html.parser')
            rows = soup.find_all('tr', class_='fundocinza1')
            if not rows:
                visible = clean_text(soup.get_text(' ', strip=True)).casefold()
                if any(marker in visible for marker in ('nenhum resultado', 'não foram encontrados', 'sem resultados')): continue
                if soup.find('form', id=re.compile(r'form|consulta', re.I)):
                    raise RuntimeError('TJSP permaneceu na página de consulta após o POST; o contrato CJSG pode ter mudado.')
                continue
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 2: continue
                details_table = cells[1].find('table')
                if details_table is None: continue
                process_link = details_table.find('a', class_=re.compile(r'esajLinkLogin.*downloadEmenta', re.I))
                if process_link is None: continue
                process = clean_text(process_link.get_text(' ', strip=True))
                cd_acordao = str(process_link.get('cdacordao') or '').strip()
                if not process or not cd_acordao: continue
                data = {}; ementa = ''
                for detail_row in details_table.find_all('tr', class_='ementaClass2'):
                    strong = detail_row.find('strong')
                    if strong is None: continue
                    label = clean_text(strong.get_text(' ', strip=True))
                    value_text = clean_text(detail_row.get_text(' ', strip=True))
                    if 'ementa:' in label.casefold():
                        ementa = clean_text(re.sub(r'^ementa:\s*', '', value_text, flags=re.I)); continue
                    value = value_text.split(':', 1)[1].strip() if ':' in value_text else value_text
                    key = label.casefold()
                    if 'data de publicação' in key: data['data_publicacao'] = value
                    elif 'órgão julgador' in key or 'orgão julgador' in key: data['orgao_julgador'] = value
                    elif 'relator' in key: data['relator'] = value
                key = (process, cd_acordao)
                if key in seen: continue
                pdf_url = f'https://esaj.tjsp.jus.br/cjsg/getArquivo.do?cdAcordao={cd_acordao}&cdForo=0'
                inteiro = None
                official_url = pdf_url
                if with_content:
                    try:
                        pdf_kind, pdf_final, pdf_raw = fetch(self.session, pdf_url)
                        if pdf_kind == 'pdf': inteiro = pdf_text(pdf_raw); official_url = pdf_final; ementa = _extract_ementa(inteiro) or ementa
                    except Exception as exc:
                        print(f'aviso: inteiro teor TJSP indisponível para {process}: {type(exc).__name__}: {exc}')
                seen.add(key)
                records.append(JurisprudenciaRecord(
                    tribunal='TJSP', numero_processo=process, orgao_julgador=data.get('orgao_julgador', ''),
                    relator=data.get('relator', ''), data_publicacao=data.get('data_publicacao', ''),
                    ementa=ementa or clean_text(row.get_text(' ', strip=True))[:4000], url_oficial=official_url,
                    tipo_decisao='Acórdão', origem='TJSP — e-SAJ CJSG oficial', inteiro_teor=inteiro,
                ))
                if len(records) >= limit: return records[:limit]
        raise RuntimeError(f'TJSP não retornou registros estruturados para {query!r}.')

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
        'tjsp': TJSPAdapter(session),
    }


def save_record(record: JurisprudenciaRecord, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    record.validate()
    record.retrieved_at = record.retrieved_at or datetime.now(timezone.utc).isoformat()
    record.version_sha256 = record.version_sha256 or record.calculate_version_sha256()
    is_sumula = str(record.tipo_documento or '').strip().casefold() == 'sumula' or str(record.tipo_decisao or '').strip().casefold() == 'súmula'
    source_id = {
        'TCU': 'tcu-jurisprudencia',
        'TCESP': 'tcesp-jurisprudencia',
        'STJ': 'stj-jurisprudencia-estruturada',
        'STF': 'stf-jurisprudencia-estruturada',
        'TJSP': 'tjsp-jurisprudencia-estruturada',
    }.get(record.tribunal, f'{record.tribunal.lower()}-jurisprudencia')
    if is_sumula:
        source_id = f'{record.tribunal.lower()}-sumulas'
    basename = f'jurisprudencia__{record.tribunal.lower()}__{record.document_key}__{record.version_sha256[:10]}'
    text_path = output_dir / f'{basename}.txt'
    json_path = output_dir / f'{basename}.json'
    text_path.write_text(record.to_index_text(), encoding='utf-8')
    metadata = {
        **record.to_dict(),
        'document_id': basename,
        'source_id': source_id,
        'parent_source_id': source_id,
        'source_role': 'jurisprudencia_controle' if record.tribunal in {'TCU', 'TCESP'} else 'jurisprudencia',
        'jurisdicao': 'estadual_sp' if record.tribunal in {'TCESP', 'TJSP'} else 'federal',
        'esfera': 'estadual' if record.tribunal in {'TCESP', 'TJSP'} else 'federal',
        'orgao': record.tribunal,
        'tribunal': record.tribunal,
        'tipo_documento': 'sumula' if is_sumula else 'jurisprudencia',
        'authority_level': 2,
        'normative_rank': None,
        'status': (
            'cancelada' if is_sumula and 'cancel' in str(record.situacao or '').casefold()
            else 'revogada' if is_sumula and 'revog' in str(record.situacao or '').casefold()
            else 'vigente' if is_sumula else 'jurisprudencia'
        ),
        'revogado': bool(is_sumula and 'revog' in str(record.situacao or '').casefold()),
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
