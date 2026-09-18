from pathlib import Path

import pytest

from jurisprudencia.collector import STJAdapter, STFAdapter, TCESPAdapter, TCUAdapter, TCMSPAdapter, TJSPAdapter, TRIBUNALS, _discover_form, _query_matches, save_record
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


def test_tcu_adapter_uses_current_public_rest_contract():
    session = FakeSession([
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
        })
    ])
    records = TCUAdapter(session).search("licitação", 1)
    assert len(records) == 1
    assert TCUAdapter.endpoint == "https://pesquisa.apps.tcu.gov.br/rest/publico/base/acordao-completo"
    assert records[0].numero_decisao == "480/2024"
    assert records[0].orgao_julgador == "Plenário"
    assert records[0].url_oficial.endswith("/4802024")

def test_tcesp_adapter_parses_result_table():
    html = '''<html><body><table><tbody>
    <tr class="borda-superior"><td>Relatório / Voto</td><td>5600/989/25</td><td>17/03/2025</td><td>EMPRESA A</td><td>PREFEITURA B</td><td>LICITAÇÃO</td><td>Exame de edital</td><td>2025</td></tr>
    <tr><td colspan="8"><ul><li>licitação e qualificação técnica devem ser pertinentes e proporcionais.</li></ul></td></tr>
    </tbody></table></body></html>'''.encode("utf-8")
    records = TCESPAdapter(FakeSession([FakeResponse(html, content_type="text/html", url="https://www.tce.sp.gov.br/jurisprudencia/pesquisar")])).search("licitação", 1)
    assert len(records) == 1
    assert records[0].numero_processo == "5600/989/25"
    assert records[0].ementa == "licitação e qualificação técnica devem ser pertinentes e proporcionais."


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

def test_tcm_sp_parser_handles_current_official_document_link():
    html = '''<html><body>
    <a href="/Management/AcordaoItem/Documento/TC0021982023">TC/002198/2023 — Licitação de serviços</a>
    </body></html>'''.encode("utf-8")
    records = TCMSPAdapter._parse_records(html, "https://portal.tcm.sp.gov.br/Acordao/Index", "licitação")
    assert len(records) == 1
    assert records[0].numero_processo == "TC/002198/2023"

def test_tcm_sp_save_record_has_municipal_scope(tmp_path: Path):
    record = JurisprudenciaRecord(tribunal="TCM-SP", numero_processo="1234/989/26", ementa="Licitação municipal.", url_oficial="https://jurisprudencia.tcm.sp.gov.br/Acordao/Detalhe/1234")
    path = save_record(record, tmp_path)
    data = path.with_suffix(".json").read_text(encoding="utf-8")
    assert '"jurisdicao": "municipal_sp"' in data
    assert '"esfera": "municipal"' in data
    assert '"authority_level": 2' in data


def test_record_version_is_stable_and_cache_has_structured_metadata(tmp_path: Path):
    record = JurisprudenciaRecord(tribunal="TCU", numero_processo="123/2026", numero_decisao="456/2026", orgao_julgador="Plenário", ementa="Licitação.", url_oficial="https://example.test/acordao/456")
    assert record.calculate_version_sha256() == record.calculate_version_sha256()
    path = save_record(record, tmp_path); data = path.with_suffix(".json").read_text(encoding="utf-8")
    assert path.exists() and '"source_role": "jurisprudencia_controle"' in data and '"version_sha256":' in data


def test_stj_adapter_uses_official_open_data_snapshot():
    session = FakeSession([
        FakeResponse({"success": True, "result": {"resources": [{
            "name": "20260915.json", "format": "JSON",
            "url": "https://dadosabertos.web.stj.jus.br/dataset/espelhos/raw/20260915.json"
        }]}}),
        FakeResponse([{
            "id": "956702", "numeroProcesso": "2238193", "numeroRegistro": "202503517440",
            "siglaClasse": "REsp", "descricaoClasse": "RECURSO ESPECIAL",
            "nomeOrgaoJulgador": "TERCEIRA SEÇÃO", "ministroRelator": "Ministro X",
            "dataPublicacao": "DJEN DATA:05/05/2026",
            "ementa": "DIREITO ADMINISTRATIVO. LICITAÇÃO E CONTRATOS PÚBLICOS.",
            "tipoDeDecisao": "ACÓRDÃO", "dataDecisao": "20260428",
            "decisao": "Recurso conhecido e provido."
        }])
    ])
    records = STJAdapter(session).search("licitação", 1)
    assert len(records) == 1
    assert records[0].tribunal == "STJ"
    assert records[0].numero_processo == "2238193"
    assert records[0].relator == "Ministro X"
    assert STJAdapter.endpoint == "https://dadosabertos.web.stj.jus.br"

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


def test_tcm_sp_uses_current_portal_endpoint():
    assert TCMSPAdapter.endpoint == "https://portal.tcm.sp.gov.br/Acordao/Index"

def test_query_matching_requires_all_terms_for_short_queries():
    assert _query_matches("contrato administrativo", "contrato administrativo")
    assert not _query_matches("contrato administrativo", "contrato")


def test_query_matching_requires_half_terms_for_long_queries():
    assert _query_matches("contrato administrativo equilíbrio financeiro público", "contrato administrativo financeiro")
    assert not _query_matches("contrato administrativo equilíbrio financeiro público", "contrato administrativo")


def test_tcm_sp_missing_browser_results_are_reported_as_failure(monkeypatch):
    monkeypatch.setattr(TCMSPAdapter, "_browser_records", lambda self, query, limit: [])
    with pytest.raises(RuntimeError, match="TCM-SP não retornou registros estruturados"):
        TCMSPAdapter(FakeSession([])).search("licitação", 1)

def test_tcesp_missing_results_table_is_reported_as_structure_failure():
    html = "<html><body><p>A página do TCESP foi redesenhada.</p></body></html>".encode("utf-8")
    with pytest.raises(RuntimeError, match="Estrutura da pesquisa TCESP|TCESP não retornou resultados estruturados"):
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

def test_tcm_sp_parses_current_portal_document_link():
    html = '''<html><body>
    <a href="/Management/AcordaoItem/Documento/TC0021982023">TC/002198/2023 — Licitação e contrato administrativo</a>
    </body></html>'''.encode("utf-8")
    records = TCMSPAdapter._parse_records(
        html,
        "https://portal.tcm.sp.gov.br/Acordao",
        "licitação",
    )
    assert len(records) == 1
    assert records[0].numero_processo == "TC/002198/2023"


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
