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
        'follow_links': True,
        'follow_patterns': [r'\\.pdf(?:$|\\?)'],
        'max_follow': 10,
    }
    root_text = 'conteudo oficial ' * 100

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
