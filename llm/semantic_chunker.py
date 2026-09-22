from __future__ import annotations

import json
import re
from typing import Any

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
    candidates: list[str] = []

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
                elif char == "\\\\":
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

    expected = list(expected_ids)
    seen: list[str] = []
    normalized: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            raise SemanticChunkingError("Grupo semântico inválido: esperado objeto JSON.")
        ids = group.get("ids")
        if not isinstance(ids, list) or not ids:
            raise SemanticChunkingError("Grupo semântico sem IDs.")
        ids = [str(item).strip() for item in ids if str(item).strip()]
        topic = str(group.get("topic") or "").strip()[:160]
        section = str(group.get("section") or "").strip()[:160]
        normalized.append({"ids": ids, "topic": topic, "section": section})
        seen.extend(ids)

    if seen != expected:
        raise SemanticChunkingError(
            "LLM alterou a ordem, duplicou ou omitiu trechos: "
            f"esperado={len(expected)} IDs, retornado={len(seen)}."
        )

    if len(set(seen)) != len(seen):
        raise SemanticChunkingError("LLM retornou IDs duplicados.")
    return normalized


def _split_large_block(text: str, max_size: int) -> list[tuple[str, int, int]]:
    if len(text) <= max_size:
        stripped = text.strip()
        left = len(text) - len(text.lstrip())
        right = left + len(stripped)
        return [(stripped, left, right)] if stripped else []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_size,
        chunk_overlap=0,
        separators=["\n\n", "\n", ". ", "; ", " ", ""],
    )
    pieces = [piece for piece in splitter.split_text(text) if piece.strip()]
    out: list[tuple[str, int, int]] = []
    cursor = 0
    for piece in pieces:
        found = text.find(piece, cursor)
        if found < 0:
            raise SemanticChunkingError("Não foi possível mapear subchunk semântico ao texto original.")
        end = found + len(piece)
        out.append((piece, found, end))
        cursor = end
    return out


def _atomic_blocks(text: str, max_atomic_size: int) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
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
        for piece, relative_start, relative_end in _split_large_block(raw, max_atomic_size):
            start = raw_start + relative_start
            end = raw_start + relative_end
            blocks.append(
                {
                    "id": f"B{sequence:04d}",
                    "text": text[start:end],
                    "start": start,
                    "end": end,
                }
            )
            sequence += 1
    return blocks


def _windows(blocks: list[dict[str, Any]], window_chars: int) -> list[list[dict[str, Any]]]:
    windows: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_size = 0
    for block in blocks:
        block_size = len(block["text"]) + 40
        if current and current_size + block_size > window_chars:
            windows.append(current)
            current = []
            current_size = 0
        current.append(block)
        current_size += block_size
    if current:
        windows.append(current)
    return windows


def _prompt_for_window(blocks: list[dict[str, Any]]) -> str:
    parts = [
        "Agrupe os trechos abaixo por continuidade semântica. "
        "Não altere os IDs e não produza o texto dos trechos na resposta."
    ]
    for block in blocks:
        parts.append(f"ID {block['id']}\n{block['text']}\nFIM {block['id']}")
    return "\n\n".join(parts)


def _segment_window(provider: Any, blocks: list[dict[str, Any]], attempts: int) -> list[dict[str, Any]]:
    expected_ids = [block["id"] for block in blocks]
    prompt = _prompt_for_window(blocks)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            extra = ""
            if attempt > 1:
                extra = (
                    "\n\nATENÇÃO: sua resposta anterior foi inválida. "
                    "Responda apenas com JSON válido no formato exigido, cobrindo cada ID exatamente uma vez."
                )
            response = provider.generate(SYSTEM_PROMPT, prompt + extra)
            return _validate_groups(_extract_json(response), expected_ids)
        except Exception as exc:
            last_error = exc
    raise SemanticChunkingError(
        f"Falha após {attempts} tentativa(s) de segmentação semântica: {last_error}"
    ) from last_error


def build_semantic_chunks(
    full_text: str,
    max_size: int,
    *,
    unit_kind: str,
    unit_ref: str | None = None,
    provider: Any | None = None,
    window_chars: int = 9000,
    min_chars: int = 1800,
    attempts: int = 2,
) -> list[dict[str, Any]]:
    if max_size <= 0:
        raise ValueError("max_size deve ser maior que zero")
    if len(full_text.strip()) < min_chars:
        return []
    if window_chars <= 0:
        raise ValueError("window_chars deve ser maior que zero")
    if attempts <= 0:
        raise ValueError("attempts deve ser maior que zero")

    if provider is None:
        from .factory import get_llm_provider
        provider = get_llm_provider()

    max_atomic_size = max(256, min(max_size, max_size // 2))
    blocks = _atomic_blocks(full_text, max_atomic_size)
    if not blocks:
        raise SemanticChunkingError("Documento sem blocos para segmentação semântica.")

    groups: list[dict[str, Any]] = []
    for window in _windows(blocks, window_chars):
        groups.extend(_segment_window(provider, window, attempts))

    block_by_id = {block["id"]: block for block in blocks}
    chunks: list[dict[str, Any]] = []
    for group_index, group in enumerate(groups):
        selected = [block_by_id[item] for item in group["ids"]]
        source_start = selected[0]["start"]
        source_end = selected[-1]["end"]
        source_text = full_text[source_start:source_end].strip()
        raw_span = full_text[source_start:source_end]
        leading = len(raw_span) - len(raw_span.lstrip())
        trimmed_start = source_start + leading
        if not source_text:
            continue

        pieces = _split_large_block(source_text, max_size)
        for subindex, (piece, local_start, local_end) in enumerate(pieces):
            absolute_start = trimmed_start + local_start
            absolute_end = trimmed_start + local_end
            chunks.append(
                {
                    "text": piece,
                    "full_unit_text": full_text.strip() if len(full_text.strip()) <= max_size else None,
                    "page_content": piece,
                    "unit_kind": unit_kind,
                    "unit_ref": unit_ref,
                    "unit_id": f"{unit_kind}:{unit_ref or 'semantic'}:{group_index:04d}:{subindex:02d}",
                    "chunk_index": len(chunks),
                    "unit_length": len(full_text),
                    "start": absolute_start,
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
                    "chunking_prompt_version": "1",
                }
            )

    if not chunks:
        raise SemanticChunkingError("A segmentação semântica não produziu chunks.")
    return chunks
