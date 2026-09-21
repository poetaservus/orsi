"""Bounded structured-call repair adapted from OpenCode's tool-call flow.

Portions of this file are substantially derived from OpenCode's repair and
invalid-tool handling patterns: https://github.com/anomalyco/opencode
(MIT License, Copyright (c) 2025 opencode). See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


_JSON_FENCE = re.compile(r"\A```(?:json)?\s*(.*?)\s*```\Z", re.IGNORECASE | re.DOTALL)
_MAX_STRUCTURED_BYTES = 2 * 1024 * 1024


class StructuredCallDecodeError(ValueError):
    """A model value could not be decoded as one bounded JSON object."""


def decode_json_object(value: Any) -> tuple[dict[str, Any], bool]:
    """Decode one complete JSON object and apply only unambiguous syntax repairs.

    This deliberately never searches surrounding prose for JSON. Repairs are
    limited to an enclosing JSON fence, trailing commas outside strings, and at
    most two missing closing braces/brackets.
    """

    if isinstance(value, dict):
        result = deepcopy(value)
        _validate_json_object(result)
        return result, False
    if not isinstance(value, str):
        raise StructuredCallDecodeError("Structured arguments must be a JSON object.")

    raw = value.strip()
    if not raw:
        raise StructuredCallDecodeError("Structured arguments cannot be empty.")
    try:
        if len(raw.encode("utf-8")) > _MAX_STRUCTURED_BYTES:
            raise StructuredCallDecodeError("Structured arguments exceed the size limit.")
    except UnicodeError as exc:
        raise StructuredCallDecodeError("Structured arguments are not valid UTF-8.") from exc

    candidates: list[tuple[str, bool]] = [(raw, False)]
    fenced = _JSON_FENCE.fullmatch(raw)
    if fenced is not None:
        candidates.append((fenced.group(1).strip(), True))

    base_candidates = tuple(candidates)
    for candidate, _repaired in base_candidates:
        without_trailing = _remove_trailing_commas(candidate)
        if without_trailing != candidate:
            candidates.append((without_trailing, True))
        closed = _close_unambiguous(candidate)
        if closed is not None:
            candidates.append((closed, True))
        closed_without_trailing = _close_unambiguous(without_trailing)
        if closed_without_trailing is not None:
            candidates.append((closed_without_trailing, True))

    seen: set[str] = set()
    for candidate, repaired in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(
                candidate,
                object_pairs_hook=_unique_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    ValueError("non-finite JSON number")
                ),
            )
            if not isinstance(parsed, dict):
                continue
            _validate_json_object(parsed)
            return parsed, repaired
        except (json.JSONDecodeError, TypeError, ValueError, UnicodeError, RecursionError):
            continue
    raise StructuredCallDecodeError("Structured arguments are not a valid JSON object.")


def decode_constrained_decision(value: Any) -> dict[str, Any]:
    """Decode the exact no-prose shape used by the text-only tool fallback."""

    decision, _repaired = decode_json_object(value)
    unexpected = set(decision) - {"tool", "arguments", "response"}
    if unexpected:
        raise StructuredCallDecodeError(
            "The structured decision contained unexpected fields: "
            + ", ".join(sorted(unexpected))
        )
    if "tool" not in decision or "arguments" not in decision:
        raise StructuredCallDecodeError(
            "A structured decision requires tool and arguments fields."
        )
    tool = decision["tool"]
    arguments = decision["arguments"]
    response = decision.get("response")
    if tool is not None and not isinstance(tool, str):
        raise StructuredCallDecodeError("The tool field must be a name or null.")
    if not isinstance(arguments, dict):
        raise StructuredCallDecodeError("The arguments field must be an object.")
    if response is not None and not isinstance(response, str):
        raise StructuredCallDecodeError("The response field must be text when present.")
    if tool is None:
        if arguments:
            raise StructuredCallDecodeError("A conversational decision must use empty arguments.")
        if response is None or not response.strip():
            raise StructuredCallDecodeError("A conversational decision requires a response.")
    elif response is not None:
        raise StructuredCallDecodeError("A tool decision cannot also contain assistant text.")
    return decision


def _remove_trailing_commas(value: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(value):
        character = value[index]
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue
        if character == ",":
            lookahead = index + 1
            while lookahead < len(value) and value[lookahead].isspace():
                lookahead += 1
            if lookahead < len(value) and value[lookahead] in "}]":
                index += 1
                continue
        output.append(character)
        index += 1
    return "".join(output)


def _close_unambiguous(value: str) -> str | None:
    stack: list[str] = []
    in_string = False
    escaped = False
    pairs = {"{": "}", "[": "]"}
    for character in value:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in pairs:
            stack.append(pairs[character])
        elif character in "}]":
            if not stack or stack.pop() != character:
                return None
    if in_string or not stack or len(stack) > 2:
        return None
    return value + "".join(reversed(stack))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _validate_json_object(value: dict[str, Any]) -> None:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StructuredCallDecodeError(
            "Structured arguments contain unsupported JSON values."
        ) from exc
    if len(encoded) > _MAX_STRUCTURED_BYTES:
        raise StructuredCallDecodeError("Structured arguments exceed the size limit.")
