from pathlib import Path

from metadata import extract_metadata


def test_unsupported_tribunal_is_not_misclassified(tmp_path: Path):
    document = tmp_path / 'jurisprudencia.txt'
    document.write_text('TRIBUNAL: TRIBUNAL-DESCONHECIDO\nPROCESSO: 1234\nLicitação.', encoding='utf-8')
    metadata = extract_metadata(document.read_text(encoding='utf-8'), document)
    assert metadata['metadata_ambiguous'] is True
    assert metadata['jurisdicao'] is None
    assert metadata['authority_level'] is None
