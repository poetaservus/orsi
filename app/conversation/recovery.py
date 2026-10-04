"""Deterministic request projections; durable history remains the original evidence.

No model-generated summaries or additional inference requests. User requirements,
system policy, call arguments and scoped call/result identities are never trimmed.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256

from app.conversation.context import ContextBudget, calculate_context_budget


@dataclass(frozen=True, slots=True)
class RecoveredContext:
    messages: list[dict]
    budget: ContextBudget
    projected_results: int = 0
    compacted: bool = False


def _encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _text_excerpt(text: str, limit: int, anchors: tuple[str, ...]) -> str:
    if len(text) <= limit:
        return text
    # Explicit boundaries prevent excerpts from looking like contiguous file content.
    windows = [(0, limit // 4), (len(text) - limit // 4, len(text))]
    remaining = limit // 2
    for anchor in anchors:
        match = re.search(re.escape(anchor), text, re.IGNORECASE)
        position = match.start() if match is not None else -1
        if position < 0 or any(start <= position < end for start, end in windows):
            continue
        width = min(remaining, max(256, len(anchor) + 128))
        if width <= 0:
            break
        start = max(0, position - 64)
        windows.append((start, min(len(text), start + width)))
        remaining -= width
    windows.sort()
    parts, previous_end = [], 0
    for start, end in windows:
        start = max(start, previous_end)
        if start >= end:
            continue
        if start > previous_end:
            parts.append(f"\n[Context projection: {start - previous_end} characters omitted]\n")
        parts.append(text[start:end])
        previous_end = end
    return "".join(parts)


def _project_value(value, *, text_limit: int, item_limit: int, anchors: tuple[str, ...], depth=0):
    if isinstance(value, str):
        return _text_excerpt(value, text_limit, anchors)
    if isinstance(value, list):
        if depth >= 8:
            return {"context_projection_excerpt": _text_excerpt(_encoded(value).decode("utf-8"), text_limit, anchors)}
        if len(value) > item_limit:
            half = max(1, item_limit // 2)
            values = [*value[:half], {"context_projection_omitted_items": len(value) - 2 * half}, *value[-half:]]
        else:
            values = value
        return [_project_value(item, text_limit=text_limit, item_limit=item_limit, anchors=anchors,
                               depth=depth + 1) for item in values]
    if isinstance(value, dict):
        if depth >= 8:
            return {"context_projection_excerpt": _text_excerpt(_encoded(value).decode("utf-8"), text_limit, anchors)}
        return {key: (item if key in {"path", "source", "destination", "name", "sha256", "call_id"}
                      or key.endswith("_path") else
                      _project_value(item, text_limit=text_limit, item_limit=item_limit, anchors=anchors,
                                     depth=depth + 1)) for key, item in value.items()}
    return value


def _anchors(messages: list[dict]) -> tuple[str, ...]:
    requirements = "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
    # Quoted snippets, selectors and identifiers are literal hints, never routing decisions.
    quoted = re.findall(r'[`"\']([^`"\'\n]{3,200})[`"\']', requirements)
    tokens = re.findall(r"[.#]?[\w-]{4,}(?:[./\\][\w.-]+)*", requirements)
    return tuple(dict.fromkeys([*quoted[-8:], *tokens[-24:]]))


def _project_result(message: dict, *, text_limit: int, item_limit: int, anchors: tuple[str, ...]) -> bool:
    result = message.get("result")
    if message.get("role") != "capability" or not isinstance(result, dict):
        return False
    output = result.get("output")
    if output is None:
        return False
    raw = _encoded(output)
    if len(raw) <= text_limit:
        return False
    projected = _project_value(output, text_limit=text_limit, item_limit=item_limit, anchors=anchors)
    encoded_projection = _encoded(projected)
    # Very broad dictionaries can exceed the budget despite per-value projection.
    if len(encoded_projection) > text_limit * 3:
        projected = {"context_projection_excerpt": _text_excerpt(raw.decode("utf-8"), text_limit, anchors)}
        if isinstance(output, dict):
            projected.update({key: value for key, value in output.items()
                if key in {"path", "source", "destination", "name", "sha256", "call_id", "content_is_untrusted"}
                or key.endswith("_path")})
        encoded_projection = _encoded(projected)
    if len(encoded_projection) >= len(raw):
        return False
    result["output"] = projected
    metadata = result.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("Capability result metadata must be an object.")
    existing = metadata.get("context_projection", {})
    if not isinstance(existing, dict):
        existing = {}
    metadata["context_projection"] = {
        "complete": False,
        "original_output_bytes": existing.get("original_output_bytes", len(raw)),
        "original_output_sha256": existing.get("original_output_sha256", sha256(raw).hexdigest()),
        "projected_output_bytes": len(encoded_projection),
        "notice": "Excerpt only. Omitted content is not evidence of absence. Do not reconstruct it or replay mutations. Use an advertised read/search capability when more evidence is needed.",
    }
    return True


def recover_context_request(inference, messages: list[dict], *, reserved_tokens: int = 0,
                            safety_buffer: int = 256, projection_enabled: bool = True) -> RecoveredContext:
    """Project results first, compact old assistant material only on admission pressure.

    If protected content still cannot fit, return a non-fitting budget rather than
    silently discard a requirement, split a tool exchange or send an empty request.
    """
    projected = deepcopy(messages)
    openai_context = getattr(inference, "supports_openai_context", False) is True
    if openai_context or any("openai_response" in message for message in messages):
        # Stateless provider evidence and the results paired with it must stay
        # untouched. OpenAI projections preserve the fitting prefix and only
        # excerpt explicit capability results under actual admission pressure.
        admission = calculate_context_budget(inference, projected,
            reserved_tokens=reserved_tokens, safety_buffer=safety_buffer)
        if not openai_context or admission.fits or not projection_enabled:
            return RecoveredContext(projected, admission)
    anchors = _anchors(messages)
    count = sum(_project_result(m, text_limit=4096, item_limit=16, anchors=anchors) for m in projected)
    def budget(values):
        return calculate_context_budget(inference, values, reserved_tokens=reserved_tokens, safety_buffer=safety_buffer)
    admission = budget(projected)
    if admission.fits:
        return RecoveredContext(projected, admission, count)

    latest_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=0)
    latest_result = max((i for i, m in enumerate(messages) if m.get("role") == "capability"), default=-1)
    compacted = deepcopy(projected)
    changed = False
    for index, message in enumerate(compacted):
        if message.get("role") == "capability" and index != latest_result:
            # Re-project original evidence, not an already excerpted string.
            message = deepcopy(messages[index])
            if _project_result(message, text_limit=256, item_limit=4, anchors=anchors):
                compacted[index] = message
                changed = True
        elif (index < latest_user and message.get("role") == "assistant" and "capability_calls" not in message
              and "openai_response" not in message
              and isinstance(message.get("content"), str) and len(message["content"]) > 256):
            message["content"] = _text_excerpt(message["content"], 256, ())
            changed = True
    admission = budget(compacted)
    if not admission.fits and latest_result >= 0:
        latest = deepcopy(messages[latest_result])
        if _project_result(latest, text_limit=256, item_limit=4, anchors=anchors):
            compacted[latest_result] = latest
            changed = True
            admission = budget(compacted)
    return RecoveredContext(compacted, admission, count, changed)
