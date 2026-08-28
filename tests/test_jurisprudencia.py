from pathlib import Path

from jurisprudencia.collector import STJAdapter, TCESPAdapter, TCUAdapter, _discover_form, save_record
from jurisprudencia.schema import JurisprudenciaRecord


class FakeResponse:
    def __init__(self, payload, *, content_type="application/json", url="https://example.test"):
        self._payload = payload
        self.headers = {"content-type": content_type}
        self.content = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
        self.url = url
        self.apparent_encoding = "utf-8"
        self.encoding = "utf-8"

    def raise_for_status(self): return None
    def json(self): return self._payload


class FakeSession:
    def __init__(self, responses): self.responses = iter(responses)
    def get(self, *args, **kwargs): return next(self.responses)


def test_tcu_adapter_normalizes_official_acordao_payload():
    session = FakeSession([FakeResponse([{"key":"abc-123","tipo":"Acórdão","numeroAcordao":"1234/2026","colegiado":"Plenário","dataSessao":"27/08/2026","relator":"Ministro X","situacao":"Publicado","sumario":"Licitação e contratação pública.","urlAcordao":"https://portal.tcu.gov.br/acordao/abc","urlArquivo":"https://portal.tcu.gov.br/acordao/abc","urlArquivoPDF":"https://portal.tcu.gov.br/acordao/abc.pdf","area":"Licitação","tema":"Contratação","subtema":"Edital"}])])
    records = TCUAdapter(session).search("licitação", 1)
    assert len(records) == 1 and records[0].numero_decisao == "1234/2026" and records[0].orgao_julgador == "Plenário"


def test_tcesp_adapter_parses_result_table():
    html = '''<html><body><table><tr><th>Doc.</th><th>N° Proc.</th><th>Autuação</th><th>Parte 1</th><th>Parte 2</th><th>Matéria</th><th>Objeto</th><th>Exercício</th></tr><tr><td>Relatório / Voto</td><td>5600/989/25</td><td>17/03/2025</td><td>EMPRESA A</td><td>PREFEITURA B</td><td>LICITAÇÃO</td><td>Exame de edital</td><td>2025</td></tr><tr><td colspan="8">Trechos localizados no documento:</td></tr><tr><td colspan="8">A exigência de qualificação técnica deve ser pertinente e proporcional.</td></tr></table></body></html>'''.encode("utf-8")
    records = TCESPAdapter(FakeSession([FakeResponse(html, content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/pesquisar")])).search("licitação", 1)
    assert len(records) == 1 and records[0].numero_processo == "5600/989/25" and "qualificação técnica" in records[0].ementa


def test_record_version_is_stable_and_cache_has_structured_metadata(tmp_path: Path):
    record = JurisprudenciaRecord(tribunal="TCU", numero_processo="123/2026", numero_decisao="456/2026", orgao_julgador="Plenário", ementa="Licitação.", url_oficial="https://example.test/acordao/456")
    assert record.calculate_version_sha256() == record.calculate_version_sha256()
    path = save_record(record, tmp_path); data = path.with_suffix(".json").read_text(encoding="utf-8")
    assert path.exists() and '"source_role": "jurisprudencia_controle"' in data and '"version_sha256":' in data


def test_stj_adapter_finds_official_acordao_links():
    html = b'<html><body><a href="/SCON/jurisprudencia/doc.jsp?livre=123456">REsp 1.234.567/SP</a></body></html>'
    records = STJAdapter(FakeSession([FakeResponse(html, content_type="text/html", url="https://scon.stj.jus.br/SCON/pesquisar.jsp?livre=licitação")])).search("licitação", 1)
    assert len(records) == 1 and records[0].tribunal == "STJ" and "1.234.567/SP" in records[0].numero_processo


def test_stf_form_is_discovered_without_hardcoding_input_name():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup('<form action="/jurisprudencia/pesquisa.asp" method="get"><label>Pesquisa por jurisprudência</label><input name="pesquisaLivre" type="text"></form>', "html.parser")
    assert _discover_form(soup) is not None


def test_session_id_does_not_create_a_new_document_version():
    a = JurisprudenciaRecord(tribunal="TCESP", numero_processo="1/989/26", url_oficial="https://www.tce.sp.gov.br/jurisprudencia/pesquisar;jsessionid=ABC123?acao=Executa")
    b = JurisprudenciaRecord(tribunal="TCESP", numero_processo="1/989/26", url_oficial="https://www.tce.sp.gov.br/jurisprudencia/pesquisar;jsessionid=XYZ987?acao=Executa")
    assert a.calculate_version_sha256() == b.calculate_version_sha256()
