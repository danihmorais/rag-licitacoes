import json
from pathlib import Path


def test_link_failure_does_not_delete_previous_cache(monkeypatch, tmp_path: Path):
    import scripts.sync_sources as sync

    monkeypatch.setattr(sync, 'CACHE', tmp_path)
    old_base = tmp_path / 'source__pdf_oficial__old'
    old_base.with_suffix('.txt').write_text('conteudo anterior\n', encoding='utf-8')
    old_base.with_suffix('.json').write_text(
        json.dumps({
            'parent_source_id': 'fonte-teste',
            'document_id': 'source__pdf_oficial__old',
        }),
        encoding='utf-8',
    )

    source = {
        'id': 'fonte-teste',
        'title': 'Fonte de teste',
        'urls': ['https://example.test/pagina'],
        'source_role': 'orientacao_oficial',
        'authority_level': 3,
        'follow_links': True,
        'follow_patterns': [r'\\.pdf(?:$|\\?)'],
        'max_follow': 10,
    }
    root_text = '\n'.join(['orientação oficial ' + ('conteudo ' * 50) for _ in range(6)])

    def fake_fetch(_session, url):
        if url.endswith('/pagina'):
            return 'html', url, root_text.encode('utf-8'), root_text
        raise RuntimeError('falha temporária')

    monkeypatch.setattr(sync, 'fetch', fake_fetch)
    monkeypatch.setattr(
        sync,
        'discover_links',
        lambda *_args, **_kwargs: [('https://example.test/arquivo.pdf', 'PDF oficial')],
    )

    ok, _, _ = sync.sync_one(object(), source, check=False, follow_links=True)

    assert ok
    assert old_base.with_suffix('.txt').exists()
    assert old_base.with_suffix('.json').exists()


def test_index_only_source_writes_linked_document_as_evidence(monkeypatch, tmp_path: Path):
    import scripts.sync_sources as sync

    monkeypatch.setattr(sync, 'CACHE', tmp_path)
    source = {
        'id': 'pge-teste',
        'title': 'PGE-SP — pareceres',
        'urls': ['https://example.test/pge'],
        'source_role': 'orientacao_oficial',
        'authority_level': 3,
        'index_only': True,
        'follow_links': True,
        'follow_patterns': [r'\\.pdf(?:$|\\?)'],
        'max_follow': 10,
    }
    root_text = '\n'.join(['índice oficial de pareceres ' + ('documentos públicos ' * 30) for _ in range(6)])
    linked_text = '\n'.join(['PARECER Nº 10/2026 — orientação oficial ' + ('fundamentação jurídica ' * 25) for _ in range(6)])

    def fake_fetch(_session, url):
        if url.endswith('/pge'):
            return 'html', url, root_text.encode('utf-8'), root_text
        return 'pdf', url, linked_text.encode('utf-8'), linked_text

    monkeypatch.setattr(sync, 'fetch', fake_fetch)
    monkeypatch.setattr(
        sync,
        'discover_links',
        lambda *_args, **_kwargs: [('https://example.test/parecer.pdf', 'Parecer 10/2026')],
    )

    ok, _, seen = sync.sync_one(object(), source, check=False, follow_links=True)

    assert ok
    assert source['id'] not in seen
    linked_json = [path for path in tmp_path.glob('*.json') if path.name != 'pge-teste.json']
    assert linked_json
