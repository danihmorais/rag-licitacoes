import json
from pathlib import Path

from metadata import extract_metadata


def test_ambiguous_sp_and_14133_filename_does_not_guess_jurisdiction(tmp_path: Path):
    pdf = tmp_path / 'sp_decreto_14133_regulamento.pdf'
    pdf.write_bytes(b'')
    metadata = extract_metadata('DECRETO ESTADUAL', pdf)
    assert metadata['classificacao_ambigua'] is True
    assert metadata['jurisdicao'] is None
    assert metadata['esfera'] is None


def test_sidecar_scope_overrides_ambiguous_filename(tmp_path: Path):
    pdf = tmp_path / 'sp_decreto_14133_regulamento.pdf'
    pdf.write_bytes(b'')
    sidecar = pdf.with_suffix('.json')
    sidecar.write_text(json.dumps({
        'jurisdicao': 'estadual_sp',
        'esfera': 'estadual',
        'orgao': 'Estado de São Paulo',
        'tipo_documento': 'norma',
        'source_role': 'norma',
        'authority_level': 1,
    }), encoding='utf-8')
    metadata = extract_metadata('DECRETO ESTADUAL', pdf)
    assert metadata['jurisdicao'] == 'estadual_sp'
    assert metadata['esfera'] == 'estadual'
    assert metadata['orgao'] == 'Estado de São Paulo'


def test_normative_year_requires_own_normative_header(tmp_path: Path):
    pdf = tmp_path / 'decreto_regulamento.pdf'
    pdf.write_bytes(b'')
    text = 'Nos termos do Decreto federal nº 10.024, de 2019.\n\nDECRETO Nº 2.056, DE 10 DE JANEIRO DE 2024.'
    metadata = extract_metadata(text, pdf)
    assert metadata['ano'] == 2024
    assert metadata['norm_ano'] == 2024


def test_year_is_left_unknown_without_normative_header(tmp_path: Path):
    pdf = tmp_path / 'documento.pdf'
    pdf.write_bytes(b'')
    metadata = extract_metadata('Referência histórica: 2024. Outra citação: 2023.', pdf)
    assert metadata['ano'] is None
    assert metadata['norm_ano'] is None
