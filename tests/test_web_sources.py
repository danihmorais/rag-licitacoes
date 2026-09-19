from datetime import date
import json

from scripts.sources import SOURCES
from scripts.sync_sources import _decode_response
from scripts.web_sources import (
    _is_web_article_url,
    _parse_web_date,
    _web_link_candidates,
    _web_topic_matches,
    extract_web_article,
)


def test_web_date_parser_supports_portuguese_iso_and_conjur_urls():
    assert _parse_web_date("5 de abril de 2024") == date(2024, 4, 5)
    assert _parse_web_date("18.set.2026") == date(2026, 9, 18)
    assert _parse_web_date("2024-04-05T12:00:00-03:00") == date(2024, 4, 5)
    assert _parse_web_date("https://conjur.com.br/2024-dez-06/licitacao-exemplo") == date(2024, 12, 6)
    assert _parse_web_date("https://example.com/2021/04/26/artigo") == date(2021, 4, 26)


def test_extract_web_article_prefers_jsonld_metadata():
    body = "Texto substantivo do artigo. " * 120
    payload = {
        "@type": "Article",
        "headline": "Licitação e contrato administrativo",
        "datePublished": "2024-04-05T10:00:00-03:00",
        "author": {"name": "Autor Teste"},
        "articleSection": "Licitações e Contratos",
        "keywords": "licitação, contrato administrativo",
        "articleBody": body,
    }
    html = f"""
    <html>
      <head>
        <script type="application/ld+json">{json.dumps(payload, ensure_ascii=False)}</script>
      </head>
      <body>
        <main>
          <article>
            <h1>Licitação e contrato administrativo</h1>
            <p>{body}</p>
          </article>
        </main>
      </body>
    </html>
    """
    article = extract_web_article(html.encode("utf-8"), "https://example.com/artigo")
    assert article["title"] == "Licitação e contrato administrativo"
    assert article["date_publicacao"] == date(2024, 4, 5)
    assert article["autor"] == "Autor Teste"
    assert article["secao"] == "Licitações e Contratos"
    assert len(article["texto"]) >= 800


def test_web_topic_filter_rejects_unrelated_migalhas_content():
    source = next(item for item in SOURCES if item["id"] == "web-migalhas")
    assert _web_topic_matches(source, {
        "title": "Nova Lei de Licitações e contratos administrativos",
        "secao": "Direito Administrativo",
        "palavras_chave": "",
        "texto": "Análise da Lei 14.133/2021 e das contratações públicas.",
    })
    assert not _web_topic_matches(source, {
        "title": "Divórcio e partilha de bens",
        "secao": "Família",
        "palavras_chave": "",
        "texto": "Discussão sobre direito de família e sucessões.",
    })


def test_web_article_url_policy_avoids_archive_and_accepts_article_paths():
    conlic = next(item for item in SOURCES if item["id"] == "web-conlicitacao")
    assert _is_web_article_url(conlic, "https://conlicitacao.com.br/blog/criterios-de-julgamento/")
    assert not _is_web_article_url(conlic, "https://conlicitacao.com.br/blog/page/4/")

    mig = next(item for item in SOURCES if item["id"] == "web-migalhas")
    assert _is_web_article_url(mig, "https://www.migalhas.com.br/depeso/123456")
    assert not _is_web_article_url(mig, "https://www.migalhas.com.br/tour_juridico")


def test_web_article_url_policy_rejects_static_assets_and_image_directories():
    source = next(item for item in SOURCES if item["id"] == "web-licitacoes-publicas-blog")
    for url in (
        "https://licitacoespublicas.blog.br/imagens/comentarios_pp005.png",
        "https://licitacoespublicas.blog.br/imagens/consultoria_15.png",
        "https://licitacoespublicas.blog.br/imagens/logo_LP_600x151.png",
        "https://licitacoespublicas.blog.br/assets/site.js",
        "https://licitacoespublicas.blog.br/arquivo.pdf",
    ):
        assert not _is_web_article_url(source, url)
    assert _is_web_article_url(
        source,
        "https://licitacoespublicas.blog.br/licitacoes/dispensa-eletronica-exemplo/",
    )


def test_web_sources_have_date_floor_and_bounded_corpus():
    web = [item for item in SOURCES if item.get("source_type") == "web_articles"]
    assert {item["id"] for item in web} == {
        "web-nova-lei-licitacao",
        "web-licitacoes-publicas-blog",
        "web-conlicitacao",
        "web-zenite",
        "web-migalhas",
        "web-conjur",
    }
    for item in web:
        assert item["min_publication_date"] == "2021-01-01"
        assert item["max_documents"] in {250, 300}
        assert item["source_role"] == "doutrina"
        assert item["authority_level"] == 4
        assert item["source_type"] == "web_articles"
        assert item["is_official"] is False


def test_web_next_link_detects_textual_pagination():
    source = next(item for item in SOURCES if item["id"] == "web-licitacoes-publicas-blog")
    html = '<html><body><a href="/page/2/">Seguinte</a></body></html>'
    candidates, next_urls = _web_link_candidates(
        html.encode("utf-8"),
        "https://licitacoespublicas.blog.br/",
        source,
    )
    assert candidates == []
    assert next_urls == ["https://licitacoespublicas.blog.br/page/2/"]


def test_extract_web_article_rejects_spa_shell():
    shell = '<html><body><div id="root"></div><script src="/assets/app.js"></script></body></html>'
    import pytest
    with pytest.raises(RuntimeError, match="casca de portal/SPA"):
        extract_web_article(shell.encode("utf-8"), "https://example.com/")


def test_sync_response_treats_sitemap_xml_as_xml_without_html_parsing_warning():
    import warnings

    raw = b'<?xml version="1.0" encoding="UTF-8"?><urlset><url><loc>https://example.com/a</loc></url></urlset>'
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        kind, final, returned_raw, text = _decode_response(
            raw,
            "https://example.com/wp-sitemap.xml",
            "application/xml",
        )

    assert kind == "xml"
    assert final.endswith("/wp-sitemap.xml")
    assert returned_raw == raw
    assert "https://example.com/a" in text
    assert not any("XMLParsedAsHTMLWarning" in str(item.message.__class__.__name__) for item in caught)


def test_nova_lei_licitacao_does_not_configure_known_404_sitemap():
    source = next(item for item in SOURCES if item["id"] == "web-nova-lei-licitacao")
    assert "https://www.novaleilicitacao.com.br/sitemap_index.xml" not in source["sitemap_urls"]
    assert "https://www.novaleilicitacao.com.br/wp-sitemap.xml" in source["sitemap_urls"]
