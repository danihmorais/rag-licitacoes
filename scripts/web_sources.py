from __future__ import annotations

from datetime import date, datetime
import hashlib
import html
import io
import json
import re
from urllib.parse import unquote, urljoin, urlparse
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from pypdf import PdfReader

WEB_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

WEB_EXCLUDED_PATH_PARTS = (
    "/page/", "/category/", "/tag/", "/autor/", "/author/", "/feed",
    "/wp-json/", "/wp-admin/", "/wp-content/", "/comments/", "/comment-page-",
    "/buscar", "/search", "/login", "/cadastro", "/sobre", "/contato",
    "/politica-de-privacidade", "/termos", "/caderno/", "/imagens/",
)

WEB_STATIC_EXTENSIONS = (
    ".7z", ".avi", ".bmp", ".css", ".csv", ".doc", ".docx", ".gif", ".gz",
    ".ico", ".jpeg", ".jpg", ".js", ".json", ".m4a", ".mp3", ".mp4",
    ".mpeg", ".png", ".rss", ".svg", ".tar", ".tif", ".tiff", ".webm", ".webp",
    ".woff", ".woff2", ".xls", ".xlsx", ".zip",
)

WEB_ADMIN_EXCLUDE = (
    "direito de família", "divórcio", "direito trabalhista",
    "direito do trabalho", "direito previdenciário", "direito penal",
    "direito empresarial", "direito societário", "direito do consumidor",
    "propriedade intelectual",
)


def _looks_like_spa_shell(soup):
    body_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    app_nodes = soup.find_all(id=re.compile(r"^(root|app|__next|application)$", re.I))
    scripts = soup.find_all("script")
    return len(body_text) < 300 and bool(app_nodes) and bool(scripts)


def _text_density(text):
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    substantive = [line for line in str(text or "").splitlines() if len(line.strip()) >= 40]
    return len(value), len(substantive)


def _valid_article_text(text, min_substantive=6):
    chars, substantive = _text_density(text)
    return chars >= 800 and substantive >= min_substantive


def _parse_web_date(value):
    if not value:
        return None
    raw = html.unescape(str(value)).strip()
    raw = re.sub(r"\s+", " ", raw)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    patterns = (
        r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b",
        r"\b(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, raw)
        if match:
            try:
                groups = [int(value) for value in match.groups()]
                if pattern.startswith(r"\b(20"):
                    return date(groups[0], groups[1], groups[2])
                return date(groups[2], groups[1], groups[0])
            except ValueError:
                return None
    match = re.search(
        r"\b(\d{1,2})\s*(?:de\s*)?([A-Za-zÀ-ÿ]+)\s*(?:de\s*)?(20\d{2})\b",
        raw, re.I,
    )
    if match:
        month = WEB_MONTHS.get(match.group(2).casefold())
        if month:
            try:
                return date(int(match.group(3)), month, int(match.group(1)))
            except ValueError:
                return None
    match = re.search(r"\b(\d{1,2})[./-]([A-Za-z]{3})[./-](20\d{2})\b", raw, re.I)
    if match:
        month = WEB_MONTHS.get(match.group(2).casefold())
        if month:
            try:
                return date(int(match.group(3)), month, int(match.group(1)))
            except ValueError:
                return None
    match = re.search(r"\b(20\d{2})[-/]([A-Za-zÀ-ÿ]{3,12})[-/](\d{1,2})\b", raw, re.I)
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

    for script in soup.find_all("script", type=lambda value: value and "ld+json" in value):
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
    for tag in soup.find_all("meta"):
        key = str(tag.get("property") or tag.get("name") or tag.get("itemprop") or "").casefold()
        if key in wanted and tag.get("content"):
            return str(tag["content"]).strip()
    return None


def _article_text_node(soup):
    for selector in (
        '[itemprop="articleBody"]',
        "article",
        ".entry-content",
        ".post-content",
        ".article-content",
        ".article-body",
        ".post__content",
        "main",
    ):
        node = soup.select_one(selector)
        if node and len(node.get_text("\n", strip=True)) >= 800:
            return node
    return soup.body or soup


def extract_web_pdf(raw_pdf, final_url):
    reader = PdfReader(io.BytesIO(raw_pdf))
    metadata = reader.metadata or {}
    pages = [page.extract_text() or "" for page in reader.pages]
    body = "\n\n".join(page.strip() for page in pages if page.strip()).strip()
    title = str(metadata.get("/Title") or metadata.get("Title") or "").strip()
    if not title:
        name = unquote(urlparse(final_url).path.rsplit("/", 1)[-1])
        title = re.sub(r"[_-]+", " ", re.sub(r"\\.[A-Za-z0-9]+$", "", name)).strip()
    creation = metadata.get("/CreationDate") or metadata.get("CreationDate")
    date_publicacao = _parse_web_date(str(creation or "")) or _parse_web_date(final_url)
    if not date_publicacao and creation:
        match = re.search(r"D:(20\d{2})(\d{2})(\d{2})", str(creation))
        if match:
            try:
                date_publicacao = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass
    return {
        "title": html.unescape(title),
        "date_publicacao": date_publicacao,
        "autor": str(metadata.get("/Author") or metadata.get("Author") or "").strip(),
        "secao": "",
        "palavras_chave": "",
        "texto": body,
        "url": final_url,
    }

def extract_web_article(raw_html, final_url):
    soup = BeautifulSoup(raw_html, "html.parser")
    if _looks_like_spa_shell(soup):
        raise RuntimeError("casca de portal/SPA sem conteúdo textual")
    jsonld = list(_jsonld_objects(soup))
    time_values = [tag.get("datetime") for tag in soup.find_all("time") if tag.get("datetime")]
    visible_hint = soup.get_text(" ", strip=True)[:2500]
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "aside", "iframe"]):
        tag.decompose()
    for tag in soup.find_all(
        class_=re.compile(
            r"(share|social|related|coment|comment|advert|banner|cookie|newsletter|menu|breadcrumb|sidebar)",
            re.I,
        )
    ):
        tag.decompose()

    title = None
    body_from_jsonld = None
    published = None
    author = None
    section = None
    keywords = None
    for item in jsonld:
        title = title or item.get("headline") or item.get("name")
        body_from_jsonld = body_from_jsonld or item.get("articleBody")
        published = published or item.get("datePublished") or item.get("dateCreated")
        author_value = item.get("author")
        if isinstance(author_value, dict):
            author_value = author_value.get("name")
        elif isinstance(author_value, list):
            author_value = ", ".join(
                str(value.get("name") if isinstance(value, dict) else value)
                for value in author_value
                if value
            )
        author = author or author_value
        section = section or item.get("articleSection")
        keyword_value = item.get("keywords")
        if isinstance(keyword_value, list):
            keyword_value = ", ".join(str(value) for value in keyword_value)
        keywords = keywords or keyword_value

    title = title or _first_meta(soup, "og:title", "twitter:title")
    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(" ", strip=True)
    published = (
        published
        or _first_meta(soup, "article:published_time", "datePublished", "date", "pubdate")
        or (time_values[0] if time_values else None)
        or final_url
    )
    author = author or _first_meta(soup, "author", "article:author")
    section = section or _first_meta(soup, "article:section", "section")
    keywords = keywords or _first_meta(soup, "keywords", "article:tag")
    if not published:
        visible = soup.get_text(" ", strip=True)
        label_match = re.search(
            r"(?:publicad[oa]|publicação|publicacao|published)(?:\s+em|\s*:)\s+(.{0,80})",
            visible[:5000],
            re.I,
        )
        published = label_match.group(1) if label_match else visible[:2000]

    article_node = _article_text_node(soup)
    body = article_node.get_text("\n", strip=True) if article_node else ""
    if len(body) < 800 and body_from_jsonld:
        body = str(body_from_jsonld).strip()
    if title and title.casefold() not in body.casefold():
        body = f"{title}\n\n{body}"

    return {
        "title": html.unescape(str(title or "").strip()),
        "date_publicacao": _parse_web_date(published),
        "autor": html.unescape(str(author or "").strip()),
        "secao": html.unescape(str(section or "").strip()),
        "palavras_chave": html.unescape(str(keywords or "").strip()),
        "texto": body.strip(),
        "url": final_url,
    }


def _is_web_article_url(source, url):
    parsed = urlparse(url)
    path = unquote(parsed.path or "/")
    low = path.casefold()
    if parsed.scheme not in {"http", "https"}:
        return False
    if any(part in low for part in WEB_EXCLUDED_PATH_PARTS):
        return False
    if low.endswith(WEB_STATIC_EXTENSIONS):
        return False
    source_id = source.get("id")
    if source_id == "web-migalhas":
        return bool(re.match(r"^/(?:depeso|quentes|colunas)/[^/]+(?:/|$)", low))
    if source_id == "web-conjur":
        return bool(re.search(r"/20\d{2}-(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)-\d{2}/", low))
    if source_id == "web-conlicitacao":
        return low.startswith("/blog/") and not low.startswith("/blog/page/")
    if source_id == "web-nova-lei-licitacao":
        return bool(re.search(r"/20\d{2}/\d{1,2}/\d{1,2}/", low))
    return path.rstrip("/") not in {"", "/"} and not low.endswith((".xml", ".rss", ".txt"))


def _web_link_candidates(raw_html, base_url, source):
    soup = BeautifulSoup(raw_html, "html.parser")
    base_host = urlparse(base_url).netloc.lower().removeprefix("www.")
    candidates = []
    next_urls = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(base_url, str(anchor["href"]).strip()).split("#", 1)[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc.lower().removeprefix("www.") != base_host:
            continue
        label = anchor.get_text(" ", strip=True)
        label_norm = re.sub(r"\s+", " ", label).strip().casefold()
        rel = " ".join(anchor.get("rel", [])) if anchor.get("rel") else ""
        query_or_path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        is_next = (
            rel.casefold() == "next"
            or bool(re.search(r"\b(?:próxima|proxima|seguinte|next)\s+p(?:á|a)gina\b", label, re.I))
            or label_norm in {"próxima", "proxima", "seguinte", "next", "older posts", "older", "mais antigas"}
            or bool(re.search(r"(?:/page/\d+/?$|[?&]pagina=\d+\b|/pagina/\d+/?$)", query_or_path, re.I))
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
        if loc.tag.rsplit("}", 1)[-1] == "loc" and loc.text and loc.text.strip()
    ]


def _rss_article_links(raw, source):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    links = []
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] not in {"item", "entry"}:
            continue
        for child in list(item):
            if child.tag.rsplit("}", 1)[-1] != "link":
                continue
            href = child.get("href") or (child.text or "").strip()
            if href and _is_web_article_url(source, href):
                links.append(href)
    return list(dict.fromkeys(links))


def _web_topic_matches(source, article):
    if source.get("web_article_scope") == "dedicated_licitacao":
        return True
    title_meta = " ".join(
        str(article.get(key) or "") for key in ("title", "secao", "palavras_chave")
    ).casefold()
    haystack = " ".join(
        str(article.get(key) or "") for key in ("title", "secao", "palavras_chave", "texto")
    ).casefold()
    positives = {
        term.casefold()
        for term in source.get("topic_include_terms", ())
        if term.casefold() in haystack
    }
    title_positives = {
        term.casefold()
        for term in source.get("topic_include_terms", ())
        if term.casefold() in title_meta
    }
    excluded = {
        term.casefold()
        for term in source.get("topic_exclude_terms", WEB_ADMIN_EXCLUDE)
        if term.casefold() in title_meta
    }
    if title_positives or "administrativo" in title_meta or "direito público" in title_meta or "direito publico" in title_meta:
        return not excluded or bool(title_positives)
    return len(positives) >= 2 and not excluded


def _article_cache_text(source, article):
    parts = [
        f"FONTE: {source['orgao']}",
        f"TÍTULO: {article['title']}",
        f"DATA_PUBLICACAO: {article['date_publicacao'].isoformat()}",
    ]
    if article.get("autor"):
        parts.append(f"AUTOR: {article['autor']}")
    if article.get("secao"):
        parts.append(f"SECAO: {article['secao']}")
    if article.get("palavras_chave"):
        parts.append(f"PALAVRAS_CHAVE: {article['palavras_chave']}")
    parts.append(f"URL: {article['url']}")
    parts.extend(["", article["texto"]])
    return "\n".join(parts).strip()


def sync_web_articles(session, source, check=False):
    from scripts.sync_sources import cleanup_source_cache, fetch, slug, write_cache

    target = int(source.get("max_documents", 250))
    min_date = _parse_web_date(source.get("min_publication_date")) or date(2021, 1, 1)
    candidates = []
    seen = set()
    page_queue = list(source.get("urls", ()))
    visited_pages = set()
    successful_discoveries = 0
    max_pages = int(source.get("discovery_max_pages", 80))

    while page_queue and len(visited_pages) < max_pages:
        page_url = page_queue.pop(0)
        if page_url in visited_pages:
            continue
        visited_pages.add(page_url)
        try:
            _, final, raw, _ = fetch(session, page_url)
            successful_discoveries += 1
        except Exception as exc:
            print(f"  aviso: descoberta {page_url} falhou: {type(exc).__name__}: {exc}")
            continue
        if raw.lstrip().startswith((b"<?xml", b"<")):
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
        for sitemap_url in source.get("sitemap_urls", ()):
            if len(candidates) >= target * 6:
                break
            try:
                _, _, raw, _ = fetch(session, sitemap_url)
                successful_discoveries += 1
            except Exception as exc:
                print(f"  aviso: sitemap {sitemap_url} falhou: {type(exc).__name__}: {exc}")
                continue
            sitemap_links = _sitemap_urls(raw)
            nested = []
            for link in sitemap_links:
                if re.search(r"\.(?:xml|xml\.gz)$", urlparse(link).path.casefold()):
                    nested.append(link)
                elif _is_web_article_url(source, link) and link not in seen:
                    seen.add(link)
                    candidates.append(link)
            for nested_url in nested[:30]:
                if len(candidates) >= target * 6:
                    break
                try:
                    _, _, nested_raw, _ = fetch(session, nested_url)
                    successful_discoveries += 1
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
    article_failures = 0
    for candidate in candidates:
        if len(accepted) >= target or fetched >= target * 6:
            break
        fetched += 1
        try:
            kind, final, raw, _ = fetch(session, candidate)
            article = extract_web_pdf(raw, final) if kind == "pdf" else extract_web_article(raw, final)
            min_substantive = 1 if kind == "pdf" else 6
            if not article["title"] or not _valid_article_text(article["texto"], min_substantive=min_substantive) or not article["date_publicacao"]:
                continue
            article["_kind"] = "web_pdf" if kind == "pdf" else "web_article"
            if article["date_publicacao"] < min_date:
                continue
            if not _web_topic_matches(source, article):
                continue
            key = (article["url"], article["title"], article["date_publicacao"].isoformat())
            if key in seen_articles:
                continue
            seen_articles.add(key)
            article["_raw"] = raw
            accepted.append(article)
        except Exception as exc:
            article_failures += 1
            print(f"  aviso: matéria {candidate} falhou: {type(exc).__name__}: {exc}")

    if successful_discoveries == 0:
        return False, f"FAIL {source['id']}: nenhuma página de descoberta acessível", set()
    if not candidates:
        return False, f"FAIL {source['id']}: nenhuma matéria candidata encontrada", set()
    if not accepted:
        return False, f"FAIL {source['id']}: nenhuma matéria válida de {min_date.isoformat()} em diante", set()

    accepted.sort(key=lambda item: item["date_publicacao"], reverse=True)
    accepted = accepted[:target]
    kept_ids = set()
    for article in accepted:
        document_id = (
            f"{source['id']}__{slug(article['title'])}__"
            f"{hashlib.sha1(article['url'].encode('utf-8')).hexdigest()[:10]}"
        )
        kept_ids.add(slug(document_id))
        if not check:
            write_cache(
                source,
                article["url"],
                article.get("_kind", "web_article"),
                article["_raw"],
                _article_cache_text(source, article),
                document_id,
                article["title"],
                extra_meta={
                    "data_publicacao": article["date_publicacao"].isoformat(),
                    "ano": article["date_publicacao"].year,
                    "autor": article.get("autor"),
                    "secao": article.get("secao"),
                    "palavras_chave": article.get("palavras_chave"),
                    "content_scope": source.get("web_article_scope"),
                    "web_source_title": source.get("title"),
                },
            )
    removed = cleanup_source_cache(source["id"], kept_ids) if not check and not article_failures else 0
    suffix = ", cache obsoleto preservado por falha de matéria" if article_failures else f", cache obsoleto removido {removed}"
    return True, (
        f"OK {source['id']}: {len(accepted)} matérias aceitas "
        f"(>= {min_date.isoformat()}, limite {target}, candidatas {len(candidates)}, "
        f"buscadas {fetched}{suffix})"
    ), kept_ids
