from __future__

import html
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "pdfs"
PDF_DIR.mkdir(exist_ok=True)
STAMP = "26082026"
RETRIEVED = date.today().isoformat()

SOURCES = [
    ("Lei_14133_2021_Texto_Compilado", "Lei nº 14.133/2021 — Licitações e Contratos Administrativos", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm"),
    ("Decreto_12807_2025_Valores_L14133", "Decreto nº 12.807/2025 — valores atualizados da Lei nº 14.133/2021", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/d12807.htm"),
    ("LINDB_DL4657_1942_Texto_Compilado", "Decreto-Lei nº 4.657/1942 — LINDB", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del4657compilado.htm"),
    ("Lei_9784_1999_Texto_Compilado", "Lei nº 9.784/1999 — Processo Administrativo Federal", "https://www.planalto.gov.br/ccivil_03/leis/l9784.htm"),
    ("Lei_8429_1992_Texto_Compilado", "Lei nº 8.429/1992 — Improbidade Administrativa", "https://www.planalto.gov.br/ccivil_03/leis/l8429.htm"),
    ("Lei_12846_2013_Texto_Compilado", "Lei nº 12.846/2013 — Lei Anticorrupção", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12846.htm"),
    ("Lei_12527_2011_Texto_Compilado", "Lei nº 12.527/2011 — Acesso à Informação", "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm"),
    ("Lei_13709_2018_Texto_Compilado", "Lei nº 13.709/2018 — LGPD", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"),
    ("Lei_8987_1995_Texto_Compilado", "Lei nº 8.987/1995 — Concessões e Permissões", "https://www.planalto.gov.br/ccivil_03/leis/l8987compilada.htm"),
    ("Lei_11079_2004_Texto_Compilado", "Lei nº 11.079/2004 — Parcerias Público-Privadas", "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l11079.htm"),
    ("Lei_14129_2021_Texto_Compilado", "Lei nº 14.129/2021 — Governo Digital", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14129.htm"),
    ("SP_Lei_10177_1998_Processo_Administrativo", "Lei estadual SP nº 10.177/1998 — Processo Administrativo", "https://www.al.sp.gov.br/repositorio/legislacao/lei/1998/lei-10177-30.12.1998.html"),
    ("SP_Decreto_67608_2023_Transicao", "Decreto SP nº 67.608/2023 — transição para a Lei nº 14.133", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67608-27.03.2023.html"),
    ("SP_Decreto_67689_2023_PCA", "Decreto SP nº 67.689/2023 — Plano de Contratações Anual", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67689-03.05.2023.html"),
    ("SP_Decreto_67885_2023_Transicao", "Decreto SP nº 67.885/2023 — regime de transição", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67885-15.08.2023.html"),
    ("SP_Decreto_67888_2023_PesquisaPrecos", "Decreto SP nº 67.888/2023 — valor estimado/pesquisa de preços", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67888-17.08.2023.html"),
    ("SP_Decreto_67985_2023_BensLuxo", "Decreto SP nº 67.985/2023 — bens de luxo", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-67985-27.09.2023.html"),
    ("SP_Decreto_68021_2023_Catalogo", "Decreto SP nº 68.021/2023 — catálogo eletrônico de padronização", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68021-11.10.2023.html"),
    ("SP_Decreto_68185_2023_TR", "Decreto SP nº 68.185/2023 — Termo de Referência", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68185-11.12.2023.html"),
    ("SP_Decreto_68220_2023_Agentes", "Decreto SP nº 68.220/2023 — agente de contratação, gestores e fiscais", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2023/decreto-68220-15.12.2023.html"),
    ("SP_Decreto_68304_2024_ContratacaoDireta", "Decreto SP nº 68.304/2024 — contratação direta eletrônica", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2024/decreto-68304-09.01.2024.html"),
    ("SP_Decreto_68422_2024_Leilao", "Decreto SP nº 68.422/2024 — leilão eletrônico", "https://www.al.sp.gov.br/repositorio/legislacao/decreto/2024/decreto-68422-02.04.2024.html"),
    ("SP_Resolucao_SGGD_34_2026_Marketplace", "Resolução SGGD nº 34/2026 — Marketplace.SP e credenciamento", "https://compras.sp.gov.br/resolucao-sggd-no-34-de-29-de-julho-de-2026/"),
]

HEADERS = {"User-Agent": "rag-licitacoes-document-builder/1.0"}


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
    text = root.get_text("\n", strip=True)
    lines = []
    for line in text.splitlines():
        line = html.unescape(re.sub(r"\s+", " ", line)).strip()
        if not line or line in {"[Input]", "[Button: Pesquisar]"}:
            continue
        lines.append(line)
    return lines


def build_pdf(stem: str, title: str, url: str, lines: list[str]) -> Path:
    out = PDF_DIR / f"{stem}.{STAMP}.pdf"
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleLegal", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=15, leading=19, alignment=TA_CENTER, spaceAfter=8)
    meta_style = ParagraphStyle("MetaLegal", parent=styles["Normal"], fontSize=8, leading=10, textColor="#444444", spaceAfter=3)
    body_style = ParagraphStyle("BodyLegal", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.2, leading=10.5, spaceAfter=3)
    doc = SimpleDocTemplate(str(out), pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=15*mm, bottomMargin=15*mm, title=title, author="rag-licitacoes")
    story = [Paragraph(html.escape(title), title_style), Paragraph(f"Fonte oficial: {html.escape(url)}", meta_style), Paragraph(f"Conteúdo obtido em: {RETRIEVED}. Nome do arquivo com carimbo solicitado: .{STAMP}", meta_style), Spacer(1, 6)]
    for line in lines:
        if re.match(r"^(LEI|DECRETO|DECRETO-LEI|RESOLUÇÃO|CAPÍTULO|TÍTULO|SEÇÃO|SUBSEÇÃO|ANEXO)\b", line, re.I):
            story.append(Spacer(1, 4))
            story.append(Paragraph(f"<b>{html.escape(line)}</b>", body_style))
        else:
            story.append(Paragraph(html.escape(line), body_style))
    doc.build(story)
    return out


def main():
    session = requests.Session()
    session.headers.update(HEADERS)
    failures = []
    for stem, title, url in SOURCES:
        try:
            response = session.get(url, timeout=60)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding
            lines = clean_html(response.text)
            if len("\n".join(lines)) < 1000:
                raise RuntimeError("fonte retornou conteúdo insuficiente")
            out = build_pdf(stem, title, url, lines)
            print(f"OK {out.name}: {out.stat().st_size} bytes")
        except Exception as exc:
            failures.append((stem, url, str(exc)))
            print(f"WARN {stem}: {exc}")
    if failures:
        print("Falhas:")
        for item in failures:
            print(" -", item)
    if not list(PDF_DIR.glob("*.pdf")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
