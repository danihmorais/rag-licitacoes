from types import SimpleNamespace

import pytest

import config
from embedding_utils import validate_embedding_inputs


class FakeTokenizer:
    truncation = {'max_length': 4}

    def encode_batch(self, texts):
        return [SimpleNamespace(ids=text.split()) for text in texts]


class FakeModel:
    model = SimpleNamespace(tokenizer=FakeTokenizer())


def test_embedding_inputs_reject_truncation():
    with pytest.raises(RuntimeError, match='não será truncado silenciosamente'):
        validate_embedding_inputs(FakeModel(), ['um dois três quatro cinco'], label='teste')


def test_embedding_inputs_accept_limit():
    validate_embedding_inputs(FakeModel(), ['um dois três'], label='teste')
