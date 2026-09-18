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


def validate(source, text, *, linked=False, final_url=None):
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
        if not any(marker in stripped.casefold() for marker in markers):
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
    host = urlparse(base_url).netloc.lower()
    out = []
    seen = set()
    for anchor in soup.find_all('a', href=True):
        absolute = urljoin(base_url, str(anchor['href']).strip()).split('#', 1)[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in {'http', 'https'} or (not source.get('allow_cross_host') and parsed.netloc.lower() != host):
            continue
        label = anchor.get_text(' ', strip=True)
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


def write_cache(source, final, kind, raw, text, document_id, title):
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
                        validate(source, linked_text, linked=True, final_url=linked_final)
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