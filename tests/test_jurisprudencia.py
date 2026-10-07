from pathlib import Path

import pytest

from jurisprudencia.collector import STJAdapter, STFAdapter, TCESPAdapter, TCUAdapter, TJSPAdapter, TRIBUNALS, _discover_form, _query_matches, save_record
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
    def request(self, method, *args, **kwargs): return self.get(*args, **kwargs)


def test_tcu_adapter_queries_rest_and_bulletin_sources():
    bulletin = (
        "KEY,ENUNCIADO,REFERENCIA,TEXTOACORDAO,TITULO\n"
        'B1,"Boletim também contém entendimento sobre licitação.","Lei 14.133/2021","Acórdão 123/2026","Boletim de Jurisprudência 600"\n'
    ).encode("utf-8")
    responses = [
        FakeResponse({
            "quantidadeEncontrada": 1,
            "documentos": [{
                "KEY": "4802024",
                "NUMACORDAO": "480",
                "ANOACORDAO": "2024",
                "COLEGIADO": "Plenário",
                "DTSESSAO": "27/08/2024",
                "RELATOR": "Ministro X",
                "SITUACAO": "Publicado",
                "SUMARIO": "Licitação e contratação pública.",
                "AREA": "Licitação", "TEMA": "Contratação", "SUBTEMA": "Edital"
            }]
        }),
        FakeResponse(bulletin, content_type="text/csv", url=TCUAdapter.bulletin_csv_url),
    ]

    class CaptureSession(FakeSession):
        def __init__(self, responses):
            super().__init__(responses)
            self.calls = []

        def get(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return super().get(*args, **kwargs)

    session = CaptureSession(responses)
    records = TCUAdapter(session).search("licitação", 2)

    assert len(records) == 2
    assert records[0].tribunal == "TCU"
    assert records[0].numero_decisao == "480/2024"
    assert records[0].url_oficial.endswith("/4802024")
    assert records[1].tipo_documento == "boletim_jurisprudencia"
    assert len(session.calls) == 2
    assert session.calls[0][0][0] == TCUAdapter.search_endpoint
    assert session.calls[1][0][0] == TCUAdapter.bulletin_csv_url



def test_tcu_adapter_uses_bulletin_csv_when_rest_returns_no_records():
    bulletin = (
        "KEY,ENUNCIADO,REFERENCIA,TEXTOACORDAO,TITULO\n"
        'B1,"Licitação exige planejamento adequado.","Lei 14.133/2021","Acórdão 123/2026","Boletim de Jurisprudência 600"\n'
    ).encode("utf-8")
    session = FakeSession([
        FakeResponse({"quantidadeEncontrada": 0, "documentos": []}),
        FakeResponse(bulletin, content_type="text/csv", url=TCUAdapter.bulletin_csv_url),
    ])

    records = TCUAdapter(session).search("licitação", 1)

    assert len(records) == 1
    assert records[0].tribunal == "TCU"
    assert records[0].tipo_documento == "boletim_jurisprudencia"
    assert records[0].numero_decisao == "123/2026"
    assert records[0].url_oficial == TCUAdapter.bulletin_csv_url
    assert records[0].origem == "TCU — Boletim de Jurisprudência (dados abertos)"


def test_tcesp_adapter_parses_result_table():
    html = '''<html><body><table><tbody>
    <tr class="borda-superior"><td>Relatório / Voto</td><td>5600/989/25</td><td>17/03/2025</td><td>EMPRESA A</td><td>PREFEITURA B</td><td>LICITAÇÃO</td><td>Exame de edital</td><td>2025</td></tr>
    <tr><td colspan="8"><ul><li>licitação e qualificação técnica devem ser pertinentes e proporcionais.</li></ul></td></tr>
    </tbody></table></body></html>'''.encode("utf-8")
    records = TCESPAdapter(FakeSession([FakeResponse(html, content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/pesquisar")])).search("licitação", 1)
    assert len(records) == 1
    assert records[0].numero_processo == "5600/989/25"
    assert records[0].ementa == "licitação e qualificação técnica devem ser pertinentes e proporcionais."


def test_tcesp_adapter_paginates_beyond_first_page():
    def result(process):
        return f'''<html><body>
        <h3>Foram encontrados 25 registros</h3>
        <table>
          <tr><th>Doc.</th><th>N° Proc.</th><th>Autuação</th><th>Parte 1</th><th>Parte 2</th><th>Matéria</th><th>Objeto</th><th>Exercício</th></tr>
          <tr><td>Acórdão</td><td>{process}</td><td>17/03/2025</td><td>EMPRESA</td><td>PREFEITURA</td><td>CONTRATO</td><td>Licitação</td><td>2025</td></tr>
        </table>
        </body></html>'''.encode("utf-8")

    class CaptureSession(FakeSession):
        def __init__(self, responses):
            super().__init__(responses)
            self.calls = []

        def get(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return super().get(*args, **kwargs)

    session = CaptureSession([
        FakeResponse(result("1000/989/25"), content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/pesquisar"),
        FakeResponse(result("1001/989/25"), content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/pesquisar"),
        FakeResponse(result("1002/989/25"), content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/pesquisar"),
    ])
    records = TCESPAdapter(session).search("licitação", 3)

    assert [record.numero_processo for record in records] == [
        "1000/989/25", "1001/989/25", "1002/989/25"
    ]
    assert [call[1]["params"][7][1] for call in session.calls] == ["0", "10", "20"]


def test_tcesp_adapter_accepts_current_result_rows_without_css_class():
    html = '''<html><body>
    <h3>Foram encontrados 191 registros</h3>
    <table>
      <tr><th>Doc.</th><th>N° Proc.</th><th>Autuação</th><th>Parte 1</th><th>Parte 2</th><th>Matéria</th><th>Objeto</th><th>Exercício</th></tr>
      <tr><td>Acórdão</td><td><a href="/jurisprudencia/exibir?codigo=560098925">5600/989/25</a></td><td>17/03/2025</td><td>EMPRESA A</td><td>PREFEITURA B</td><td>CONTRATO</td><td>Licitação e qualificação técnica</td><td>2025</td></tr>
      <tr><td colspan="8"><div>Trechos localizados no documento:</div><ul><li>licitação e qualificação técnica devem ser pertinentes e proporcionais.</li></ul></td></tr>
    </table>
    </body></html>'''.encode("utf-8")
    records = TCESPAdapter(FakeSession([
        FakeResponse(html, content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/pesquisar")
    ])).search("licitação", 1)
    assert len(records) == 1
    assert records[0].numero_processo == "5600/989/25"
    assert records[0].url_oficial == "https://www.tce.sp.gov.br/jurisprudencia/exibir?codigo=560098925"
    assert records[0].ementa == "licitação e qualificação técnica devem ser pertinentes e proporcionais."

def test_tcesp_rendered_fallback_does_not_emit_false_partial_warning(monkeypatch, capsys):
    html = '''<html><body>
    <h3>Foram encontrados 121068 registros</h3>
    <div class="resultado">Resultado renderizado pelo navegador.</div>
    </body></html>'''.encode("utf-8")
    record = JurisprudenciaRecord(
        tribunal="TCESP",
        numero_processo="5600/989/25",
        data_autuacao="17/03/2025",
        ementa="Licitação e qualificação técnica.",
        tipo_decisao="Jurisprudência",
        origem="TCESP — Pesquisa de Jurisprudência",
        url_oficial="https://www.tce.sp.gov.br/jurisprudencia/exibir?codigo=560098925",
    )
    adapter = TCESPAdapter(FakeSession([
        FakeResponse(html, content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/pesquisar")
    ]))
    monkeypatch.setattr(adapter, "_browser_records", lambda *args, **kwargs: [record])
    records = adapter.search("licitação", 1)
    captured = capsys.readouterr().out

    assert len(records) == 1
    assert records[0].numero_processo == "5600/989/25"
    assert "potencialmente parcial" not in captured


def test_tcesp_adapter_falls_back_to_process_links_when_rows_are_not_structured():
    html = '''<html><body>
    <h3>Foram encontrados 353880 registros</h3>
    <div class="resultado">
      <div class="documento"><span>Acórdão</span></div>
      <a href="/jurisprudencia/exibir?codigo=560098925">5600/989/25</a>
      <span>17/03/2025</span>
      <span>CONTRATO</span>
      <span>Licitação e qualificação técnica</span>
    </div>
    </body></html>'''.encode("utf-8")
    records = TCESPAdapter(FakeSession([
        FakeResponse(html, content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/pesquisar")
    ])).search("licitação", 1)
    assert len(records) == 1
    assert records[0].numero_processo == "5600/989/25"
    assert records[0].data_autuacao == "17/03/2025"
    assert records[0].url_oficial == "https://www.tce.sp.gov.br/jurisprudencia/exibir?codigo=560098925"




def test_record_version_is_stable_and_cache_has_structured_metadata(tmp_path: Path):
    record = JurisprudenciaRecord(tribunal="TCU", numero_processo="123/2026", numero_decisao="456/2026", orgao_julgador="Plenário", ementa="Licitação.", url_oficial="https://example.test/acordao/456")
    assert record.calculate_version_sha256() == record.calculate_version_sha256()
    path = save_record(record, tmp_path); data = path.with_suffix(".json").read_text(encoding="utf-8")
    assert path.exists() and '"source_role": "jurisprudencia_controle"' in data and '"version_sha256":' in data


def test_stj_scon_textarea_fallback_extracts_process():
    html = '''<html><body>
      <div class="resultado">
        <div>Processo</div>
        <div>REsp 2211999 / SP</div>
        <div>Ministro Regina Helena Costa</div>
        <div>DJe 18/02/2026</div>
        <div>Decisão: 10/02/2026</div>
        <textarea id="textSemformatacao1">DIREITO ADMINISTRATIVO. LICITAÇÃO E CONTRATOS.</textarea>
        <a href="/SCON/GetInteiroTeorDoAcordao?num_registro=123&amp;dt_publicacao=18/02/2026">íntegra</a>
      </div>
    </body></html>'''.encode("iso-8859-1")

    records = STJAdapter(FakeSession([
        FakeResponse(html, content_type="text/html", url=STJAdapter.search_endpoint)
    ])).search("licitação", 1)

    assert len(records) == 1
    assert records[0].numero_processo == "REsp 2211999 / SP"
    assert records[0].data == "10/02/2026"
    assert records[0].data_publicacao == "18/02/2026"
    records[0].validate()


def test_stj_adapter_parses_official_scon_snapshot():
    html = '''<html><body>
      <div class="row itemlistadocumentos p-2">
        <div class="col-sm-3">
          <h4>Processo</h4>
          <div><a href="/SCON/jurisprudencia/doc.jsp?ementa=LICITACAO&i=1">REsp&nbsp;2238193</a></div>
          <div class="small">(ACORDAO)</div>
          <div>Ministro X</div>
          <div>DJe 05/05/2026</div>
          <div>Decisao: 28/04/2026</div>
        </div>
        <div class="col-sm-8">
          <div class="clsEmentaCompleta">DIREITO ADMINISTRATIVO. LICITAÇÃO E CONTRATOS PÚBLICOS.<br>RECURSO CONHECIDO E PROVIDO.</div>
        </div>
      </div>
    </body></html>'''.encode("iso-8859-1")
    session = FakeSession([
        FakeResponse(html, content_type="text/html", url=STJAdapter.search_endpoint),
    ])

    records = STJAdapter(session).search("licitação", 1)

    assert len(records) == 1
    assert records[0].tribunal == "STJ"
    assert records[0].numero_processo == "REsp 2238193"
    assert records[0].relator == "X"
    assert records[0].data_publicacao == "05/05/2026"
    assert STJAdapter.search_endpoint == "https://processo.stj.jus.br/SCON/pesquisar.jsp"
    assert records[0].url_oficial.startswith("https://processo.stj.jus.br/SCON/jurisprudencia/doc.jsp")


def test_stf_form_is_discovered_without_hardcoding_input_name():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup('<form action="/jurisprudencia/pesquisa.asp" method="get"><label>Pesquisa por jurisprudência</label><input name="pesquisaLivre" type="text"></form>', "html.parser")
    assert _discover_form(soup) is not None


def test_session_id_does_not_create_a_new_document_version():
    a = JurisprudenciaRecord(tribunal="TCESP", numero_processo="1/989/26", url_oficial="https://www.tce.sp.gov.br/jurisprudencia/pesquisar;jsessionid=ABC123?acao=Executa")
    b = JurisprudenciaRecord(tribunal="TCESP", numero_processo="1/989/26", url_oficial="https://www.tce.sp.gov.br/jurisprudencia/pesquisar;jsessionid=XYZ987?acao=Executa")
    assert a.calculate_version_sha256() == b.calculate_version_sha256()


def test_all_required_tribunals_have_adapters():
    assert TRIBUNALS == ('tcu', 'tcesp', 'stj', 'stf', 'tjsp')


def test_stf_adapter_uses_current_search_api_and_maps_hits(monkeypatch):
    payload = {"result": {"hits": {"total": {"value": 1}, "hits": [{
        "_id": "sjur524003",
        "_source": {
            "processo_codigo_completo": "RE 1234567/SP",
            "orgao_julgador": "Primeira Turma",
            "relator_acordao_nome": "Ministro X",
            "julgamento_data": "2026-08-20",
            "publicacao_data": "2026-08-29",
            "ementa_texto": "Licitação e contrato administrativo.",
            "documental_tese_texto": "A contratação deve observar a legislação aplicável.",
            "inteiro_teor_texto": "Inteiro teor do acórdão.",
            "ramo_direito": "Direito Administrativo"
        }
    }]}}}
    monkeypatch.setattr(STFAdapter, "_browser_search", lambda self, query, limit, *, with_content: payload)
    records = STFAdapter(FakeSession([])).search("licitação", 1, with_content=True)
    assert len(records) == 1
    assert records[0].numero_processo == "RE 1234567/SP"
    assert records[0].inteiro_teor == "Inteiro teor do acórdão."
    assert STFAdapter.endpoint == "https://jurisprudencia.stf.jus.br/api/search/search"

def test_tjsp_adapter_uses_current_cjsg_post_then_page_contract():
    initial = '''<html><body><form action="/cjsg/resultadoCompleta.do" method="post"></form></body></html>'''.encode("utf-8")
    posted = '''<html><body><input name="conversationId" value="CONV123"></body></html>'''.encode("utf-8")
    page = '''<html><body><table><tr class="fundocinza1"><td>Acórdão</td><td><table>
      <tr class="ementaClass2"><td><a class="esajLinkLogin downloadEmenta" cdacordao="15096525" cdforo="0">1017109-50.2020.8.26.0053</a></td></tr>
      <tr class="ementaClass2"><td><strong>Órgão julgador:</strong> 5ª Câmara de Direito Público</td></tr>
      <tr class="ementaClass2"><td><strong>Relator:</strong> Des. Exemplo</td></tr>
      <tr class="ementaClass2"><td><strong>Data de publicação:</strong> 12/12/2023</td></tr>
      <tr class="ementaClass2"><td><strong>Ementa:</strong> Licitação e contrato administrativo.</td></tr>
    </table></td></tr></table></body></html>'''.encode("utf-8")
    records = TJSPAdapter(FakeSession([
        FakeResponse(initial, content_type="text/html", url="https://esaj.tjsp.jus.br/cjsg/consultaCompleta.do"),
        FakeResponse(posted, content_type="text/html", url="https://esaj.tjsp.jus.br/cjsg/resultadoCompleta.do"),
        FakeResponse(page, content_type="text/html", url="https://esaj.tjsp.jus.br/cjsg/trocaDePagina.do?pagina=1"),
    ])).search("licitação contrato administrativo", 1, detail=True)
    assert len(records) == 1
    assert records[0].numero_processo == "1017109-50.2020.8.26.0053"
    assert records[0].relator == "Des. Exemplo"
    assert records[0].data_publicacao == "12/12/2023"
    assert records[0].url_oficial.endswith("cdForo=0")

def test_tjsp_save_record_has_state_scope(tmp_path: Path):
    record = JurisprudenciaRecord(
        tribunal="TJSP",
        numero_processo="1017109-50.2020.8.26.0053",
        ementa="Licitação e contrato administrativo.",
        url_oficial="https://esaj.tjsp.jus.br/cjsg/getArquivo.do?cdAcordao=15096525&cdForo=0",
    )
    path = save_record(record, tmp_path)
    data = path.with_suffix(".json").read_text(encoding="utf-8")
    assert '"jurisdicao": "estadual_sp"' in data
    assert '"esfera": "estadual"' in data
    assert '"tribunal": "TJSP"' in data


def test_query_matching_requires_all_terms_for_short_queries():
    assert _query_matches("contrato administrativo", "contrato administrativo")
    assert not _query_matches("contrato administrativo", "contrato")


def test_query_matching_requires_half_terms_for_long_queries():
    assert _query_matches("contrato administrativo equilíbrio financeiro público", "contrato administrativo financeiro")
    assert not _query_matches("contrato administrativo equilíbrio financeiro público", "contrato administrativo")



def test_tcesp_missing_results_table_is_reported_as_structure_failure():
    html = "<html><body><p>A página do TCESP foi redesenhada.</p></body></html>".encode("utf-8")
    with pytest.raises(RuntimeError, match="Estrutura da pesquisa TCESP|TCESP não retornou registros|tbody de resultados"):
        TCESPAdapter(FakeSession([FakeResponse(html, content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/pesquisar")])).search("licitação", 1)



def test_query_terms_preserve_legal_numbers():
    from jurisprudencia.collector import _query_terms
    assert _query_terms("Lei 14.133 licitação contrato administrativo") == [
        "14.133", "licitação", "contrato", "administrativo"
    ]


def test_tcesp_falls_back_from_long_query_to_meaningful_term():
    empty = '<html><body><form><input name="txtTdPalvs"></form><table><tbody><tr><td>Pesquisa de Jurisprudência</td></tr></tbody></table></body></html>'.encode("utf-8")
    result = '''<html><body><table><tbody>
    <tr class="borda-superior"><td>Acórdão</td><td>1000/989/26</td><td>17/09/2026</td><td>EMPRESA A</td><td>PREFEITURA B</td><td>LICITAÇÃO</td><td>Lei 14.133 contratação pública</td><td>2026</td></tr>
    <tr><td colspan="8"><ul><li>licitação Lei 14.133 contratação pública</li></ul></td></tr>
    </tbody></table></body></html>'''.encode("utf-8")
    records = TCESPAdapter(FakeSession([
        FakeResponse(empty, content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/pesquisar"),
        FakeResponse(empty, content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/"),
        FakeResponse(result, content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/pesquisar"),
    ])).search("Lei 14.133 licitação contrato administrativo", 1)
    assert len(records) == 1
    assert records[0].numero_processo == "1000/989/26"


def test_tjsp_falls_back_from_long_query():
    initial = b'<html><body><form action="/cjsg/resultadoCompleta.do" method="post"></form></body></html>'
    posted = b'<html><body></body></html>'
    result = '''<html><body><table><tr class="fundocinza1"><td>Acórdão</td><td><table>
      <tr class="ementaClass2"><td><a class="esajLinkLogin downloadEmenta" cdacordao="15099999" cdforo="0">1000000-10.2026.8.26.0053</a></td></tr>
      <tr class="ementaClass2"><td><strong>Ementa:</strong> Lei 14.133 licitação.</td></tr>
    </table></td></tr></table></body></html>'''.encode("utf-8")
    records = TJSPAdapter(FakeSession([
        FakeResponse(initial, content_type="text/html", url="https://esaj.tjsp.jus.br/cjsg/consultaCompleta.do"),
        FakeResponse(posted, content_type="text/html", url="https://esaj.tjsp.jus.br/cjsg/resultadoCompleta.do"),
        FakeResponse(b'<html><body></body></html>', content_type="text/html", url="https://esaj.tjsp.jus.br/cjsg/trocaDePagina.do"),
        FakeResponse(initial, content_type="text/html", url="https://esaj.tjsp.jus.br/cjsg/consultaCompleta.do"),
        FakeResponse(posted, content_type="text/html", url="https://esaj.tjsp.jus.br/cjsg/resultadoCompleta.do"),
        FakeResponse(result, content_type="text/html", url="https://esaj.tjsp.jus.br/cjsg/trocaDePagina.do?pagina=1"),
    ])).search("Lei 14.133 licitação contrato administrativo", 1)
    assert len(records) == 1
    assert records[0].numero_processo == "1000000-10.2026.8.26.0053"

def test_stj_resources_fall_back_to_public_catalog_when_ckan_api_is_forbidden():
    class ForbiddenResponse(FakeResponse):
        def raise_for_status(self):
            from requests import HTTPError
            raise HTTPError("403 Client Error: Forbidden")

    class CaptureSession(FakeSession):
        def __init__(self, responses):
            super().__init__(responses)
            self.calls = []

        def get(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return super().get(*args, **kwargs)

    html = '''<html><body>
      <a href="/dataset/abc/resource/1/download/20260831.json">20260831.json</a>
      <a href="/dataset/abc/resource/2/download/20260731.json">20260731.json</a>
      <a href="/dataset/abc/resource/3/download/20260630.json">20260630.json</a>
    </body></html>'''.encode("utf-8")

    session = CaptureSession([
        ForbiddenResponse({"error": "forbidden"}, content_type="application/json"),
        FakeResponse(html, content_type="text/html", url="https://dadosabertos.web.stj.jus.br/dataset/espelhos-de-acordaos-corte-especial"),
    ])
    resources = STJAdapter(session)._resources("espelhos-de-acordaos-corte-especial")

    assert [item["name"] for item in resources] == [
        "20260831.json", "20260731.json", "20260630.json"
    ]
    assert session.calls[1][0][0].endswith("/dataset/espelhos-de-acordaos-corte-especial")


def test_stj_adapter_uses_direct_scon_endpoint():
    html = '''<html><body>
      <div class="row itemlistadocumentos p-2">
        <div class="col-sm-3">
          <h4>Processo</h4>
          <div><a href="/SCON/jurisprudencia/doc.jsp?ementa=LICITACAO&i=1">REsp&nbsp;1234567</a></div>
          <div class="small">(ACORDAO)</div>
          <div>Ministro EXEMPLO</div>
          <div>DJe 30/09/2026</div>
          <div>Decisao: 29/09/2026</div>
        </div>
        <div class="col-sm-8">
          <div class="clsEmentaCompleta">LICITAÇÃO E CONTRATO ADMINISTRATIVO.<br>RECURSO PROVIDO.</div>
        </div>
      </div>
    </body></html>'''.encode("iso-8859-1")

    class CaptureSession(FakeSession):
        def __init__(self, responses):
            super().__init__(responses)
            self.calls = []

        def request(self, method, *args, **kwargs):
            self.calls.append((method, args, kwargs))
            return super().request(method, *args, **kwargs)

    session = CaptureSession([
        FakeResponse(html, content_type="text/html", url=STJAdapter.search_endpoint),
    ])
    records = STJAdapter(session).search("licitação", 1)

    assert len(records) == 1
    assert records[0].numero_processo == "REsp 1234567"
    assert records[0].relator == "EXEMPLO"
    assert records[0].data_publicacao == "30/09/2026"
    assert records[0].data == "29/09/2026"
    assert "LICITAÇÃO E CONTRATO ADMINISTRATIVO." in records[0].ementa
    assert session.calls[0][0] == "POST"
    assert session.calls[0][1][0] == STJAdapter.search_endpoint
    assert b"licita%E7%E3o" in session.calls[0][2]["data"]


def test_stj_adapter_uses_current_open_data_host():
    assert STJAdapter.endpoint == "https://dadosabertos.web.stj.jus.br"

def test_stf_body_uses_acordaos_and_full_text_fields():
    body = STFAdapter(FakeSession([]))._body("licitação", 1, include_full_text=True)
    assert body["query"]["bool"]["filter"][0] == {"term": {"base": "acordaos"}}
    assert "inteiro_teor_texto.plural" in body["_source"]
    assert "inteiro_teor_texto" in body["highlight"]["fields"]


def test_tjsp_reports_visible_antibot_without_treating_it_as_zero():
    html = b"<html><body><div>CAPTCHA</div><div>Verificacao de seguranca</div></body></html>"
    with pytest.raises(RuntimeError, match="desafio/captcha/antibot"):
        TJSPAdapter._check_access_block(html)


def test_tcesp_search_does_not_send_blank_document_type():
    class CaptureSession(FakeSession):
        def get(self, *args, **kwargs):
            assert 'tipoDocumento' not in kwargs.get('params', [])
            return super().get(*args, **kwargs)
    html = '<html><body><table><tr><th>N° Proc.</th><th>N° Proc.</th><th>Autuação</th><th>Parte 1</th><th>Parte 2</th><th>Matéria</th><th>Objeto</th></tr></table></body></html>'.encode('utf-8')
    with pytest.raises(RuntimeError):
        TCESPAdapter(CaptureSession([FakeResponse(html, content_type='text/html', url='https://www.tce.sp.gov.br/jurisprudencia/pesquisar')])).search('licitação', 1)
        raise AssertionError("a página sintética não deveria gerar registro")
