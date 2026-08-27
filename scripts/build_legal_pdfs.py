import html
import json
import os
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "pdfs"
PDF_DIR.mkdir(exist_ok=True)
STAMP = os.getenv("RAG_CORPUS_STAMP", "27082026")
RETRIEVED = date.today().isoformat()

# Fonte -> título -> jurisdição -> tipo -> papel -> URL
SOURCES = [
    ("Lei_14133_2021_Texto_Compilado", "Lei nº 14.133/2021 — Licitações e Contratos Administrativos", "federal", "lei", "norma", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm"),
    ("Decreto_12807_2025_Valores_L14133", "Decreto nº 12.807/2025 — atualização dos valores da Lei nº 14.133/2021", "federal", "decreto", "norma", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/d12807.htm"),
    ("LINDB_DL4657_1942_Texto_Compilado", "Decreto-Lei nº 4.657/1942 — LINDB", "federal", "decreto_lei", "norma", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del4657compilado.htm"),
    ("DecretoLei_200_1967_Texto_Atualizado", "Decreto-Lei nº 200/1967 — Organização da Administração Federal", "federal", "decreto_lei", "norma", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del0200.htm"),
    ("Lei_9784_1999_Texto_Compilado", "Lei nº 9.784/1999 — Processo Administrativo Federal", "federal", "lei", "norma", "https://www.planalto.gov.br/ccivil_03/leis/l9784.htm"),
    ("Lei_8429_1992_Texto_Compilado", "Lei nº 8.429/1992 — Improbidade Administrativa", "federal", "lei", "norma", "https://www.planalto.gov.br/ccivil_03/leis/l8429.htm"),
    ("Lei_12846_2013_Texto_Compilado", "Lei nº 12.846/2013 — Lei Anticorrupção", "federal", "lei", "norma", "https://planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12846.htm"),
    ("Decreto_11129_2022_Regulamento_Anticorrupcao", "Decreto nº 11.129/2022 — Regulamento da Lei Anticorrupção", "federal", "decreto", "norma", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/decreto/d11129.htm"),
    ("Lei_12527_2011_Texto_Compilado", "Lei nº 12.527/2011 — Lei de Acesso à Informação", "federal", "lei", "norma", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm"),
    ("Lei_13709_2018_Texto_Compilado", "Lei nº 13.709/2018 — LGPD", "federal", "lei", "norma", "https://planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm"),
    ("Lei_13460_2017_Texto_Compilado", "Lei nº 13.460/2017 — Participação, proteção e defesa do usuário do serviço público", "federal", "lei", "norma", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2017/lei/l13460.htm"),
    ("Lei_14129_2021_Texto_Compilado", "Lei nº 14.129/2021 — Governo Digital", "federal", "lei", "norma", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14129.htm"),
    ("Lei_13303_2016_Texto_Compilado", "Lei nº 13.303/2016 — Estatuto das Empresas Estatais", "federal", "lei", "norma", "https://planalto.gov.br/ccivil_03/_ato2015-2018/2016/lei/l13303.htm"),
    ("Lei_8987_1995_Texto_Compilado", "Lei nº 8.987/1995 — Concessões e Permissões", "federal", "lei", "norma", "https://planalto.gov.br/ccivil_03/leis/l8987cons.htm"),
    ("Lei_11079_2004_Texto_Compilado", "Lei nº 11.079/2004 — Parcerias Público-Privadas", "federal", "lei", "norma", "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l11079.htm"),
    ("Lei_Complementar_101_2000_Texto_Atualizado", "Lei Complementar nº 101/2000 — Lei de Responsabilidade Fiscal", "federal", "lei_complementar", "norma", "https://www2.camara.leg.br/legin/fed/leicom/2000/leicomplementar-101-4-maio-2000-351480-normaatualizada-pl.html"),
    ("Lei_4320_1964_Texto_Compilado", "Lei nº 4.320/1964 — Normas Gerais de Direito Financeiro", "federal", "lei", "norma", "https://www.planalto.gov.br/ccivil_03/leis/l4320compilado.htm"),
    ("SP_Constituicao_Estadual_Texto_Atualizado", "Constituição do Estado de São Paulo — texto atualizado", "estadual_sp", "constituicao_estadual", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/constituicao/1989/compilacao-constituicao-0-05.10.1989.html"),
    ("SP_Lei_10177_1998_Processo_Administrativo", "Lei estadual SP nº 10.177/1998 — Processo Administrativo", "estadual_sp", "lei", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/lei/1998/compilacao-lei-10177-30.12.1998.html"),
    ("SP_Lei_Complementar_709_1993_TCESP", "Lei Complementar SP nº 709/1993 — Lei Orgânica do TCESP", "estadual_sp", "lei_complementar", "norma", "https://www.al.sp.gov.br/norma/?id=16279"),
    ("SP_Decreto_67608_2023_Transicao", "Decreto SP nº 67.608/2023 — transição para a Lei nº 14.133", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67608-27.03.2023.html"),
    ("SP_Decreto_67689_2023_PCA", "Decreto SP nº 67.689/2023 — Plano de Contratações Anual", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67689-03.05.2023.html"),
    ("SP_Decreto_67885_2023_Transicao", "Decreto SP nº 67.885/2023 — Regime de transição", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67885-15.08.2023.html"),
    ("SP_Decreto_67888_2023_PesquisaPrecos", "Decreto SP nº 67.888/2023 — Pesquisa de preços e valor estimado", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67888-17.08.2023.html"),
    ("SP_Decreto_67985_2023_BensLuxo", "Decreto SP nº 67.985/2023 — Bens e serviços de luxo", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67985-27.09.2023.html"),
    ("SP_Decreto_68017_2023_ETP", "Decreto SP nº 68.017/2023 — Estudo Técnico Preliminar", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68017-11.10.2023.html"),
    ("SP_Decreto_68021_2023_Catalogo", "Decreto SP nº 68.021/2023 — Catálogo eletrônico de padronização", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68021-11.10.2023.html"),
    ("SP_Decreto_68185_2023_TR", "Decreto SP nº 68.185/2023 — Termo de Referência", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68185-11.12.2023.html"),
    ("SP_Decreto_68220_2023_Agentes", "Decreto SP nº 68.220/2023 — Agente de contratação, gestores e fiscais", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68220-15.12.2023.html"),
    ("SP_Decreto_68304_2024_ContratacaoDireta", "Decreto SP nº 68.304/2024 — Contratação direta eletrônica", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2024/decreto-68304-09.01.2024.html"),
    ("SP_Decreto_68422_2024_Leilao", "Decreto SP nº 68.422/2024 — Leilão eletrônico", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2024/decreto-68422-02.04.2024.html"),
    ("SP_Decreto_69588_2025_PAR_Anticorrupcao", "Decreto SP nº 69.588/2025 — responsabilização administrativa de pessoas jurídicas", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2025/decreto-69588-09.06.2025.html"),
    ("SP_Decreto_69861_2025_Integridade", "Decreto SP nº 69.861/2025 — avaliação de programas de integridade", "estadual_sp", "decreto", "norma", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2025/decreto-69861-11.09.2025.html"),
    ("SP_Resolucao_SGGD_34_2026_Marketplace", "Resolução SGGD nº 34/2026 — Marketplace.SP e credenciamento", "estadual_sp", "resolucao", "norma", "https://compras.sp.gov.br/resolucao-sggd-no-34-de-29-de-julho-de-2026/"),
]

HEADERS = {"User-Agent": "rag-licitacoes-document-builder/3.0"}
NAV_NOISE = {"[Input]", "[Button: Pesquisar]", "expand_more", "collapse"}
LEGAL_MARKER = re.compile(r"\b(?:Art\.?|Artigo|LEI|DECRETO|RESOLUÇÃO|CAPÍTULO|TÍTULO|SEÇÃO|SUBSEÇÃO|ANEXO)\b", re.I)


def clean_html(raw: str) -> list[str]:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form"]):
        tag.decompose()
    for tag in soup.find_all(["del", "s", "strike"]):
        tag.decompose()
    for tag in soup.find_all(style=True):
        if "line-through" in tag.get("style", "").replace(" ", "").lower():
            tag.decompose()
    root = soup.find("main") or soup.find(id=re.compile(r"conteudo|content|corpo", re.I)) or soup.body or soup
    lines: list[str] = []
    for line in root.get_text("\n", strip=True).splitlines():
        line = html.unescape(re.sub(r"\s+", " ", line)).strip()
        if not line or line in NAV_NOISE or len(line) > 5000:
            continue
        lines.append(line)
    return lines


def validate_source(lines: list[str], document_type: str, title: str) -> None:
    text = "\n".join(lines)
    if len(text) < 1200:
        raise RuntimeError(f"fonte retornou apenas {len(text)} caracteres")
    if document_type in {"lei", "lei_complementar", "decreto", "decreto_lei", "resolucao", "constituicao_estadual"}:
        if not LEGAL_MARKER.search(text):
            raise RuntimeError(f"conteúdo não parece íntegra normativa: {title}")
        if text.lower().count("art") < 3 and document_type != "resolucao":
            raise RuntimeError(f"conteúdo normativo suspeito/incompleto: {title}")


def build_pdf(stem: str, title: str, jurisdiction: str, document_type: str, role: str, url: str, lines: list[str]) -> Path:
    out = PDF_DIR / f"{stem}.{STAMP}.pdf"
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleLegal", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=15, leading=19, alignment=TA_CENTER, spaceAfter=8)
    meta_style = ParagraphStyle("MetaLegal", parent=styles["Normal"], fontSize=8, leading=10, spaceAfter=3)
    body_style = ParagraphStyle("BodyLegal", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.2, leading=10.5, spaceAfter=3)
    doc = SimpleDocTemplate(str(out), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=15 * mm, bottomMargin=15 * mm, title=title, author="rag-licitacoes")
    story = [
        Paragraph(html.escape(title), title_style),
        Paragraph(f"Fonte oficial: {html.escape(url)}", meta_style),
        Paragraph(f"jurisdicao={jurisdiction} | tipo_documento={document_type} | source_role={role} | retrieved_at={RETRIEVED} | stamp={STAMP}", meta_style),
        Spacer(1, 6),
    ]
    for line in lines:
        if re.match(r"^(LEI|LEI COMPLEMENTAR|DECRETO(?:-LEI)?|RESOLUÇÃO|CAPÍTULO|TÍTULO|SEÇÃO|SUBSEÇÃO|ANEXO)\b", line, re.I):
            story.append(Spacer(1, 4))
            story.append(Paragraph(f"<b>{html.escape(line)}</b>", body_style))
        else:
            story.append(Paragraph(html.escape(line), body_style))
    doc.build(story)
    sidecar = out.with_suffix(".json")
    sidecar.write_text(json.dumps({
        "jurisdicao": jurisdiction,
        "esfera": "estadual" if jurisdiction == "estadual_sp" else "federal",
        "tipo_documento": document_type,
        "source_role": role,
        "status": "vigente",
        "fonte_oficial": url,
        "retrieved_at": RETRIEVED,
        "data_versao": f"{STAMP[4:]}-{STAMP[2:4]}-{STAMP[:2]}",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> None:
    session = requests.Session()
    session.headers.update(HEADERS)
    failures: list[tuple[str, str, str]] = []
    generated = 0
    for stem, title, jurisdiction, document_type, role, url in SOURCES:
        try:
            response = session.get(url, timeout=60)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding
            lines = clean_html(response.text)
            validate_source(lines, document_type, title)
            out = build_pdf(stem, title, jurisdiction, document_type, role, url, lines)
            generated += 1
            print(f"OK {out.name}: {out.stat().st_size} bytes; {len(chr(10).join(lines))} chars")
        except Exception as exc:
            failures.append((stem, url, str(exc)))
            print(f"WARN {stem}: {exc}")
    print(f"Gerados: {generated}/{len(SOURCES)}")
    if failures:
        print("Falhas:")
        for stem, url, error in failures:
            print(f" - {stem}: {error} ({url})")
    if generated == 0 or failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
