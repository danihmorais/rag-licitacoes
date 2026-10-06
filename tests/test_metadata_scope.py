from pathlib import Path

from metadata import _detect_regime, extract_metadata


def test_unsupported_tribunal_is_not_misclassified(tmp_path: Path):
    document = tmp_path / 'jurisprudencia.txt'
    document.write_text('TRIBUNAL: TRIBUNAL-DESCONHECIDO\nPROCESSO: 1234\nLicitação.', encoding='utf-8')
    metadata = extract_metadata(document.read_text(encoding='utf-8'), document)
    assert metadata['metadata_ambiguous'] is True
    assert metadata['jurisdicao'] is None
    assert metadata['authority_level'] is None


def test_primary_law_is_not_changed_by_cited_law(tmp_path: Path):
    document = tmp_path / 'lei_14133.txt'
    text = (
        'LEI Nº 14.133, DE 1º DE ABRIL DE 2021\n'
        'Art. 1º Conforme a Lei nº 8.666/1993 e a LC 123/2006...'
    )

    metadata = extract_metadata(text, document)

    assert metadata['document_regime'] == 'lei_14133'
    assert metadata['regime_juridico'] == 'lei_14133'
    assert metadata['cited_regimes'] == ['lei_8666', 'lei_123']


def test_old_law_remains_primary_when_citing_new_law():
    regime, _ = _detect_regime(
        'LEI Nº 8.666, DE 21 DE JUNHO DE 1993\nConforme a Lei nº 14.133/2021...',
        {'source_id': 'lei_8666', 'title': 'Lei 8.666/1993'},
    )

    assert regime == 'lei_8666'


def test_explicit_comparison_document_is_transition():
    regime, _ = _detect_regime(
        'Comparação entre regimes: Lei 8.666 e Lei 14.133',
        {'title': 'Comparação entre regimes'},
    )

    assert regime == 'transicao'
