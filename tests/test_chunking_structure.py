"""Regressões de estrutura jurídica no chunking (hierarquia, perda de texto, falsos limites)."""
import re
from pathlib import Path

import chunking
from chunking import build_structural_chunks


def chunks_of(text, size=2000, overlap=100):
    # O helper usa o pipeline real de chunking; o tamanho reduzido torna a regressão independente do tokenizer.
    return build_structural_chunks(text, size, overlap, tokenizer=None)


def articles_in(chunks):
    return [c["unit_ref"] for c in chunks if c["unit_kind"] == "artigo"]


def test_inciso_de_paragrafo_carrega_o_paragrafo_no_caminho():
    text = (
        "Art. 75. É dispensável a licitação:\n"
        "I - valores inferiores a R$ 100.000,00;\n"
        "§ 1º Para fins de aferição dos valores:\n"
        "I - o somatório do exercício;\n"
        "II - o somatório do mesmo ramo.\n"
        "§ 2º Os valores serão atualizados.\n"
    )
    incisos = [c for c in chunks_of(text) if c["segment_kind"] == "inciso"]
    paths = [c["hierarchy_path"][1:] for c in incisos]
    assert paths == [["I -"], ["§ 1º", "I -"], ["§ 1º", "II -"]]
    assert "Art. 75. > § 1º > II -" in incisos[2]["text"]


def test_alinea_e_item_sob_o_caput_nao_somem():
    text = (
        "Art. 30. Os requisitos são:\n"
        "a) capacidade técnica;\n"
        "b) regularidade fiscal.\n"
        "Parágrafo único. Aplica-se a todos.\n"
    )
    chunks = chunks_of(text)
    joined = "\n".join(c["text"] for c in chunks)
    assert "capacidade técnica" in joined and "regularidade fiscal" in joined
    assert [c["segment_ref"] for c in chunks if c["segment_kind"] == "alinea"] == ["a)", "b)"]


def test_todo_texto_do_artigo_aparece_em_algum_chunk():
    text = (
        "LEI Nº 1, DE 2026\n\n"
        "Art. 1º Caput com regra.\n"
        "I - primeiro inciso;\n"
        "a) alínea sob inciso;\n"
        "1. item sob alínea;\n"
        "§ 1º Parágrafo.\n"
        "I - inciso do parágrafo.\n"
        "Parágrafo único. Fecho.\n\n"
        "Art. 2º Outro artigo.\n"
        "a) alínea solta sob o caput.\n"
    )
    joined = "\n".join(c["text"] for c in chunks_of(text))
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("LEI Nº"):
            assert line in joined, line


def test_numero_quebrado_de_pdf_nao_vira_item():
    text = "Art. 10. Regulamenta a Lei nº\n14.133, de 1º de abril de 2021.\nArt. 11. Outra regra."
    chunks = chunks_of(text)
    assert all(c["segment_kind"] != "item" for c in chunks)
    assert articles_in(chunks) == ["Art. 10.", "Art. 11."]


def test_palavra_com_hifen_ou_sigla_no_inicio_da_linha_nao_vira_inciso():
    text = "Art. 40. Trata da responsabilidade\ncivil- administrativa e do e-mail\np. 12 do processo.\nI - inciso real."
    kinds = [c["segment_kind"] for c in chunks_of(text) if c["segment_kind"] not in {"caput"}]
    assert kinds == ["inciso"]


def test_citacoes_nao_criam_artigos_falsos():
    text = (
        "Art. 20. A dispensa observa o disposto\n"
        "art. 75, inciso II, e o previsto no art. 76 desta Lei, bem como o art. 77 do Decreto.\n"
        "Art. 21. Fim."
    )
    assert articles_in(chunks_of(text)) == ["Art. 20.", "Art. 21."]


def test_artigo_com_milhar_e_sufixo_duplo():
    text = "Art. 1.045. Regra com milhar.\nArt. 337-E. Admitir.\nArt. 337-AB. Dois sufixos."
    assert articles_in(chunks_of(text)) == ["Art. 1.045.", "Art. 337-E.", "Art. 337-AB."]


def test_cabecalho_do_proximo_capitulo_nao_polui_o_artigo_anterior():
    text = (
        "LEI Nº 14.133, DE 1º DE ABRIL DE 2021\n\n"
        "CAPÍTULO I\nDAS DISPOSIÇÕES GERAIS\n\n"
        "Art. 1º Esta Lei estabelece normas gerais.\n\n"
        "CAPÍTULO II\nDA CONTRATAÇÃO DIRETA\n\n"
        "Art. 2º Regra de contratação.\n"
    )
    by_ref = {c["unit_ref"]: c for c in chunks_of(text)}
    assert "CAPÍTULO II" not in by_ref["Art. 1º"]["text"]
    assert by_ref["Art. 1º"]["hierarchy_headers"][-1] == "CAPÍTULO I — DAS DISPOSIÇÕES GERAIS"
    assert by_ref["Art. 2º"]["hierarchy_headers"][-1] == "CAPÍTULO II — DA CONTRATAÇÃO DIRETA"


def test_anexo_vira_unidade_propria_e_nao_gera_filhos_do_ultimo_artigo():
    text = (
        "LEI Nº 1, DE 2026\n\nCAPÍTULO II\n\n"
        "Art. 3º Fim.\n\n"
        "ANEXO I\nTabela de valores\n1. Item um da tabela\n2. Item dois da tabela\n"
    )
    chunks = chunks_of(text)
    art = [c for c in chunks if c["unit_kind"] == "artigo"]
    anexo = [c for c in chunks if c["unit_kind"] == "anexo"]
    assert len(art) == 1 and "ANEXO" not in art[0]["text"] and art[0]["segment_kind"] == "caput"
    assert anexo and "Item dois da tabela" in anexo[0]["text"]
    assert anexo[0]["hierarchy_headers"] == ["LEI Nº 1, DE 2026"]  # sem o capítulo herdado


def test_linha_quebrada_com_lei_nao_sequestra_o_titulo_da_norma():
    text = (
        "LEI Nº 14.133, DE 1º DE ABRIL DE 2021\n\n"
        "Art. 1º Esta Lei estabelece normas, conforme a\nLei nº 8.666, de 21 de junho de 1993, para todos.\n\n"
        "Art. 2º Regra.\n"
    )
    by_ref = {c["unit_ref"]: c for c in chunks_of(text)}
    assert by_ref["Art. 2º"]["hierarchy_headers"] == ["LEI Nº 14.133, DE 1º DE ABRIL DE 2021"]


def test_secao_nova_encerra_subsecao_da_secao_anterior():
    text = "CAPÍTULO I\nSEÇÃO I\nSUBSEÇÃO I\nArt. 1º A.\nSEÇÃO II\nArt. 2º B.\n"
    units = chunking._article_units(text)
    assert units[1]["headers"] == ["CAPÍTULO I", "SEÇÃO II"]


def test_unit_id_distingue_artigos_com_a_mesma_referencia():
    text = "Art. 1º Lei principal.\n\nArt. 2º Segunda.\n\nANEXO I\nMODELO\nArt. 1º Regra do modelo.\n"
    ids = [c["unit_id"] for c in chunks_of(text) if c["unit_kind"] == "artigo" and c["unit_ref"] == "Art. 1º"]
    assert len(ids) == 2 and len(set(ids)) == 2


def test_fixture_real_da_lei_14133_preserva_ordem_e_ref_do_artigo():
    fixture = Path(__file__).resolve().parent / "fixtures" / "legal_act.txt"
    text = fixture.read_text(encoding="utf-8")
    chunks = chunks_of(text)
    articles = [item["unit_ref"] for item in chunks if item["unit_kind"] == "artigo"]
    assert articles[:4] == ["Art. 1º", "Art. 2º", "Art. 3º", "Art. 4º"]
    assert articles[-1] == "Art. 8º"
    assert len(articles) == 8
    assert all(article.startswith("Art.") for article in articles)


def test_end_aponta_para_o_trecho_na_fonte_e_nao_inclui_o_prefixo():
    text = (
        "CAPÍTULO I\nArt. 1º Regra do caput que precisa de contexto:\n"
        "I - primeira hipótese;\nII - segunda hipótese.\n"
    )
    for c in chunks_of(text):
        source = text[c["start"]:c["end"]]
        assert source and source.strip() in c["text"]
        assert c["end"] - c["start"] <= len(c["text"])
    inciso = [c for c in chunks_of(text) if c["segment_ref"] == "II -"][0]
    assert text[inciso["start"]:inciso["end"]] == "II - segunda hipótese."


def test_split_longo_nao_comeca_chunk_com_pontuacao():
    long_text = "Art. 9º " + " ".join(f"Sentença número {i} do texto jurídico com várias palavras." for i in range(40))
    pieces = chunks_of(long_text, size=100, overlap=40)
    assert len(pieces) > 3
    for c in pieces:
        assert not re.match(r"^[.;:]", c["text"])
    assert all(c["text"].rstrip().endswith(".") for c in pieces)


def test_aspas_de_abertura_do_artigo_emendado_nao_ficam_no_artigo_anterior():
    text = "Art. 5º O Decreto-Lei passa a vigorar com o artigo:\n“Art. 337-E. Admitir à licitação.” (NR)\nArt. 6º Vigência."
    by_ref = {c["unit_ref"]: c for c in chunks_of(text)}
    assert not by_ref["Art. 5º"]["text"].rstrip().endswith("“")


def test_artigo_entre_aspas_em_formula_de_alteracao_nao_gera_artigo_irmao():
    text = (
        "Art. 5º O Decreto-Lei passa a vigorar com o artigo:\n"
        "“Art. 337-E. Admitir à licitação.” (NR)\n"
        "Art. 6º Vigência."
    )
    refs = [item["unit_ref"] for item in chunks_of(text) if item["unit_kind"] == "artigo"]
    assert refs == ["Art. 5º", "Art. 6º"]


def test_alteracao_com_fica_acrescentado_eh_identificada_sem_gerar_artigo_falso():
    text = (
        "Art. 2º Fica acrescentado o art. 75-A:\n"
        "“Art. 75-A. Nova regra de licitação.”\n"
        "Art. 3º Vigência."
    )
    by_ref = {item["unit_ref"]: item for item in chunks_of(text) if item["unit_kind"] == "artigo"}
    assert by_ref["Art. 2º"]["amendment"] is True
    assert by_ref["Art. 2º"]["target_article"] == "Art. 75-A"
    assert list(by_ref) == ["Art. 2º", "Art. 3º"]


def test_alteracao_plural_com_ficam_acrescentados_eh_identificada_sem_gerar_artigo_falso():
    text = (
        "Art. 2º Ficam acrescentados os arts. 75-A e 76-A:\n"
        "“Art. 75-A. Nova regra de licitação.”\n"
        "“Art. 76-A. Segunda regra de licitação.”\n"
        "Art. 3º Vigência."
    )
    by_ref = {item["unit_ref"]: item for item in chunks_of(text) if item["unit_kind"] == "artigo"}
    assert by_ref["Art. 2º"]["amendment"] is True
    assert by_ref["Art. 2º"]["target_article"] == "Art. 75-A"


def test_alteracao_com_passa_a_vigorar_com_redacao_eh_identificada_sem_gerar_artigo_falso():
    text = (
        "Art. 5º O art. 75 passa a vigorar com a seguinte redação:\n"
        "“Art. 75. Nova regra de licitação.”\n"
        "Art. 6º Vigência."
    )
    by_ref = {item["unit_ref"]: item for item in chunks_of(text) if item["unit_kind"] == "artigo"}
    assert by_ref["Art. 5º"]["amendment"] is True
    assert by_ref["Art. 5º"]["target_article"] == "Art. 75"
    assert list(by_ref) == ["Art. 5º", "Art. 6º"]
