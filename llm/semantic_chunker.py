from __future__ import annotations

import json
import re
from typing import Any, Callable

from langchain_text_splitters import RecursiveCharacterTextSplitter


class SemanticChunkingError(RuntimeError):
    """Falha na segmentação semântica por LLM."""


SYSTEM_PROMPT = """Você é um segmentador de documentos jurídicos brasileiros.
Sua função é SOMENTE agrupar trechos consecutivos do documento em unidades semanticamente coerentes.
Não reescreva, resuma, corrija, traduza ou invente conteúdo.
Não descarte nenhum trecho.
Os IDs informados representam trechos do texto original e devem permanecer na mesma ordem.
Responda SOMENTE com JSON válido, sem markdown:
{"groups":[{"ids":["B0000"],"topic":"tema curto","section":"seção curta"}]}.
Cada ID deve aparecer exatamente uma vez.
Os grupos devem ser contíguos e cobrir todos os IDs.
"topic" e "section" são apenas rótulos auxiliares e nunca substituem o texto original.
"""


def _extract_json(response: str) -> dict[str, Any]:
    raw = str(response or "").strip()
    candidates = []
    start = raw.find("{")
    while start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(raw)):
            char = raw[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(raw[start:index + 1])
                    break
        start = raw.find("{", start + 1)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    raise SemanticChunkingError("LLM não retornou JSON válido para o chunking semântico.")


def _validate_groups(payload: dict[str, Any], expected_ids: list[str]) -> list[dict[str, Any]]:
    groups = payload.get("groups")
    if not isinstance(groups, list) or not groups:
        raise SemanticChunkingError("LLM não retornou grupos semânticos.")
    seen = []
    normalized = []
    for group in groups:
        if not isinstance(group, dict):
            raise SemanticChunkingError("Grupo semântico inválido: esperado objeto JSON.")
        ids = group.get("ids")
        if not isinstance(ids, list) or not ids:
            raise SemanticChunkingError("Grupo semântico sem IDs.")
        ids = [str(item).strip() for item in ids if str(item).strip()]
        normalized.append({"ids": ids, "topic": str(group.get("topic") or "").strip()[:160], "section": str(group.get("section") or "").strip()[:160]})
        seen.extend(ids)
    if seen != list(expected_ids):
        raise SemanticChunkingError(f"LLM alterou a ordem, duplicou ou omitiu trechos: esperado={len(expected_ids)} IDs, retornado={len(seen)}.")
    if len(set(seen)) != len(seen):
        raise SemanticChunkingError("LLM retornou IDs duplicados.")
    return normalized


def _token_length_factory(tokenizer: Any | None) -> Callable[[str], int]:
    if tokenizer is None:
        return len
    def length(text: str) -> int:
        try:
            encoded = tokenizer.encode(text)
            return len(getattr(encoded, "ids", encoded))
        except Exception:
            try:
                encoded = tokenizer.encode_batch([text])[0]
                return len(getattr(encoded, "ids", encoded))
            except Exception:
                return len(text)
    return length


def _split_large_block(text: str, max_size: int, tokenizer=None) -> list[tuple[str, int, int]]:
    length_fn = _token_length_factory(tokenizer)
    if length_fn(text) <= max_size:
        stripped = text.strip()
        left = len(text) - len(text.lstrip())
        return [(stripped, left, left + len(stripped))] if stripped else []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_size,
        chunk_overlap=0,
        length_function=length_fn,
        separators=["\n\n", "\n", ". ", "; ", " ", ""],
        add_start_index=True,
    )
    return [
        (doc.page_content, int(doc.metadata.get("start_index", 0)), int(doc.metadata.get("start_index", 0)) + len(doc.page_content))
        for doc in splitter.create_documents([text])
    ]


def _atomic_blocks(text: str, max_atomic_size: int, tokenizer=None) -> list[dict[str, Any]]:
    blocks = []
    paragraph_matches = list(re.finditer(r"(?s).+?(?=(?:\n\s*\n)|$)", text))
    if not paragraph_matches and text:
        fallback = re.match(r"(?s).+", text)
        paragraph_matches = [fallback] if fallback else []
    sequence = 0
    for match in paragraph_matches:
        raw = match.group(0)
        if not raw.strip():
            continue
        raw_start = match.start()
        for piece, relative_start, relative_end in _split_large_block(raw, max_atomic_size, tokenizer):
            start = raw_start + relative_start
            end = raw_start + relative_end
            blocks.append({"id": f"B{sequence:04d}", "text": text[start:end], "start": start, "end": end})
            sequence += 1
    return blocks


def _windows(blocks, window_chars):
    windows, current = [], []
    current_size = 0
    for block in blocks:
        block_size = len(block["text"]) + 40
        if current and current_size + block_size > window_chars:
            windows.append(current)
            current, current_size = [], 0
        current.append(block)
        current_size += block_size
    if current:
        windows.append(current)
    return windows


def _prompt_for_window(blocks):
    parts = ["Agrupe os trechos abaixo por continuidade semântica. Não altere os IDs e não produza o texto dos trechos na resposta."]
    for block in blocks:
        parts.append(f"ID {block['id']}\n{block['text']}\nFIM {block['id']}")
    return "\n\n".join(parts)


def _segment_window(provider, blocks, attempts):
    expected_ids = [block["id"] for block in blocks]
    prompt = _prompt_for_window(blocks)
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            extra = "" if attempt == 1 else "\n\nATENÇÃO: sua resposta anterior foi inválida. Responda apenas com JSON válido no formato exigido, cobrindo cada ID exatamente uma vez."
            return _validate_groups(_extract_json(provider.generate(SYSTEM_PROMPT, prompt + extra)), expected_ids)
        except Exception as exc:
            last_error = exc
    raise SemanticChunkingError(f"Falha após {attempts} tentativa(s) de segmentação semântica: {last_error}") from last_error


def build_semantic_chunks(full_text: str, max_size: int, *, unit_kind: str, unit_ref: str | None = None, provider: Any | None = None, window_chars: int = 9000, min_chars: int = 1800, attempts: int = 2, prompt_version: str = "1", tokenizer: Any | None = None) -> list[dict[str, Any]]:
    if max_size <= 0:
        raise ValueError("max_size deve ser maior que zero")
    if len(full_text.strip()) < min_chars:
        return []
    if window_chars <= 0 or attempts <= 0:
        raise ValueError("window_chars e attempts devem ser maiores que zero")
    if provider is None:
        from .factory import get_llm_provider
        provider = get_llm_provider()
    max_atomic_size = max(256, min(max_size, max_size // 2))
    blocks = _atomic_blocks(full_text, max_atomic_size, tokenizer)
    if not blocks:
        raise SemanticChunkingError("Documento sem blocos para segmentação semântica.")
    groups = []
    for window in _windows(blocks, window_chars):
        groups.extend(_segment_window(provider, window, attempts))
    block_by_id = {block["id"]: block for block in blocks}
    length_fn = _token_length_factory(tokenizer)
    chunks = []
    for group_index, group in enumerate(groups):
        selected = [block_by_id[item] for item in group["ids"]]
        source_start, source_end = selected[0]["start"], selected[-1]["end"]
        source_text = full_text[source_start:source_end].strip()
        raw_span = full_text[source_start:source_end]
        trimmed_start = source_start + len(raw_span) - len(raw_span.lstrip())
        if not source_text:
            continue
        for subindex, (piece, local_start, _local_end) in enumerate(_split_large_block(source_text, max_size, tokenizer)):
            chunks.append({
                "text": piece,
                "full_unit_text": full_text.strip() if length_fn(full_text.strip()) <= max_size else None,
                "page_content": piece,
                "unit_kind": unit_kind,
                "unit_ref": unit_ref,
                "unit_id": f"{unit_kind}:{unit_ref or 'semantic'}:{group_index:04d}:{subindex:02d}",
                "chunk_index": len(chunks),
                "unit_length": len(full_text),
                "start": trimmed_start + local_start,
                "page_uncertain": False,
                "hierarchy_headers": [],
                "hierarchy_path": [value for value in (group.get("section"), group.get("topic")) if value],
                "parent_caput": None,
                "segment_kind": "semantic",
                "segment_ref": group.get("topic") or None,
                "semantic_topic": group.get("topic") or None,
                "semantic_section": group.get("section") or None,
                "semantic_source_units": group["ids"],
                "chunking_method": "ai_semantic",
                "chunking_model": getattr(provider, "model", None),
                "chunking_prompt_version": str(prompt_version),
            })
    if not chunks:
        raise SemanticChunkingError("A segmentação semântica não produziu chunks.")
    return chunks
