from __future__ import annotations

import json
from copy import deepcopy
from math import ceil
from typing import Any


def select_context_messages(
    inference,
    *,
    system_prompt: str,
    history: list[dict[str, Any]],
    reserved_tokens: int = 0,
) -> list[dict[str, Any]]:
    """Select complete conversation turns that fit the model's context window."""
    reserved_tokens = _validated_reserved_tokens(reserved_tokens)
    system = {"role": "system", "content": system_prompt}
    count_message_tokens(inference, [system])
    budget = max(
        1,
        context_length(inference) - response_reserve(inference) - reserved_tokens,
    )
    selected: list[dict[str, Any]] = []
    for group in reversed(conversation_turn_groups(history)):
        candidate_group = deepcopy(group)
        if count_message_tokens(inference, [system, *candidate_group, *selected]) <= budget:
            selected[0:0] = candidate_group
            continue
        if (
            len(candidate_group) == 1
            and set(candidate_group[0]) == {"role", "content"}
            and isinstance(candidate_group[0].get("content"), str)
        ):
            truncated = _largest_fitting_suffix(
                inference,
                system,
                candidate_group[0],
                selected,
                budget,
            )
            if truncated is not None:
                selected.insert(0, truncated)
        break
    return [system, *selected]


def estimated_context_tokens(
    inference,
    messages: list[dict[str, Any]],
    *,
    reserved_tokens: int = 0,
) -> int:
    if not messages:
        return 0
    reserved_tokens = _validated_reserved_tokens(reserved_tokens)
    return min(
        context_length(inference),
        count_message_tokens(inference, messages)
        + response_reserve(inference)
        + reserved_tokens,
    )


def capability_schema_reserve(definitions) -> int:
    """Conservatively reserve context for native tool schemas and wrappers."""
    values = tuple(definitions)
    if not values:
        return 0
    payload = [value.model_dump(mode="json") for value in values]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return ceil(len(encoded) / 3) + 48 * len(values)


def _validated_reserved_tokens(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("Reserved context tokens must be an integer.")
    if value < 0:
        raise ValueError("Reserved context tokens cannot be negative.")
    return value


def count_message_tokens(inference, messages: list[dict[str, Any]]) -> int:
    counter = getattr(inference, "count_message_tokens", None)
    countable = [
        message
        if set(message) == {"role", "content"}
        and isinstance(message.get("content"), str)
        else {
            "role": str(message.get("role", "assistant")),
            "content": json.dumps(
                message,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        for message in messages
    ]
    if callable(counter):
        return max(1, int(counter(countable)))
    characters = sum(len(message["content"]) for message in countable)
    return max(1, (characters + 3) // 4 + 4 * len(countable) + 3)


def context_length(inference) -> int:
    return max(512, int(getattr(inference, "context_length", 8192)))


def response_reserve(inference) -> int:
    configured = max(32, int(getattr(inference, "max_response_tokens", 512)))
    return min(configured, context_length(inference) // 2)


def conversation_turn_groups(history: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Keep each user turn and its tool trace atomic during context trimming."""
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for message in history:
        if message.get("role") == "user" and current:
            groups.append(current)
            current = []
        current.append(message)
    if current:
        groups.append(current)
    return groups


def _largest_fitting_suffix(
    inference,
    system: dict[str, str],
    message: dict[str, Any],
    selected: list[dict[str, Any]],
    budget: int,
) -> dict[str, str] | None:
    marker = "[Earlier content truncated]\n"
    content = message["content"]
    low, high = 0, len(content)
    best = None
    while low <= high:
        keep = (low + high) // 2
        shortened = marker + (content[-keep:] if keep else "")
        candidate_message = {"role": message["role"], "content": shortened}
        if count_message_tokens(
            inference,
            [system, candidate_message, *selected],
        ) <= budget:
            best = candidate_message
            low = keep + 1
        else:
            high = keep - 1
    return best
