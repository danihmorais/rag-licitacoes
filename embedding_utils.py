import config


def validate_embedding_inputs(model, texts, *, label):
    tokenizer = getattr(getattr(model, 'model', None), 'tokenizer', None)
    if tokenizer is None or not hasattr(tokenizer, 'encode_batch'):
        raise RuntimeError('Não foi possível validar o tamanho dos textos antes do embedding.')
    truncation = getattr(tokenizer, 'truncation', None) or {}
    actual_limit = truncation.get('max_length') if isinstance(truncation, dict) else None
    limit = min(config.DENSE_MAX_TOKENS, int(actual_limit)) if actual_limit else config.DENSE_MAX_TOKENS
    restore_truncation = getattr(tokenizer, 'enable_truncation', None) if hasattr(tokenizer, 'no_truncation') else None
    if hasattr(tokenizer, 'no_truncation'):
        tokenizer.no_truncation()
    try:
        for offset in range(0, len(texts), 256):
            batch = texts[offset:offset + 256]
            encoded = tokenizer.encode_batch(batch)
            oversized = [
                (offset + index + 1, len(item.ids))
                for index, item in enumerate(encoded)
                if len(item.ids) > limit
            ]
            if oversized:
                index, count = oversized[0]
                raise RuntimeError(
                    f'{label} excede o limite de {limit} tokens do embedding no item {index}: {count} tokens. '
                    'O texto não será truncado silenciosamente; reduza o chunk ou ajuste o limite do modelo.'
                )
    finally:
        if restore_truncation is not None:
            restore_truncation(max_length=limit)
