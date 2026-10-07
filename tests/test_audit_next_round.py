from types import SimpleNamespace

import config
import evaluation
import query
from chunking import build_legal_ast


def _point(source, text):
    return SimpleNamespace(
        id=source,
        payload={
            'source_id': source,
            'source': source,
            'unit_id': 'u1',
            'title': source,
            'text': text,
            'page_content': text,
        },
    )


def _condition_keys(compiled):
    return {condition.key for condition in (compiled.must or [])}


def test_temporal_parser_recognizes_exact_date_year_and_month():
    exact = query.parse_query_temporal_context('A norma estava vigente em 15/12/2023?')
    assert exact.mode == 'historical'
    assert exact.effective_on.isoformat() == '2023-12-15'

    month = query.parse_query_temporal_context('Qual regra valia em dezembro de 2023?')
    assert month.effective_from.isoformat() == '2023-12-01'
    assert month.effective_to.isoformat() == '2023-12-31'

    year = query.parse_query_temporal_context('Quais valores eram aplicáveis em 2025?')
    assert year.effective_from.isoformat() == '2025-01-01'
    assert year.effective_to.isoformat() == '2025-12-31'


def test_temporal_parser_handles_before_after_boundaries():
    before = query.parse_query_temporal_context('Qual era a regra antes de 2024?')
    assert before.effective_on.isoformat() == '2023-12-31'

    after = query.parse_query_temporal_context('Qual era a regra depois de 2023?')
    assert after.effective_on.isoformat() == '2024-01-01'


def test_temporal_filter_is_compiled_into_qdrant_and_history_skips_current_only_exclusion():
    plan = query.build_retrieval_plan(
        'A Lei nº 8.666/1993 estava vigente em dezembro de 2023?'
    )
    keys = _condition_keys(plan['qdrant_filter'])
    assert 'effective_from_day' in keys
    assert 'effective_to_day' in keys
    assert not plan['qdrant_filter'].must_not
    assert plan['temporal_context'].mode == 'historical'
    assert plan['filtered_for_current_only'] is False


def test_context_base_is_auxiliary_and_primary_evidence_survives_tight_budget(monkeypatch):
    primary = _point('lei14133', 'Planejamento e eficiência.')
    auxiliary = _point('tcu-manual-licitacoes', 'Orientação auxiliar do TCU.')
    auxiliary.payload['_context_only'] = True
    primary_context, _ = query.context_with_sources([primary])
    monkeypatch.setattr(config, 'MAX_CONTEXT_CHARS', len(primary_context) + 1)

    context_text, included = query.context_with_sources([primary, auxiliary])
    assert included == [primary]
    assert 'Planejamento e eficiência.' in context_text
    assert 'Orientação auxiliar' not in context_text
    assert 'referências-base auxiliares' in query.SYSTEM_PROMPT
    assert 'Não são fontes obrigatórias' in query.SYSTEM_PROMPT


def test_annex_ast_uses_immediate_internal_structural_parent():
    text = (
        'LEI Nº 1, DE 2026\n'
        'ANEXO I\n'
        'CAPÍTULO I\n'
        'SEÇÃO I\n'
        'Art. 1º Regra do anexo.\n'
    )
    root = build_legal_ast(text)
    norma = next(node for node in root.children if node.kind == 'norma')

    def find(node, kind):
        for child in node.children:
            if child.kind == kind:
                return child
            found = find(child, kind)
            if found is not None:
                return found
        return None

    annex = find(norma, 'anexo')
    chapter = next(node for node in annex.children if node.kind == 'capitulo')
    section = next(node for node in chapter.children if node.kind == 'secao')
    article = next(node for node in section.children if node.kind == 'artigo')

    assert article.parent_id == section.node_id
    assert article.anexo_path[-3:] == ['ANEXO I', 'CAPÍTULO I', 'SEÇÃO I']
    assert article.path[-4:] == ['ANEXO I', 'CAPÍTULO I', 'SEÇÃO I', 'Art. 1º']


def test_amendment_preserves_multiple_operations_in_order():
    import chunking

    result = chunking._detect_amendment(
        'Fica alterado o inciso IV do art. 75 e fica revogado o item 2.',
        'Art. 2º',
    )
    assert result['amendment_operations'] == ['alteracao', 'revogacao']
    assert result['amendment_type'] == 'alteracao'


def test_temporal_rejection_metric_detects_version_outside_window():
    case = {
        'expected_source_ids': ['decreto12343'],
        'temporal': {'effective_on': '2026-06-15'},
        'temporal_rejection_test': True,
        'expected_temporal_rejection': True,
    }
    payload = _point('decreto12343', 'valores 2025').payload
    payload['effective_to'] = '2025-12-31'

    assert evaluation.temporal_match(payload, case) is False

    report = evaluation.evaluate_rankings(
        {'x': []},
        [{
            'id': 'x',
            'query': 'x',
            **case,
            'expected_rejection': True,
            'rejection_test': True,
        }],
        (1,),
    )
    assert report['summary']['temporal_rejection_accuracy'] == 1.0


def test_historical_query_combines_regime_and_temporal_filters():
    plan = query.build_retrieval_plan(
        'A Lei 8.666/1993 estava vigente em dezembro de 2023?'
    )
    regime = next(
        condition for condition in plan['qdrant_filter'].must
        if condition.key == 'regime_juridico'
    )
    assert regime.match.value == 'lei_8666'
    assert {condition.key for condition in plan['qdrant_filter'].must} >= {
        'regime_juridico',
        'effective_from_day',
        'effective_to_day',
    }


def test_temporal_parser_ignores_normative_identification_month_year():
    current = query.parse_query_temporal_context(
        'Qual é a regra da Lei 14.133, de 1º de abril de 2021, sobre ETP?'
    )
    historical = query.parse_query_temporal_context(
        'Qual regra valia em abril de 2021?'
    )
    assert current.mode == 'current'
    assert current.has_filter is False
    assert historical.mode == 'historical'
    assert historical.effective_from.isoformat() == '2021-04-01'
    assert historical.effective_to.isoformat() == '2021-04-30'


def test_effective_range_states_keep_unknown_distinct_from_open_bounds():
    assert ingest._effective_range_payload({
        'effective_from': '2024-01-01',
        'effective_to': '2024-12-31',
    }) == {
        'effective_range_status': 'closed',
        'effective_from_day': 20240101,
        'effective_to_day': 20241231,
    }
    assert ingest._effective_range_payload({
        'effective_from': None,
        'effective_to': '2024-12-31',
        'effective_range_status': 'open_start',
    }) == {
        'effective_range_status': 'open_start',
        'effective_from_day': 0,
        'effective_to_day': 20241231,
    }
    assert ingest._effective_range_payload({
        'effective_from': '2024-01-01',
        'effective_to': None,
        'effective_range_status': 'open_end',
    }) == {
        'effective_range_status': 'open_end',
        'effective_from_day': 20240101,
        'effective_to_day': 99991231,
    }
    assert ingest._effective_range_payload({
        'effective_from': None,
        'effective_to': None,
    }) == {
        'effective_range_status': 'unknown',
    }


def test_amendment_operations_ignore_reproduced_article_verbs():
    result = chunking._detect_amendment(
        'Fica alterado o art. 75: “Art. 75. O inciso X fica revogado.”',
        'Art. 1º',
    )
    assert result['amendment_operations'] == ['alteracao']
