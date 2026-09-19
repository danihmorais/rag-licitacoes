from scripts.sources import SOURCES
from pathlib import Path
import pytest

from scripts.sync_sources import discover_links, normalized_pattern, validate


def test_pdf_follow_pattern_accepts_normal_and_double_escaped_regex():
    normal = "\\.pdf(?:$|\\?)"
    overescaped = normal.replace("\\", "\\\\")
    source = {"follow_patterns": [overescaped], "max_follow": 10}
    html = '<main><a href="/docs/a.pdf">PDF oficial</a><a href="/docs/b.html">HTML</a></main>'
    assert normalized_pattern(overescaped) == normal
    assert discover_links(html, "https://example.gov.br/pagina", source) == [("https://example.gov.br/docs/a.pdf", "PDF oficial")]


def test_source_catalog_is_unique_and_broad():
    ids = [item["id"] for item in SOURCES]
    assert len(ids) == len(set(ids))
    required = {"cf1988","lei14133","lei9784","lei8429","lei12846","lei12527","lei13709","lei13303","lei8987","lei11079","lrf","lei4320","lc123","lei13019","lei13460","lei14129","decreto11462","decreto11878","in65","in58","in81","sp-pca","lei14770","lei15190","lei15266","lei15471","decreto13031","decreto13106","pl-14230","pl-lc173","pl-12232","pl-13243","pl-10973","sp-const","sp-lei10177","sp-lai","tcesp-srp","lei4717","lei7347","lc131","decreto7724","lei6019","lei12016","lc182","spm-decreto62100","spm-decreto62436","spm-decreto64863","spm-in-seges6-2023","spm-pgm38-2025","sp-pge-pareceres"}
    assert required <= set(ids)
    retired = {"tcu","tcesp","tcu-dados-jurisprudencia","tcu-jurisprudencia-pesquisa","stj-jurisprudencia","stj-teses","stj-repetitivos-iacs","stj-sumulas-anotadas","stj-legislacao-aplicada","stj-informativos","stf-jurisprudencia","stf-repercussao-geral","stf-teses-rg","stf-tesauro","tjsp-jurisprudencia","tjsp-saj-jurisprudencia"}
    assert retired.isdisjoint(set(ids))
    areas = {item.get("ramo_direito") for item in SOURCES if item.get("ramo_direito")}
    assert {"Constitucional","Administrativo","Processual Público","Tributário","Financeiro e Orçamentário","Ambiental","Urbanístico","Saúde Pública","Educação Pública","Assistência Social","Pessoal e Servidores","Serviços Públicos","Contratações Públicas"} <= areas


def test_discovery_indexes_are_not_indexed_as_corpus_documents():
    index_ids = {"pl-discovery-camara","pl-discovery-lexml","pl-discovery-leis-2026","pl-discovery-leis-2025","pl-discovery-lc-atualizadas","pl-discovery-decretos-2026"}
    catalog = {item["id"]: item for item in SOURCES}
    index_ids.update({"pncp", "compras", "compras-in", "sp-compras", "sp-pge-pareceres", "pl-discovery-camara", "pl-discovery-lexml", "pl-discovery-leis-2026", "pl-discovery-leis-2025", "pl-discovery-lc-atualizadas", "pl-discovery-decretos-2026"})
    assert all(catalog[item].get("index_only") is True for item in index_ids)



def test_no_duplicate_primary_source_urls():
    urls = [url for item in SOURCES if not item.get("index_only") for url in item.get("urls", [])]
    assert len(urls) == len(set(urls))


ROOT = Path(__file__).resolve().parents[1]


def test_validator_rejects_spa_portal_shell():
    shell = (ROOT / "tests" / "fixtures" / "spa_shell.html").read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="casca de portal"):
        validate(next(item for item in SOURCES if item["id"] == "lei14133"), shell)


def test_validator_rejects_wrong_normative_identity():
    legal = (ROOT / "tests" / "fixtures" / "legal_act.txt").read_text(encoding="utf-8").replace("14.133", "13.999")
    with pytest.raises(RuntimeError, match="identidade normativa"):
        validate(next(item for item in SOURCES if item["id"] == "lei14133"), legal)


def test_validator_accepts_structured_normative_content():
    legal = (ROOT / "tests" / "fixtures" / "legal_act.txt").read_text(encoding="utf-8")
    validate(next(item for item in SOURCES if item["id"] == "lei14133"), legal)


def test_validator_accepts_official_guidance_content():
    guidance = (ROOT / "tests" / "fixtures" / "pge_guidance.txt").read_text(encoding="utf-8")
    validate(next(item for item in SOURCES if item["id"] == "sp-pge-pareceres"), guidance, linked=True)

def test_current_source_endpoints():
    catalog = {item["id"]: item for item in SOURCES}
    assert catalog["pncp"]["urls"][0] == "https://www.gov.br/pncp/pt-br/pncp/legislacao"
    assert catalog["tcesp-srp"]["urls"][0] == "https://tce.sp.gov.br/sites/default/files/legislacao/SEI_1482508_DELIBERACAO_TCESP.pdf"
    assert catalog["agu-modelos-14133"]["urls"][0].endswith("/modelos/licitacoesecontratos/14133")
    assert catalog["agu-tic"]["urls"][0].endswith("/modelos/licitacoesecontratos/14133/bens-e-servicos-de-tic")
    assert catalog["pl-discovery-camara"]["urls"][0] == "https://www.camara.leg.br/legislacao/busca?geral=&origem=C%C3%A2mara+dos+Deputados"
    assert catalog["pl-discovery-leis-2026"]["urls"][0].endswith("/_leis2026.htm")
    assert catalog["pl-discovery-lc-atualizadas"]["urls"][0].endswith("/quadro_lcp.htm")


def test_validator_accepts_short_discovery_page():
    source = next(item for item in SOURCES if item["id"] == "pl-discovery-lexml")
    validate(source, "LexML\nTudo\nLegislação\nJurisprudência\nProposições Legislativas")


def test_validator_rejects_empty_discovery_page():
    source = next(item for item in SOURCES if item["id"] == "pl-discovery-lexml")
    with pytest.raises(RuntimeError, match="conteúdo vazio"):
        validate(source, "   ")


def test_discover_links_honors_exclude_patterns():
    source = {
        "follow_patterns": [r"\\.pdf(?:$|\\?)"],
        "exclude_patterns": [r"observatorio_da_democracia", r"(?:^|/)cartilha\\.pdf(?:$|\\?)"],
        "max_follow": 10,
    }
    html = (
        '<main>'
        '<a href="pareceres/PARECERREFERENCIAL.pdf">Parecer Referencial</a>'
        '<a href="/observatorio_da_democracia/cartilha.pdf">Cartilha</a>'
        '</main>'
    )
    assert discover_links(
        html, "https://www.gov.br/agu/pagina", source
    ) == [("https://www.gov.br/agu/pareceres/PARECERREFERENCIAL.pdf", "Parecer Referencial")]


def test_validator_accepts_official_guidance_when_marker_is_only_in_link_metadata():
    source = next(item for item in SOURCES if item["id"] == "agu-pareceres-referenciais")
    content = "\n".join(
        ["MANIFESTAÇÃO JURÍDICA " + ("fundamentação jurídica " * 25) for _ in range(6)]
    )
    validate(
        source,
        content,
        linked=True,
        final_url="https://www.gov.br/agu/documentos/00009.pdf",
        document_title="PARECER REFERENCIAL n. 00009/2025/GERTEC/ELIC/PGF/AGU",
    )


def test_agu_model_collection_sources_exclude_irrelevant_cartilha():
    html = (
        '<main>'
        '<a href="modelos/edital.pdf">Edital</a>'
        '<a href="/assuntos-1/observatorio_da_democracia/cartilha.pdf">Cartilha</a>'
        '</main>'
    )
    catalog = {item["id"]: item for item in SOURCES}
    for source_id in {"agu-contratacao-direta", "agu-pregao-concorrencia"}:
        source = catalog[source_id]
        assert discover_links(html, source["urls"][0], source) == [
            ("https://www.gov.br/agu/pt-br/composicao/cgu/cgu/modelos/licitacoesecontratos/14133/modelos/edital.pdf", "Edital")
        ]


def test_tcesp_srp_source_accepts_official_deliberation_pdf_content():
    source = next(item for item in SOURCES if item["id"] == "tcesp-srp")
    content = "\n".join(
        [
            "DELIBERAÇÃO",
            "(SEI N. 0005763/2025-11)",
            "Artigo 1º - " + ("Sistema de Registro de Preços e adesão a atas. " * 4),
            "Artigo 2º - " + ("Cumprimento dos procedimentos pelos órgãos e entidades. " * 4),
            "I - " + ("estimativa das quantidades demandadas para registro e futura contratação. " * 4),
            "II - " + ("precisa descrição dos itens pretendidos e dos materiais e serviços. " * 4),
            "Artigo 3º - " + ("Processo administrativo específico para adesão e demonstração da vantajosidade. " * 4),
            "Artigo 5º - " + ("Regras para adesões no Estado e nos Municípios paulistas. " * 4),
        ]
    )
    validate(source, content)


def test_tcu_manual_is_required_official_guidance_source():
    catalog = {item["id"]: item for item in SOURCES}
    source = catalog["tcu-manual-licitacoes"]
    assert source["required"] is True
    assert source["source_role"] == "orientacao_oficial"
    assert source["authority_level"] == 3
    assert source["tipo_documento"] == "manual"
    assert source["urls"][0].endswith("Licitacoes-e-Contratos-Orientacoes-e-Jurisprudencia-do-TCU-5a-Edicao.pdf")


def test_validator_accepts_tcu_manual_content():
    source = next(item for item in SOURCES if item["id"] == "tcu-manual-licitacoes")
    content = "\n".join(
        [
            "MANUAL DE LICITAÇÕES E CONTRATOS",
            "Orientações e Jurisprudência do Tribunal de Contas da União",
            "5ª edição",
            "Objetivo e escopo do manual.",
            "Licitações e contratos administrativos.",
            "A Lei 14.133/2021 constitui a referência normativa central.",
            "São apresentadas orientações preventivas e pedagógicas.",
            "O manual reúne referências normativas e jurisprudência.",
        ]
    )
    validate(source, content)
