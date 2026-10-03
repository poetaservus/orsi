from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, fields
from math import ceil
from typing import Any


DEFAULT_SAFETY_BUFFER_TOKENS = 256


@dataclass(frozen=True, slots=True)
class ContextBudget:
    """Content-free token accounting for one projected model request."""

    model_context_limit: int
    system_message_tokens: int
    conversation_tokens: int
    structured_tool_history_tokens: int
    capability_schema_reserve: int
    requested_output_reserve: int
    safety_buffer: int
    total_estimated_request_tokens: int
    remaining_tokens: int

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("Context budget values must be non-negative integers.")
        expected_total = (
            self.system_message_tokens
            + self.conversation_tokens
            + self.structured_tool_history_tokens
            + self.capability_schema_reserve
            + self.requested_output_reserve
            + self.safety_buffer
        )
        if self.total_estimated_request_tokens != expected_total:
            raise ValueError("The context budget total does not match its components.")
        if self.remaining_tokens != max(
            0,
            self.model_context_limit - self.total_estimated_request_tokens,
        ):
            raise ValueError("The context budget remaining count is inconsistent.")

    @property
    def request_input_tokens(self) -> int:
        return (
            self.system_message_tokens
            + self.conversation_tokens
            + self.structured_tool_history_tokens
            + self.capability_schema_reserve
        )

    @property
    def fits(self) -> bool:
        return self.total_estimated_request_tokens <= self.model_context_limit

    def diagnostic_values(self) -> dict[str, int]:
        """Return only numeric values suitable for diagnostics and UI projection."""
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
        }


@dataclass(frozen=True, slots=True)
class ContextSelection:
    messages: list[dict[str, Any]]
    budget: ContextBudget


def select_context_request(
    inference,
    *,
    system_prompt: str,
    history: list[dict[str, Any]],
    reserved_tokens: int = 0,
    safety_buffer: int = DEFAULT_SAFETY_BUFFER_TOKENS,
    recovery_enabled: bool = False,
) -> ContextSelection:
    """Select complete turns and return the exact budget used for admission."""
    reserved_tokens = _validated_reserved_tokens(reserved_tokens)
    safety_buffer = _validated_safety_buffer(safety_buffer)
    system = {"role": "system", "content": system_prompt}
    if type(recovery_enabled) is not bool:
        raise TypeError("Context recovery selection requires an explicit boolean.")
    if recovery_enabled:
        from app.conversation.recovery import recover_context_request
        recovered = recover_context_request(inference, [system, *history], reserved_tokens=reserved_tokens,
                                            safety_buffer=safety_buffer)
        return ContextSelection(messages=recovered.messages, budget=recovered.budget)
    count_message_tokens(inference, [system])
    budget = max(
        1,
        context_length(inference)
        - response_reserve(inference)
        - reserved_tokens
        - safety_buffer,
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
    messages = [system, *selected]
    return ContextSelection(
        messages=messages,
        budget=calculate_context_budget(
            inference,
            messages,
            reserved_tokens=reserved_tokens,
            safety_buffer=safety_buffer,
        ),
    )


def select_context_messages(
    inference,
    *,
    system_prompt: str,
    history: list[dict[str, Any]],
    reserved_tokens: int = 0,
    safety_buffer: int = DEFAULT_SAFETY_BUFFER_TOKENS,
) -> list[dict[str, Any]]:
    """Select complete conversation turns that fit the model's context window."""
    return select_context_request(
        inference,
        system_prompt=system_prompt,
        history=history,
        reserved_tokens=reserved_tokens,
        safety_buffer=safety_buffer,
    ).messages


def calculate_context_budget(
    inference,
    messages: list[dict[str, Any]],
    *,
    reserved_tokens: int = 0,
    safety_buffer: int = DEFAULT_SAFETY_BUFFER_TOKENS,
) -> ContextBudget:
    """Calculate the one provider-neutral budget used by admission and display."""
    reserved_tokens = _validated_reserved_tokens(reserved_tokens)
    safety_buffer = _validated_safety_buffer(safety_buffer)
    system_tokens, conversation_tokens, tool_tokens = _message_token_breakdown(
        inference,
        messages,
    )
    # Counting can initialize a guarded lazy backend and discover lower limits.
    limit = context_length(inference)
    output_reserve = response_reserve(inference)
    total = (
        system_tokens
        + conversation_tokens
        + tool_tokens
        + reserved_tokens
        + output_reserve
        + safety_buffer
    )
    return ContextBudget(
        model_context_limit=limit,
        system_message_tokens=system_tokens,
        conversation_tokens=conversation_tokens,
        structured_tool_history_tokens=tool_tokens,
        capability_schema_reserve=reserved_tokens,
        requested_output_reserve=output_reserve,
        safety_buffer=safety_buffer,
        total_estimated_request_tokens=total,
        remaining_tokens=max(0, limit - total),
    )


def empty_context_budget(inference) -> ContextBudget:
    """Return the zero-use meter state when there is no active conversation."""
    limit = context_length(inference)
    return ContextBudget(
        model_context_limit=limit,
        system_message_tokens=0,
        conversation_tokens=0,
        structured_tool_history_tokens=0,
        capability_schema_reserve=0,
        requested_output_reserve=0,
        safety_buffer=0,
        total_estimated_request_tokens=0,
        remaining_tokens=limit,
    )


def estimated_context_tokens(
    inference,
    messages: list[dict[str, Any]],
    *,
    reserved_tokens: int = 0,
    safety_buffer: int = DEFAULT_SAFETY_BUFFER_TOKENS,
) -> int:
    if not messages:
        return 0
    return calculate_context_budget(
        inference,
        messages,
        reserved_tokens=reserved_tokens,
        safety_buffer=safety_buffer,
    ).total_estimated_request_tokens


def capability_schema_reserve(definitions, *, inference=None) -> int:
    """Conservatively reserve context for native tool schemas and wrappers."""
    values = tuple(definitions)
    if not values:
        return 0
    counter = getattr(inference, "count_capability_schema_tokens", None)
    if callable(counter):
        return _validated_reserved_tokens(counter(values))
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


def _validated_safety_buffer(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("The context safety buffer must be an integer.")
    if value < 0:
        raise ValueError("The context safety buffer cannot be negative.")
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


def _message_token_breakdown(
    inference,
    messages: list[dict[str, Any]],
) -> tuple[int, int, int]:
    if not messages:
        return 0, 0, 0
    total = count_message_tokens(inference, messages)
    system_messages = [
        message for message in messages if message.get("role") == "system"
    ]
    ordinary_messages = [
        message for message in messages if not _is_structured_tool_message(message)
    ]
    system = min(
        total,
        count_message_tokens(inference, system_messages) if system_messages else 0,
    )
    ordinary = min(
        total,
        count_message_tokens(inference, ordinary_messages) if ordinary_messages else 0,
    )
    conversation = min(max(0, ordinary - system), total - system)
    structured = total - system - conversation
    return system, conversation, structured


def _is_structured_tool_message(message: dict[str, Any]) -> bool:
    role = message.get("role")
    return (
        role in {"capability", "tool"}
        or "capability_calls" in message
        or "tool_calls" in message
    )


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
