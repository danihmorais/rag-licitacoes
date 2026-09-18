from datetime import date
import json

from scripts.sources import SOURCES
from scripts.sync_sources import (
    _is_web_article_url,
    _parse_web_date,
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
