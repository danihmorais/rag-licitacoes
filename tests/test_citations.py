from types import SimpleNamespace

import query


def point(point_id, source, unit_id, text, chunk_index=0):
    return SimpleNamespace(
        id=point_id,
        payload={
            'source': source,
            'title': source,
            'unit_id': unit_id,
            'chunk_index': chunk_index,
            'text': text,
            'source_role': 'norma',
            'authority_level': 1,
            'status': 'vigente',
        },
    )


def test_context_with_sources_returns_exact_points_sent_to_model(monkeypatch):
    first = point('1', 'lei14133.txt', 'artigo:1', 'Regra principal.')
    second = point('2', 'lei14133.txt', 'artigo:1', 'Regra complementar.', 1)
    monkeypatch.setattr(query.config, 'MAX_CONTEXT_CHARS', 100000)
    context_text, sources = query.context_with_sources([first, second])
    assert '[F1]' in context_text and '[F2]' in context_text
    assert sources == [first, second]


def test_context_with_sources_drops_sources_that_do_not_fit(monkeypatch):
    first = point('1', 'a.txt', 'artigo:1', 'x' * 100)
    second = point('2', 'b.txt', 'artigo:2', 'y' * 100)
    monkeypatch.setattr(query.config, 'MAX_CONTEXT_CHARS', 180)
    context_text, sources = query.context_with_sources([first, second])
    assert '[F1]' in context_text
    assert '[F2]' not in context_text
    assert sources == [first]


def test_answer_query_returns_sources_used_in_context(monkeypatch):
    selected = point('1', 'a.txt', 'artigo:1', 'Regra selecionada.')
    neighbor = point('2', 'a.txt', 'artigo:1', 'Regra vizinha.', 1)
    captured = {}

    class FakeLLM:
        def generate(self, *, system_prompt, user_prompt):
            captured['prompt'] = system_prompt
            return 'Resposta [F2].'

    monkeypatch.setattr(query, 'hybrid', lambda *args, **kwargs: [selected])
    monkeypatch.setattr(query, 'rerank', lambda *args, **kwargs: [selected])
    monkeypatch.setattr(query, 'expand_context', lambda *args, **kwargs: [selected, neighbor])
    monkeypatch.setattr(query, 'context_with_sources', lambda points: ('[F1] selecionada\n[F2] vizinha', [selected, neighbor]))

    answer, sources = query.answer_query(
        object(), object(), object(), object(), FakeLLM(), 'qual é a regra?'
    )

    assert answer == 'Resposta [F2].'
    assert sources == [selected, neighbor]
    assert '[F2] vizinha' in captured['prompt']
