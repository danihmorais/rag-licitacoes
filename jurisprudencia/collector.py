from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config
from .schema import JurisprudenciaRecord

DEFAULT_QUERY = "licitação"
TRIBUNALS = ("tcu", "tcesp", "stj", "stf")
HEADERS = {"User-Agent": "rag-licitacoes-jurisprudencia/1.0 (+https://github.com/danihmorais/rag-licitacoes)", "Accept": "text/html,application/xhtml+xml,application/json,application/pdf;q=0.9,*/*;q=0.8"}


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=4, connect=4, read=4, status=4, backoff_factor=1.5, status_forcelist=(408, 425, 429, 500, 502, 503, 504), allowed_methods=frozenset({"GET", "POST", "HEAD"}), respect_retry_after_header=True)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter); session.mount("http://", adapter); session.headers.update(HEADERS)
    return session


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def page_text(raw: bytes) -> str:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "aside"]): tag.decompose()
    return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if clean_text(line))


def pdf_text(data: bytes) -> str:
    path = config.SOURCE_CACHE_DIR / ".jurisprudencia_tmp.pdf"
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    try: return "\n\f\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages).strip()
    finally: path.unlink(missing_ok=True)


def fetch(session: requests.Session, url: str, *, method: str = "GET", **kwargs: Any):
    response = session.request(method, url, timeout=(20, 90), allow_redirects=True, **kwargs)
    response.raise_for_status(); content_type = (response.headers.get("content-type") or "").lower(); final = response.url
    if "application/pdf" in content_type or final.lower().split("?", 1)[0].endswith(".pdf") or response.content.startswith(b"%PDF"):
        return "pdf", final, response.content
    response.encoding = response.apparent_encoding or response.encoding
    return "html", final, response.content


def _first_value(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""): return str(value).strip()
    return ""


def _as_list(*values: str) -> list[str]:
    return [value for value in (clean_text(v) for v in values) if value]


def _query_matches(query: str, *fields: str) -> bool:
    if not query.strip(): return True
    haystack = clean_text(" ".join(fields)).casefold()
    terms = [term for term in re.findall(r"[\wÀ-ÿ]+", query.casefold()) if len(term) >= 3]
    return not terms or any(term in haystack for term in terms)


class JurisprudenciaAdapter(ABC):
    tribunal: str
    def __init__(self, session: requests.Session) -> None: self.session = session
    @abstractmethod
    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]: raise NotImplementedError


class TCUAdapter(JurisprudenciaAdapter):
    tribunal = "TCU"
    endpoint = "https://dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos"

    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        records=[]; start=0; page_size=min(max(limit*2,20),100)
        while len(records)<limit and start<5000:
            response=self.session.get(self.endpoint,params={"inicio":start,"quantidade":page_size},timeout=(20,90)); response.raise_for_status(); payload=response.json(); rows=payload
            if isinstance(payload,dict):
                for key in ("data","items","acordaos","resultados"):
                    if isinstance(payload.get(key),list): rows=payload[key]; break
            if not isinstance(rows,list) or not rows: break
            for row in rows:
                if not isinstance(row,dict): continue
                title=_first_value(row,"titulo","sumario","ementa")
                if not _query_matches(query,title,_first_value(row,"area"),_first_value(row,"tema"),_first_value(row,"subtema")): continue
                number=_first_value(row,"numeroAcordao","numeroDecisao"); process=_first_value(row,"numeroProcessoFormatado","numeroProcesso","processo") or _first_value(row,"key") or number
                record=JurisprudenciaRecord(tribunal="TCU",numero_processo=process,orgao_julgador=_first_value(row,"colegiado"),relator=_first_value(row,"relator"),data=_first_value(row,"dataSessao","dataSessaoFormatada"),ementa=_first_value(row,"sumario","ementa","titulo"),assunto=_as_list(_first_value(row,"area"),_first_value(row,"tema"),_first_value(row,"subtema")),url_oficial=_first_value(row,"urlAcordao","urlArquivo"),tipo_decisao=_first_value(row,"tipo"),numero_decisao=number,origem="TCU — dados abertos de acórdãos",situacao=_first_value(row,"situacao"))
                if with_content:
                    pdf_url=_first_value(row,"urlArquivoPDF","urlArquivo")
                    if pdf_url:
                        try:
                            kind,final,raw=fetch(self.session,pdf_url)
                            if kind=="pdf": record.inteiro_teor=pdf_text(raw); record.url_oficial=final
                        except Exception as exc: print(f"aviso: inteiro teor TCU indisponível para {number}: {type(exc).__name__}: {exc}")
                records.append(record)
                if len(records)>=limit: break
            if len(rows)<page_size: break
            start += len(rows)
        return records


class TCESPAdapter(JurisprudenciaAdapter):
    tribunal="TCESP"; endpoint="https://www.tce.sp.gov.br/jurisprudencia/pesquisar"
    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        params={"acao":"Executa","offset":0,"dataAutuacaoFim":"","dataAutuacaoInicio":"","exercicio":"","processo":"","quantTrechos":3,"tipoBuscaTxt":"Documento","tipoDocumento":"","_auditor":1,"_materia":1,"_relator":1,"txtExp":"","txtNenhPalvs":"","txtNumFim":"","txtNumIni":"","txtQqUma":"","txtTdPalvs":query}
        response=self.session.get(self.endpoint,params=params,timeout=(20,90)); response.raise_for_status(); soup=BeautifulSoup(response.content,"html.parser"); records=[]
        table=next((tbl for tbl in soup.find_all("table") if "N° Proc." in clean_text(tbl.get_text(" ",strip=True)) or "Nº Proc." in clean_text(tbl.get_text(" ",strip=True))),None)
        if table is None: return records
        expect_excerpt=False
        for row in table.find_all("tr"):
            cells=[clean_text(cell.get_text(" ",strip=True)) for cell in row.find_all(["th","td"])]
            if not cells: continue
            joined=" | ".join(cells)
            if joined.casefold().startswith("trechos localizados"): expect_excerpt=True; continue
            if expect_excerpt and len(cells)==1 and records:
                excerpt=cells[0]
                if excerpt and not excerpt.casefold().startswith("trechos localizados"): records[-1].ementa=excerpt
                expect_excerpt=False; continue
            if len(cells)<7 or not re.search(r"\d{2}/\d{2}/\d{4}",cells[2]): continue
            records.append(JurisprudenciaRecord(tribunal="TCESP",numero_processo=cells[1],data_autuacao=cells[2],ementa=cells[6],assunto=_as_list(cells[5],cells[6]),tipo_decisao=cells[0],origem="TCESP — Pesquisa de Jurisprudência",url_oficial=response.url,partes=_as_list(cells[3],cells[4])))
        return records[:limit]


def _label_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match=re.search(rf"(?im)^\s*{re.escape(label)}\s*[:\-]?\s*(.+)$",text)
        if match: return clean_text(match.group(1))
    return None


def _extract_process(text: str, url: str = "") -> str:
    for pattern in (r"\b(?:REsp|AREsp|AgInt no REsp|AgRg no REsp|RMS|MS|HC|RHC|AgInt|EDcl)\s+[\d.]+(?:/[A-Z]{2})?",r"\b\d{1,7}[\d.]+/[A-Z]{2}\b"):
        match=re.search(pattern,text,re.I)
        if match: return clean_text(match.group(0))
    match=re.search(r"(?:^|&)livre=([^&]+)",urlparse(url).query,re.I)
    return match.group(1) if match else ""


class STJAdapter(JurisprudenciaAdapter):
    tribunal="STJ"; endpoint="https://scon.stj.jus.br/SCON/pesquisar.jsp"
    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        params={"acao":"pesquisar","novaConsulta":"true","i":1,"b":"ACOR","livre":query,"thesaurus":"JURIDICO","tp":"P","tipo_visualizacao":"RESUMO"}
        response=self.session.get(self.endpoint,params=params,timeout=(20,90)); response.raise_for_status(); soup=BeautifulSoup(response.content,"html.parser"); records=[]; seen=set()
        for anchor in soup.find_all("a",href=True):
            absolute=urljoin(response.url,str(anchor["href"])); label=clean_text(anchor.get_text(" ",strip=True))
            if "/SCON/jurisprudencia/doc.jsp" not in absolute or not label or absolute in seen: continue
            seen.add(absolute); detail_text=""; relator=None; data=None; ementa=label
            if detail:
                try:
                    kind,final,raw=fetch(self.session,absolute)
                    if kind=="html": detail_text=page_text(raw); ementa=_label_value(detail_text,("EMENTA","Ementa")) or label; relator=_label_value(detail_text,("RELATOR","Relator")); data=_label_value(detail_text,("DATA DO JULGAMENTO","Data do julgamento","JULGAMENTO")); absolute=final
                except Exception as exc: print(f"aviso: detalhe STJ indisponível: {type(exc).__name__}: {exc}")
            records.append(JurisprudenciaRecord(tribunal="STJ",numero_processo=_extract_process(label,absolute) or label,relator=relator,data=data,ementa=ementa,assunto=["licitações/contratos"] if "licit" in label.casefold() else [],url_oficial=absolute,tipo_decisao="acórdão",origem="STJ — SCON",inteiro_teor=detail_text if with_content and detail_text else None))
            if len(records)>=limit: break
        return records


def _discover_form(soup: BeautifulSoup):
    candidates=[]
    for form in soup.find_all("form"):
        text=clean_text(form.get_text(" ",strip=True)); action=str(form.get("action") or ""); inputs=form.find_all("input")
        if "jurisprud" in text.casefold() and ("pesquis" in action.casefold() or any((str(item.get("name") or "")+" "+str(item.get("id") or "")).casefold().find("pesquis")>=0 for item in inputs)): candidates.append(form)
    return candidates[0] if candidates else None


class STFAdapter(JurisprudenciaAdapter):
    tribunal="STF"; endpoint="https://portal.stf.jus.br/jurisprudencia/"
    def search(self, query: str, limit: int, *, detail: bool = False, with_content: bool = False) -> list[JurisprudenciaRecord]:
        kind,final,raw=fetch(self.session,self.endpoint)
        if kind!="html": return []
        soup=BeautifulSoup(raw,"html.parser"); form=_discover_form(soup); result_raw=raw; result_url=final
        if form is not None:
            action=urljoin(final,str(form.get("action") or final)); method=str(form.get("method") or "get").lower(); data={}
            for field in form.find_all(["input","select","textarea"]):
                name=str(field.get("name") or "").strip()
                if not name: continue
                if field.name=="input" and str(field.get("type") or "text").lower() in {"submit","button"}: continue
                if field.name=="select":
                    option=field.find("option",selected=True) or field.find("option"); value=str(option.get("value") if option else "")
                else: value=str(field.get("value") or field.get_text() or "")
                data[name]=value
            text_field=next((field for field in form.find_all("input") if str(field.get("type") or "text").lower() in {"text","search"} and any(token in (str(field.get("name") or "")+" "+str(field.get("id") or "")).casefold() for token in ("livre","pesquisa","termo","juris"))),None)
            if text_field is not None:
                field_name=str(text_field.get("name") or "").strip(); data[field_name]=query
                try:
                    kind,result_url,result_raw=fetch(self.session,action,method="POST" if method=="post" else "GET",data=data if method=="post" else None,params=None if method=="post" else data)
                except Exception as exc: print(f"aviso: consulta STF pelo formulário falhou: {type(exc).__name__}: {exc}")
        soup=BeautifulSoup(result_raw,"html.parser"); records=[]; seen=set()
        for anchor in soup.find_all("a",href=True):
            absolute=urljoin(result_url,str(anchor["href"])); label=clean_text(anchor.get_text(" ",strip=True))
            if not label or absolute in seen or not ("/jurisprudencia/" in absolute and any(token in absolute.casefold() for token in ("detalhe","documento","inteiro","pesquisar"))): continue
            seen.add(absolute); records.append(JurisprudenciaRecord(tribunal="STF",numero_processo=_extract_process(label,absolute) or label,ementa=label,url_oficial=absolute,tipo_decisao="jurisprudência",origem="STF — Portal de Jurisprudência"))
            if len(records)>=limit: break
        return records


def adapters(session): return {"tcu":TCUAdapter(session),"tcesp":TCESPAdapter(session),"stj":STJAdapter(session),"stf":STFAdapter(session)}


def save_record(record: JurisprudenciaRecord, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True,exist_ok=True); record.retrieved_at=record.retrieved_at or datetime.now(timezone.utc).isoformat(); record.version_sha256=record.version_sha256 or record.calculate_version_sha256()
    source_id={"TCU":"tcu-dados-jurisprudencia","TCESP":"tcesp","STJ":"stj-jurisprudencia","STF":"stf-jurisprudencia"}.get(record.tribunal,f"{record.tribunal.lower()}-jurisprudencia")
    basename=f"jurisprudencia__{record.tribunal.lower()}__{record.document_key}__{record.version_sha256[:10]}"; text_path=output_dir/f"{basename}.txt"; json_path=output_dir/f"{basename}.json"; text_path.write_text(record.to_index_text(),encoding="utf-8")
    metadata={**record.to_dict(),"document_id":basename,"source_id":source_id,"parent_source_id":source_id,"source_role":"jurisprudencia_controle" if record.tribunal in {"TCU","TCESP"} else "jurisprudencia","jurisdicao":"estadual_sp" if record.tribunal=="TCESP" else "federal","esfera":"estadual" if record.tribunal=="TCESP" else "federal","orgao":record.tribunal,"tipo_documento":"jurisprudencia","authority_level":2,"status":"jurisprudencia","fonte_oficial":record.url_oficial,"fonte_host":urlparse(record.url_oficial).netloc if record.url_oficial else None,"version_sha256":record.version_sha256}
    json_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return text_path


def collect(tribunals,query,limit,*,detail=False,with_content=False,output_dir=None):
    output_dir=output_dir or (config.SOURCE_CACHE_DIR/"jurisprudencia"); session=make_session(); source_adapters=adapters(session); output=[]
    for tribunal in tribunals:
        try: records=source_adapters[tribunal].search(query,limit,detail=detail,with_content=with_content)
        except Exception as exc: print(f"FAIL {tribunal}: {type(exc).__name__}: {exc}"); continue
        for record in records: save_record(record,output_dir); output.append(record)
        print(f"OK {tribunal}: {len(records)} registros para {query!r}")
    return output


def main() -> int:
    parser=argparse.ArgumentParser(description="Coleta jurisprudência oficial em formato estruturado para o RAG."); parser.add_argument("--tribunais",default=",".join(TRIBUNALS)); parser.add_argument("--query",default=DEFAULT_QUERY); parser.add_argument("--limit",type=int,default=25); parser.add_argument("--detail",action="store_true"); parser.add_argument("--with-content",action="store_true"); parser.add_argument("--output-dir",type=Path,default=None); args=parser.parse_args()
    tribunals=[item.strip().lower() for item in args.tribunais.split(",") if item.strip()]; unknown=[item for item in tribunals if item not in TRIBUNALS]
    if unknown: parser.error("tribunais inválidos: "+", ".join(unknown))
    config.ensure_directories(); records=collect(tribunals,args.query,max(1,args.limit),detail=args.detail,with_content=args.with_content,output_dir=args.output_dir); print(f"Total de registros coletados: {len(records)}"); return 0 if records else 1

if __name__ == "__main__": raise SystemExit(main())
