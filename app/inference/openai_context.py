"""Offline Responses admission estimates; no extra API calls or context storage."""
from __future__ import annotations

from copy import deepcopy
import json
from math import ceil

from app.inference.openai_replay import OpenAIReplay, REPLAY_KEY, neutral_messages
from app.inference.protocol import _canonical_json, _provider_function_name


def estimate_input_tokens(items):
    """Estimate rendered input from UTF-8 bytes, counting opaque evidence once.

    This is not a tokenizer or the provider's decrypted-reasoning token count.
    Ciphertext has no known local token mapping: reserve its full byte length.
    Final provider usage remains authoritative, including cached input tokens.
    """
    total = 3
    for source in items:
        item = deepcopy(source)
        opaque = item.pop("encrypted_content", None)
        if opaque is not None and not isinstance(opaque, str):
            raise ValueError("OpenAI context evidence has invalid encrypted content.")
        encoded = _canonical_json(item).encode("utf-8")
        total += ceil(len(encoded) / 3) + 12
        if opaque is not None:
            total += len(opaque.encode("utf-8")) + 12
    return max(1, total)


def context_input_items(messages, model_id):
    """Count partial budget groups without requiring a complete tool exchange.

    The actual request converter still validates complete call/result pairing,
    strict nullable arguments and replay/transcript agreement before sending.
    """
    items = []
    for source, message in zip(messages, neutral_messages(messages), strict=True):
        if REPLAY_KEY in source:
            replay = OpenAIReplay.model_validate(source[REPLAY_KEY])
            if replay.model == model_id:
                items.extend(replay.items())
                continue
        if message.get("role") == "capability":
            items.append({"type": "function_call_output", "call_id": message.get("provider_call_id"),
                          "output": _canonical_json(message.get("result"))})
        elif "capability_calls" in message:
            if "content" in message:
                items.append({"role": "assistant", "content": message["content"]})
            for call in message["capability_calls"]:
                items.append({"type": "function_call", "call_id": call["provider_call_id"],
                    "name": _provider_function_name(call["capability"]), "arguments": _canonical_json(call["arguments"])})
        else:
            items.append(message)
    return items


def estimate_schema_tokens(tools):
    return ceil(len(json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode("utf-8")) / 3) + 48 * len(tools) if tools else 0
