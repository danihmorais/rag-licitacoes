from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from scripts.sources import SOURCES
except ModuleNotFoundError:
    from sources import SOURCES

SOURCES = [dict(item) for item in SOURCES]
for item in SOURCES:
    if item.get('id') == 'sp-lei6544':
        item['status'] = 'historico'

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'db' / 'source_cache'
HEADERS = {
    'User-Agent': 'rag-licitacoes-source-sync/3.0 (+https://github.com/danihmorais/rag-licitacoes)',
    'Accept': 'text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8',
}
LEGAL_RE = re.compile(
    r'\b(?:Art\.?|Artigo|CAPÍTULO|TÍTULO|SEÇÃO|SUBSEÇÃO|ANEXO|S[ÚU]MULA|LEI|DECRETO|DECRETO-LEI|RESOLUÇÃO|PORTARIA|INSTRUÇÃO\s+NORMATIVA|CONSTITUIÇÃO)\b',
    re.I,
)
NOISE = {'[Input]', '[Button: Pesquisar]', 'expand_more', 'collapse'}
NORMATIVE_HEADER_RE = re.compile(
    r'(?im)^\s*(?:LEI\s+COMPLEMENTAR|LEI|DECRETO-LEI|DECRETO|PORTARIA|RESOLU[ÇC][ÃA]O|INSTRU[ÇC][ÃA]O\s+NORMATIVA|CONSTITUI[ÇC][ÃÃ]O)\b'
)
ARTICLE_RE = re.compile(r'(?im)\bArt(?:igo)?\.?\s+\d+[A-Za-zºª\-]*\b')
RETIRED_SOURCE_IDS = {
    'tcu', 'tcesp', 'stj-jurisprudencia', 'stj-teses', 'stj-repetitivos-iacs',
    'stj-sumulas-anotadas', 'stj-legislacao-aplicada', 'stj-informativos',
    'stf-repercussao-geral', 'stf-teses-rg', 'stf-tesauro', 'stf-jurisprudencia',
    'tjsp-jurisprudencia', 'tjsp-saj-jurisprudencia', 'tcu-dados-jurisprudencia',
    'tcu-jurisprudencia-pesquisa',
}


def make_session():
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.8,
        status_forcelist=(408, 429, 500, 502, 503, 504),
        allowed_methods=frozenset({'GET', 'HEAD'}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    session.headers.update(HEADERS)
    return session


def clean_html(raw):
    soup = BeautifulSoup(raw, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'nav', 'header', 'footer', 'form', 'aside']):
        tag.decompose()
    for tag in soup.find_all(style=True):
        if 'line-through' in tag.get('style', '').replace(' ', '').lower():
            tag.decompose()
    root = soup.find('main') or soup.find(id=re.compile(r'conteudo|content|corpo', re.I)) or soup.body or soup
    lines = []
    for line in root.get_text('\n', strip=True).splitlines():
        line = html.unescape(re.sub(r'\s+', ' ', line)).strip()
        if line and line not in NOISE and len(line) <= 10000:
            lines.append(line)
    return '\n'.join(lines)


def pdf_text(data):
    CACHE.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.sync_', suffix='.pdf', dir=CACHE, delete=False) as handle:
            handle.write(data)
            temp_name = handle.name
        return '\n\f\n'.join(page.extract_text() or '' for page in PdfReader(temp_name).pages)
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def _decode_response(raw, final, content_type=''):
    is_pdf = (
        'application/pdf' in content_type.lower()
        or final.lower().split('?', 1)[0].endswith('.pdf')
        or raw.startswith(b'%PDF')
    )
    if is_pdf:
        return 'pdf', final, raw, pdf_text(raw)
    return 'html', final, raw, clean_html(raw)


def _fetch_with_wget(url):
    if shutil.which('wget') is None:
        raise RuntimeError('wget não está instalado no sistema.')
    result = subprocess.run(
        [
            'wget',
            '--quiet',
            '--server-response',
            '--max-redirect=10',
            '--timeout=20',
            '--tries=2',
            '--user-agent=Mozilla/5.0',
            '--header=Accept: text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8',
            '--output-document=-',
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=50,
    )
    if result.returncode != 0:
        detail = result.stderr.decode('utf-8', errors='replace').strip().splitlines()
        raise ConnectionError(detail[-1] if detail else f'wget falhou com código {result.returncode}')
    raw = result.stdout
    final = url
    return _decode_response(raw, final)


def fetch(session, url):
    try:
        response = session.get(url, timeout=(8, 20), allow_redirects=True)
        response.raise_for_status()
        return _decode_response(
            response.content,
            response.url,
            response.headers.get('content-type', ''),
        )
    except (requests.RequestException, ConnectionError, TimeoutError) as request_error:
        try:
            return _fetch_with_wget(url)
        except Exception as wget_error:
            raise ConnectionError(
                f'requests falhou: {request_error}; wget falhou: {wget_error}'
            ) from wget_error


def _compact(value):
    return re.sub(r'[^0-9A-Za-z]', '', str(value or '')).casefold()


def _expected_normative_number(source):
    if source.get('tipo_documento') in {'constituicao', 'constituicao_estadual'}:
        return None
    title = str(source.get('title') or '')
    match = re.search(r'\b(?:n[ºo]?\s*)?((?:\d{1,4}\.)*\d{1,4})(?:/\d{2,4})?\b', title)
    return match.group(1) if match else None


def _source_urls(source):
    urls = [*source.get('urls', ()), *source.get('fallback_urls', ())]
    return list(dict.fromkeys(str(url).strip() for url in urls if str(url).strip()))


def _substantive_lines(text):
    return [line.strip() for line in text.splitlines() if len(line.strip()) >= 40]


def _looks_like_shell(text):
    lowered = text.casefold()
    shell_hits = sum(
        term in lowered
        for term in ('enable javascript', 'habilite javascript', 'carregando', 'aguarde', '[input]', '[button')
    )
    return shell_hits >= 2 and len(_substantive_lines(text)) <= 8


def validate(source, text, *, linked=False, final_url=None, document_title=None):
    stripped = text.strip()
    if source.get('index_only') and not linked:
        if not stripped:
            raise RuntimeError('conteúdo vazio')
        if _looks_like_shell(stripped):
            raise RuntimeError('conteúdo aparenta ser apenas casca de portal/SPA')
        return
    if len(stripped) < 800:
        raise RuntimeError(f'conteúdo insuficiente: {len(stripped)} caracteres')
    substantive = _substantive_lines(stripped)
    if len(substantive) < 6:
        raise RuntimeError(f'conteúdo sem densidade substantiva suficiente: {len(substantive)} linhas')
    if _looks_like_shell(stripped):
        raise RuntimeError('conteúdo aparenta ser apenas casca de portal/SPA')

    role = source.get('source_role')
    if role == 'norma':
        if not NORMATIVE_HEADER_RE.search(stripped) and not LEGAL_RE.search(stripped):
            raise RuntimeError('conteúdo não apresenta estrutura normativa reconhecível')
        expected = _expected_normative_number(source)
        if expected and _compact(expected) not in _compact(stripped[:30000]):
            url_identity = _compact(final_url or '')
            allowed_url_identity = _compact(expected) in url_identity
            if not allowed_url_identity:
                raise RuntimeError(f'identidade normativa ausente: {expected}')
        if source.get('tipo_documento') not in {'portal_oficial'} and len(ARTICLE_RE.findall(stripped)) < 1:
            raise RuntimeError('conteúdo normativo sem artigo/dispositivo reconhecível')
    elif role == 'orientacao_oficial' and not (source.get('index_only') and linked):
        markers = ('parecer', 'manual', 'guia', 'orientação', 'orientacao', 'modelo', 'boletim')
        identity = f"{document_title or ''} {final_url or ''}".casefold()
        if not any(marker in stripped.casefold() or marker in identity for marker in markers):
            raise RuntimeError('conteúdo de orientação oficial sem marcador documental reconhecível')


def slug(value):
    value = re.sub(r'[^0-9A-Za-zÀ-ÿ]+', '_', value, flags=re.UNICODE).strip('_')
    return re.sub(r'_+', '_', value)[:120] or 'documento'


def normalized_pattern(value):
    previous = None
    while value != previous and '\\\\' in value:
        previous = value
        value = value.replace('\\\\', '\\')
    return value


def discover_links(raw_html, base_url, source):
    soup = BeautifulSoup(raw_html, 'html.parser')
    patterns = [re.compile(normalized_pattern(p), re.I) for p in source.get('follow_patterns', ())]
    exclude_patterns = [re.compile(normalized_pattern(p), re.I) for p in source.get('exclude_patterns', ())]
    host = urlparse(base_url).netloc.lower()
    out = []
    seen = set()
    for anchor in soup.find_all('a', href=True):
        absolute = urljoin(base_url, str(anchor['href']).strip()).split('#', 1)[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in {'http', 'https'} or (not source.get('allow_cross_host') and parsed.netloc.lower() != host):
            continue
        label = anchor.get_text(' ', strip=True)
        if exclude_patterns and any(pattern.search(absolute) or pattern.search(label) for pattern in exclude_patterns):
            continue
        if patterns and not any(pattern.search(absolute) or pattern.search(label) for pattern in patterns):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append((absolute, label or absolute.rsplit('/', 1)[-1]))
        if len(out) >= int(source.get('max_follow', 12)):
            break
    return out


def _atomic_write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _atomic_write_json(path, value):
    _atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def write_cache(source, final, kind, raw, text, document_id, title, extra_meta=None):
    CACHE.mkdir(parents=True, exist_ok=True)
    base = slug(document_id)
    _atomic_write_text(CACHE / f'{base}.txt', text.strip() + '\n')
    meta = {
        'source_id': source['id'],
        'document_id': base,
        'parent_source_id': source['id'],
        'title': title,
        'jurisdicao': source.get('jurisdicao'),
        'esfera': source.get('esfera'),
        'orgao': source.get('orgao'),
        'tribunal': source.get('tribunal'),
        'tipo_documento': source.get('tipo_documento'),
        'source_role': source.get('source_role', 'desconhecido'),
        'authority_level': source.get('authority_level'),
        'normative_rank': source.get('normative_rank'),
        'ramo_direito': source.get('ramo_direito'),
        'status': source.get('status') or 'orientativo',
        'revogado': source.get('revogado', False),
        'data_publicacao': source.get('data_publicacao'),
        'data_vigencia': source.get('data_vigencia'),
        'effective_from': source.get('effective_from'),
        'effective_to': source.get('effective_to'),
        'norma_alteradora': source.get('norma_alteradora'),
        'fonte_oficial': final,
        'fonte_host': urlparse(final).netloc,
        'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'data_versao': source.get('data_versao'),
        'source_kind': kind,
        'sha256': hashlib.sha256(raw).hexdigest(),
    }
    if extra_meta:
        meta.update({key: value for key, value in extra_meta.items() if value not in (None, '')})
    _atomic_write_json(CACHE / f'{base}.json', meta)


def cleanup_source_cache(source_id, keep_document_ids):
    removed = 0
    keep = {str(item) for item in keep_document_ids}
    if not CACHE.exists():
        return removed
    for sidecar in CACHE.glob('*.json'):
        try:
            meta = json.loads(sidecar.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if meta.get('parent_source_id') != source_id or str(meta.get('document_id') or '') in keep:
            continue
        sidecar.unlink(missing_ok=True)
        sidecar.with_suffix('.txt').unlink(missing_ok=True)
        removed += 1
    return removed



def purge_retired_source_cache():
    removed = 0
    if not CACHE.exists():
        return removed
    for sidecar in CACHE.glob('*.json'):
        try:
            meta = json.loads(sidecar.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if meta.get('source_id') not in RETIRED_SOURCE_IDS and meta.get('parent_source_id') not in RETIRED_SOURCE_IDS:
            continue
        sidecar.unlink(missing_ok=True)
        sidecar.with_suffix('.txt').unlink(missing_ok=True)
        removed += 1
    return removed




WEB_MONTHS = {
    'janeiro': 1, 'fevereiro': 2, 'março': 3, 'marco': 3, 'abril': 4,
    'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8, 'setembro': 9,
    'outubro': 10, 'novembro': 11, 'dezembro': 12,
    'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
    'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12,
}

WEB_EXCLUDED_PATH_PARTS = (
    '/page/', '/category/', '/tag/', '/autor/', '/author/', '/feed',
    '/wp-json/', '/wp-admin/', '/wp-content/', '/comments/', '/comment-page-',
    '/buscar', '/search', '/login', '/cadastro', '/sobre', '/contato',
    '/politica-de-privacidade', '/termos', '/caderno/',
)

WEB_ADMIN_POSITIVE = (
    'direito administrativo', 'direito público', 'direito publico',
    'licitação', 'licitações', 'licitação pública', 'licitações públicas',
    'contrato administrativo', 'contratos administrativos',
    'contratação pública', 'contratações públicas',
    'administração pública', 'poder público', 'serviço público',
    'processo administrativo', 'ato administrativo',
    'improbidade administrativa', 'responsabilidade do estado',
    'compras públicas', 'pregão', 'edital', 'inexigibilidade',
    'dispensa de licitação', 'lei 14.133', 'lei 13.303',
    'tribunal de contas', 'tcu', 'tcesp', 'controladoria',
    'transparência pública', 'concessão', 'concessões',
    'parceria público-privada', 'parcerias público-privadas', 'ppp',
    'regulação', 'regulação pública', 'licitações e contratos',
)

WEB_ADMIN_EXCLUDE = (
    'direito de família', 'divórcio', 'direito trabalhista',
    'direito do trabalho', 'direito previdenciário', 'direito penal',
    'direito empresarial', 'direito societário', 'direito do consumidor',
    'propriedade intelectual',
)

def _parse_web_date(value):
    if not value:
        return None
    raw = html.unescape(str(value)).strip()
    raw = re.sub(r'\s+', ' ', raw)
    iso = raw.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        pass
    match = re.search(r'\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b', raw)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            return None
    match = re.search(
        r'\b(\d{1,2})\s*(?:de\s*)?([A-Za-zÀ-ÿ]+)\s*(?:de\s*)?(20\d{2})\b',
        raw, re.I,
    )
    if match:
        month = WEB_MONTHS.get(match.group(2).casefold())
        if month:
            try:
                return date(int(match.group(3)), month, int(match.group(1)))
            except ValueError:
                return None
    match = re.search(r'\b(\d{1,2})[./-]([A-Za-z]{3})[./-](20\d{2})\b', raw, re.I)
    if match:
        month = WEB_MONTHS.get(match.group(2).casefold())
        if month:
            try:
                return date(int(match.group(3)), month, int(match.group(1)))
            except ValueError:
                return None
    match = re.search(r'\b(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\b', raw)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    match = re.search(r'\b(20\d{2})[-/]([A-Za-zÀ-ÿ]{3,12})[-/](\d{1,2})\b', raw, re.I)
    if match:
        month = WEB_MONTHS.get(match.group(2).casefold())
        if month:
            try:
                return date(int(match.group(1)), month, int(match.group(3)))
            except ValueError:
                return None
    return None


def _jsonld_objects(soup):
    def walk(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)
    for script in soup.find_all('script', type=lambda value: value and 'ld+json' in value):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        yield from walk(parsed)


def _first_meta(soup, *names):
    wanted = {name.casefold() for name in names}
    for tag in soup.find_all('meta'):
        key = str(tag.get('property') or tag.get('name') or tag.get('itemprop') or '').casefold()
        if key in wanted and tag.get('content'):
            return str(tag.get('content')).strip()
    return None


def _article_text_node(soup):
    for selector in (
        '[itemprop="articleBody"]',
        'article',
        '.entry-content',
        '.post-content',
        '.article-content',
        '.article-body',
        '.post__content',
        'main',
    ):
        node = soup.select_one(selector)
        if node:
            text = node.get_text('\n', strip=True)
            if len(text) >= 800:
                return node
    return soup.body or soup


def extract_web_article(raw_html, final_url):
    soup = BeautifulSoup(raw_html, 'html.parser')
    jsonld = list(_jsonld_objects(soup))
    for tag in soup(['script', 'style', 'noscript', 'nav', 'header', 'footer', 'form', 'aside', 'iframe']):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(r'(share|social|related|coment|comment|advert|banner|cookie|newsletter|menu|breadcrumb|sidebar)', re.I)):
        tag.decompose()
    title = None
    body_from_jsonld = None
    published = None
    author = None
    section = None
    keywords = None
    for item in jsonld:
        title = title or item.get('headline') or item.get('name')
        body_from_jsonld = body_from_jsonld or item.get('articleBody')
        published = published or item.get('datePublished') or item.get('dateCreated')
        author_value = item.get('author')
        if isinstance(author_value, dict):
            author_value = author_value.get('name')
        elif isinstance(author_value, list):
            author_value = ', '.join(
                str(value.get('name') if isinstance(value, dict) else value)
                for value in author_value
                if value
            )
        author = author or author_value
        section = section or item.get('articleSection')
        keyword_value = item.get('keywords')
        if isinstance(keyword_value, list):
            keyword_value = ', '.join(str(value) for value in keyword_value)
        keywords = keywords or keyword_value

    title = title or _first_meta(soup, 'og:title', 'twitter:title') or (soup.find('h1').get_text(' ', strip=True) if soup.find('h1') else None)
    published = (
        published
        or _first_meta(soup, 'article:published_time', 'datePublished', 'date', 'pubdate')
        or next((tag.get('datetime') for tag in soup.find_all('time') if tag.get('datetime')), None)
    )
    if not published:
        published = final_url
    author = author or _first_meta(soup, 'author', 'article:author')
    section = section or _first_meta(soup, 'article:section', 'section')
    keywords = keywords or _first_meta(soup, 'keywords', 'article:tag')
    if not published:
        visible = soup.get_text(' ', strip=True)
        label_match = re.search(
            r'(?:publicad[oa]|publicação|publicacao|published)(?:\s+em|\s*:)\s+(.{0,80})',
            visible[:5000],
            re.I,
        )
        published = label_match.group(1) if label_match else visible[:2000]

    article_node = _article_text_node(soup)
    body = article_node.get_text('\n', strip=True) if article_node else ''
    if len(body) < 800 and body_from_jsonld:
        body = str(body_from_jsonld).strip()
    if title and title.casefold() not in body.casefold():
        body = f'{title}\n\n{body}'
    published_date = _parse_web_date(published)
    return {
        'title': html.unescape(str(title or '').strip()),
        'date_publicacao': published_date,
        'autor': html.unescape(str(author or '').strip()),
        'secao': html.unescape(str(section or '').strip()),
        'palavras_chave': html.unescape(str(keywords or '').strip()),
        'texto': body.strip(),
        'url': final_url,
    }


def _is_web_article_url(source, url):
    parsed = urlparse(url)
    path = unquote(parsed.path or '/')
    low = path.casefold()
    if parsed.scheme not in {'http', 'https'}:
        return False
    if any(part in low for part in WEB_EXCLUDED_PATH_PARTS):
        return False
    source_id = source.get('id')
    if source_id == 'web-migalhas':
        return bool(re.match(r'^/(?:depeso|quentes|colunas)/[^/]+(?:/|$)', low))
    if source_id == 'web-conjur':
        return bool(re.search(r'/20\d{2}-(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)-\d{2}/', low))
    if source_id == 'web-conlicitacao':
        return low.startswith('/blog/') and not low.startswith('/blog/page/')
    if source_id == 'web-nova-lei-licitacao':
        return bool(re.search(r'/20\d{2}/\d{1,2}/\d{1,2}/', low))
    return path.rstrip('/') not in {'', '/'} and not low.endswith(('.xml', '.rss', '.txt'))


def _web_link_candidates(raw_html, base_url, source):
    soup = BeautifulSoup(raw_html, 'html.parser')
    base_host = urlparse(base_url).netloc.lower().removeprefix('www.')
    candidates = []
    next_urls = []
    seen = set()
    for anchor in soup.find_all('a', href=True):
        absolute = urljoin(base_url, str(anchor['href']).strip()).split('#', 1)[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in {'http', 'https'}:
            continue
        if parsed.netloc.lower().removeprefix('www.') != base_host:
            continue
        label = anchor.get_text(' ', strip=True)
        rel = ' '.join(anchor.get('rel', [])) if anchor.get('rel') else ''
        label_norm = re.sub(r'\s+', ' ', label).strip().casefold()
        is_next = (
            rel.casefold() == 'next'
            or bool(re.search(r'\b(?:próxima|proxima|seguinte|next)\s+p(?:á|a)gina\b', label, re.I))
            or label_norm in {'próxima', 'proxima', 'seguinte', 'next', 'older posts', 'older', 'mais antigas'}
            or bool(re.search(r'(?:/page/\d+/?$|[?&]pagina=\d+\b|/pagina/\d+/?$)', urlparse(absolute).path + ('?' + urlparse(absolute).query if urlparse(absolute).query else ''), re.I))
        )
        if is_next:
            next_urls.append(absolute)
            continue
        if _is_web_article_url(source, absolute) and absolute not in seen:
            seen.add(absolute)
            candidates.append(absolute)
    return candidates, next_urls


def _sitemap_urls(raw):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    return [
        loc.text.strip()
        for loc in root.iter()
        if loc.tag.rsplit('}', 1)[-1] == 'loc' and loc.text and loc.text.strip()
    ]


def _rss_article_links(raw, source):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    links = []
    for item in root.iter():
        if item.tag.rsplit('}', 1)[-1] not in {'item', 'entry'}:
            continue
        values = []
        for child in list(item):
            tag = child.tag.rsplit('}', 1)[-1]
            if tag == 'link':
                href = child.get('href') or (child.text or '').strip()
                if href:
                    values.append(href)
        for href in values:
            if _is_web_article_url(source, href):
                links.append(href)
    return list(dict.fromkeys(links))


def _web_topic_matches(source, article):
    if source.get('web_article_scope') == 'dedicated_licitacao':
        return True
    haystack = ' '.join(
        str(article.get(key) or '')
        for key in ('title', 'secao', 'palavras_chave', 'texto')
    ).casefold()
    title_meta = ' '.join(
        str(article.get(key) or '')
        for key in ('title', 'secao', 'palavras_chave')
    ).casefold()
    positive = {term for term in source.get('topic_include_terms', ()) if term.casefold() in haystack}
    title_positive = {term for term in source.get('topic_include_terms', ()) if term.casefold() in title_meta}
    excluded = {term for term in source.get('topic_exclude_terms', WEB_ADMIN_EXCLUDE) if term.casefold() in title_meta}
    if title_positive:
        return True
    if 'administrativo' in title_meta or 'direito público' in title_meta or 'direito publico' in title_meta:
        return True
    if len(positive) >= 2 and not excluded:
        return True
    return False


def _article_cache_text(source, article):
    parts = [
        f'FONTE: {source["orgao"]}',
        f'TÍTULO: {article["title"]}',
        f'DATA_PUBLICACAO: {article["date_publicacao"].isoformat()}',
    ]
    if article.get('autor'):
        parts.append(f'AUTOR: {article["autor"]}')
    if article.get('secao'):
        parts.append(f'SECAO: {article["secao"]}')
    if article.get('palavras_chave'):
        parts.append(f'PALAVRAS_CHAVE: {article["palavras_chave"]}')
    parts.append(f'URL: {article["url"]}')
    parts.extend(['', article['texto']])
    return '\n'.join(parts).strip()


def sync_web_articles(session, source, check=False):
    target = int(source.get('max_documents', 250))
    min_date = _parse_web_date(source.get('min_publication_date')) or date(2021, 1, 1)
    candidates = []
    seen = set()
    page_queue = list(source.get('urls', ()))
    visited_pages = set()
    successful_discoveries = 0
    max_pages = int(source.get('discovery_max_pages', 80))

    while page_queue and len(visited_pages) < max_pages:
        page_url = page_queue.pop(0)
        if page_url in visited_pages:
            continue
        visited_pages.add(page_url)
        try:
            kind, final, raw, text = fetch(session, page_url)
            successful_discoveries += 1
        except Exception as exc:
            print(f'  aviso: descoberta {page_url} falhou: {type(exc).__name__}: {exc}')
            continue
        if raw.lstrip().startswith(b'<?xml') or raw.lstrip().startswith(b'<'):
            rss_links = _rss_article_links(raw, source)
            if rss_links:
                for link in rss_links:
                    if link not in seen:
                        seen.add(link)
                        candidates.append(link)
                continue
            sitemap_links = _sitemap_urls(raw)
            if sitemap_links:
                for link in sitemap_links[:50]:
                    if link not in page_queue and link not in visited_pages:
                        page_queue.append(link)
                continue
        links, next_urls = _web_link_candidates(raw, final, source)
        for link in links:
            if link not in seen:
                seen.add(link)
                candidates.append(link)
        for next_url in next_urls:
            if next_url not in visited_pages and next_url not in page_queue:
                page_queue.append(next_url)

    if len(candidates) < target:
        for sitemap_url in source.get('sitemap_urls', ()):
            if len(candidates) >= target:
                break
            try:
                kind, final, raw, text = fetch(session, sitemap_url)
                successful_discoveries += 1
            except Exception as exc:
                print(f'  aviso: sitemap {sitemap_url} falhou: {type(exc).__name__}: {exc}')
                continue
            sitemap_links = _sitemap_urls(raw)
            if not sitemap_links:
                continue
            nested = []
            for link in sitemap_links:
                if re.search(r'\.(?:xml|xml\.gz)    last = ''
    for url in _source_urls(source):
        try:
            kind, final, raw, text = fetch(session, url)
            validate(source, text, linked=False, final_url=final)
            seen_ids = {slug(source['id'])}
            if not check and not source.get('index_only'):
                write_cache(source, final, kind, raw, text, source['id'], source['title'])
            linked_ok = linked_total = 0
            link_failures = False
            if follow_links and source.get('follow_links') and kind == 'html':
                for link_url, link_title in discover_links(raw, final, source):
                    linked_total += 1
                    try:
                        linked_kind, linked_final, linked_raw, linked_text = fetch(session, link_url)
                        validate(source, linked_text, linked=True, final_url=linked_final, document_title=link_title)
                        linked_ok += 1
                        document_id = (
                            f"{source['id']}__{slug(link_title)}__{hashlib.sha1(linked_final.encode()).hexdigest()[:10]}"
                        )
                        seen_ids.add(slug(document_id))
                        if not check:
                            write_cache(source, linked_final, linked_kind, linked_raw, linked_text, document_id, link_title)
                    except Exception as exc:
                        link_failures = True
                        print(f'  aviso: link {link_url} falhou: {type(exc).__name__}: {exc}; cache anterior preservado')
            if source.get('index_only'):
                seen_ids.discard(slug(source['id']))
            removed = cleanup_source_cache(source['id'], seen_ids) if not check and not link_failures else 0
            suffix = f', PDFs linkados {linked_ok}/{linked_total}' if linked_total else ''
            if link_failures:
                suffix += ', cache obsoleto preservado por falha de link'
            elif removed:
                suffix += f', cache obsoleto removido {removed}'
            return True, f'OK {source["id"]} via {final} ({kind}, {len(text)} chars{suffix})', seen_ids
        except Exception as exc:
            last = f'{type(exc).__name__}: {exc}'
    return False, f'FAIL {source["id"]}: {last}', set()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--required-only', action='store_true')
    parser.add_argument('--legislation-only', action='store_true')
    parser.add_argument('--strict', action='store_true')
    parser.add_argument('--no-follow-links', action='store_true')
    args = parser.parse_args()
    sources = [
        s for s in SOURCES
        if (not args.required_only or s.get('required'))
        and (
            not args.legislation_only
            or (s.get('source_role') == 'norma' and not s.get('index_only'))
        )
    ]
    session = make_session()
    if not args.check:
        removed_retired = purge_retired_source_cache()
        if removed_retired:
            print(f'Fontes jurisprudenciais legadas removidas do cache: {removed_retired}')
    failures = []
    ok = 0
    for index, source in enumerate(sources, 1):
        print(f'[{index}/{len(sources)}] {source["id"]}', flush=True)
        if source.get('source_type') == 'web_articles':
            good, message, _ = sync_web_articles(session, source, check=args.check)
        else:
            good, message, _ = sync_one(session, source, check=args.check, follow_links=not args.no_follow_links and not args.check)
        print(message, flush=True)
        ok += int(good)
        if not good:
            failures.append(source['id'])
    print(f'Fontes: {ok}/{len(sources)} OK')
    if failures:
        print('Falhas:', ', '.join(failures))
    strict_failures = []
    if args.strict:
        strict_failures = [
            source['id']
            for source in sources
            if source['id'] in failures
            and source.get('source_role') == 'norma'
            and not source.get('index_only')
        ]
    if failures and args.required_only:
        return 1
    if strict_failures:
        print('Falhas legislativas bloqueantes:', ', '.join(strict_failures))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main()), urlparse(link).path.casefold()):
                    nested.append(link)
                elif _is_web_article_url(source, link):
                    if link not in seen:
                        seen.add(link)
                        candidates.append(link)
            for nested_url in nested[:30]:
                if len(candidates) >= target * 6:
                    break
                try:
                    _, _, nested_raw, _ = fetch(session, nested_url)
                except Exception:
                    continue
                for link in _sitemap_urls(nested_raw):
                    if _is_web_article_url(source, link) and link not in seen:
                        seen.add(link)
                        candidates.append(link)
                        if len(candidates) >= target * 6:
                            break

    accepted = []
    fetched = 0
    seen_articles = set()
    old_count = 0
    for candidate in candidates:
        if len(accepted) >= target or fetched >= target * 6:
            break
        fetched += 1
        try:
            kind, final, raw, text = fetch(session, candidate)
            article = extract_web_article(raw, final)
            if not article['title'] or len(article['texto']) < 800 or not article['date_publicacao']:
                continue
            if article['date_publicacao'] < min_date:
                continue
            if not _web_topic_matches(source, article):
                continue
            article_key = (article['url'], article['title'], article['date_publicacao'].isoformat())
            if article_key in seen_articles:
                continue
            seen_articles.add(article_key)
            accepted.append(article)
        except Exception as exc:
            print(f'  aviso: matéria {candidate} falhou: {type(exc).__name__}: {exc}')

    accepted.sort(key=lambda item: item['date_publicacao'], reverse=True)
    accepted = accepted[:target]
    kept_ids = set()
    for article in accepted:
        document_id = (
            f'{source["id"]}__{slug(article["title"])}__'
            f'{hashlib.sha1(article["url"].encode("utf-8")).hexdigest()[:10]}'
        )
        kept_ids.add(slug(document_id))
        if not check:
            write_cache(
                source,
                article['url'],
                'web_article',
                raw,
                _article_cache_text(source, article),
                document_id,
                article['title'],
                extra_meta={
                    'data_publicacao': article['date_publicacao'].isoformat(),
                    'ano': article['date_publicacao'].year,
                    'autor': article.get('autor'),
                    'secao': article.get('secao'),
                    'palavras_chave': article.get('palavras_chave'),
                    'content_scope': source.get('web_article_scope'),
                    'web_source_title': source.get('title'),
                },
            )

    removed = cleanup_source_cache(source['id'], kept_ids) if not check else 0
    if successful_discoveries == 0:
        return False, f'FAIL {source["id"]}: nenhuma página de descoberta acessível', kept_ids
    return True, (
        f'OK {source["id"]}: {len(accepted)} matérias aceitas '
        f'(>= {min_date.isoformat()}, limite {target}, candidatas {len(candidates)}, '
        f'buscadas {fetched}, cache removido {removed})'
    ), kept_ids

def sync_one(session, source, check=False, follow_links=True):
    last = ''
    for url in _source_urls(source):
        try:
            kind, final, raw, text = fetch(session, url)
            validate(source, text, linked=False, final_url=final)
            seen_ids = {slug(source['id'])}
            if not check and not source.get('index_only'):
                write_cache(source, final, kind, raw, text, source['id'], source['title'])
            linked_ok = linked_total = 0
            link_failures = False
            if follow_links and source.get('follow_links') and kind == 'html':
                for link_url, link_title in discover_links(raw, final, source):
                    linked_total += 1
                    try:
                        linked_kind, linked_final, linked_raw, linked_text = fetch(session, link_url)
                        validate(source, linked_text, linked=True, final_url=linked_final, document_title=link_title)
                        linked_ok += 1
                        document_id = (
                            f"{source['id']}__{slug(link_title)}__{hashlib.sha1(linked_final.encode()).hexdigest()[:10]}"
                        )
                        seen_ids.add(slug(document_id))
                        if not check:
                            write_cache(source, linked_final, linked_kind, linked_raw, linked_text, document_id, link_title)
                    except Exception as exc:
                        link_failures = True
                        print(f'  aviso: link {link_url} falhou: {type(exc).__name__}: {exc}; cache anterior preservado')
            if source.get('index_only'):
                seen_ids.discard(slug(source['id']))
            removed = cleanup_source_cache(source['id'], seen_ids) if not check and not link_failures else 0
            suffix = f', PDFs linkados {linked_ok}/{linked_total}' if linked_total else ''
            if link_failures:
                suffix += ', cache obsoleto preservado por falha de link'
            elif removed:
                suffix += f', cache obsoleto removido {removed}'
            return True, f'OK {source["id"]} via {final} ({kind}, {len(text)} chars{suffix})', seen_ids
        except Exception as exc:
            last = f'{type(exc).__name__}: {exc}'
    return False, f'FAIL {source["id"]}: {last}', set()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--required-only', action='store_true')
    parser.add_argument('--legislation-only', action='store_true')
    parser.add_argument('--strict', action='store_true')
    parser.add_argument('--no-follow-links', action='store_true')
    args = parser.parse_args()
    sources = [
        s for s in SOURCES
        if (not args.required_only or s.get('required'))
        and (
            not args.legislation_only
            or (s.get('source_role') == 'norma' and not s.get('index_only'))
        )
    ]
    session = make_session()
    if not args.check:
        removed_retired = purge_retired_source_cache()
        if removed_retired:
            print(f'Fontes jurisprudenciais legadas removidas do cache: {removed_retired}')
    failures = []
    ok = 0
    for index, source in enumerate(sources, 1):
        print(f'[{index}/{len(sources)}] {source["id"]}', flush=True)
        good, message, _ = sync_one(session, source, check=args.check, follow_links=not args.no_follow_links and not args.check)
        print(message, flush=True)
        ok += int(good)
        if not good:
            failures.append(source['id'])
    print(f'Fontes: {ok}/{len(sources)} OK')
    if failures:
        print('Falhas:', ', '.join(failures))
    strict_failures = []
    if args.strict:
        strict_failures = [
            source['id']
            for source in sources
            if source['id'] in failures
            and source.get('source_role') == 'norma'
            and not source.get('index_only')
        ]
    if failures and args.required_only:
        return 1
    if strict_failures:
        print('Falhas legislativas bloqueantes:', ', '.join(strict_failures))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())