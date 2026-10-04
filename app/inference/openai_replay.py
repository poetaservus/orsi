"""Bounded, private stateless Responses evidence; never a tool execution plan.

OpenCode's Responses protocol retains encrypted reasoning as provider metadata.
Here the complete supported output is retained, as required by OpenAI's docs.
See THIRD_PARTY_NOTICES.md and docs/cloud-openai-replay.md.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy

from pydantic import BaseModel, ConfigDict, Field, model_validator

REPLAY_KEY = "openai_response"
MAX_REPLAY_BYTES = 8 * 1024 * 1024


class OpenAIReplay(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    version: int = Field(default=1, ge=1, le=1)
    model: str = Field(min_length=1, max_length=128)
    response_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    # JSON text makes nested evidence immutable, including across model_copy.
    items_json: str = Field(min_length=2, max_length=MAX_REPLAY_BYTES, repr=False)

    @model_validator(mode="after")
    def validate_items(self):
        try:
            if len(self.items_json.encode("utf-8")) > MAX_REPLAY_BYTES:
                raise ValueError
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError
                    result[key] = value
                return result
            items = json.loads(self.items_json, object_pairs_hook=unique,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(items, list) or not 1 <= len(items) <= 64:
                raise ValueError
            ids, calls = set(), set()
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError
                identity = item.get("id")
                if not isinstance(identity, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", identity) is None or identity in ids:
                    raise ValueError
                ids.add(identity)
                if item.get("status") not in {None, "completed"}:
                    raise ValueError
                kind = item.get("type")
                if kind == "reasoning":
                    if not set(item).issubset({"type", "id", "status", "summary", "encrypted_content"}):
                        raise ValueError
                    if not isinstance(item.get("encrypted_content"), str) or not item["encrypted_content"]:
                        raise ValueError
                    summary = item.get("summary")
                    if not isinstance(summary, list) or any(not isinstance(part, dict)
                            or set(part) != {"type", "text"} or part["type"] != "summary_text"
                            or not isinstance(part["text"], str) for part in summary):
                        raise ValueError
                elif kind == "function_call":
                    if not set(item).issubset({"type", "id", "status", "call_id", "name", "arguments"}):
                        raise ValueError
                    for key in ("call_id", "name", "arguments"):
                        if not isinstance(item.get(key), str) or not item[key]:
                            raise ValueError
                    if item["call_id"] in calls:
                        raise ValueError
                    calls.add(item["call_id"])
                elif kind == "message":
                    if (not set(item).issubset({"type", "id", "status", "role", "content", "phase"})
                            or item.get("role") != "assistant"
                            or item.get("phase") not in {None, "commentary", "final_answer"}
                            or not isinstance(item.get("content"), list)):
                        raise ValueError
                    for part in item["content"]:
                        if not isinstance(part, dict):
                            raise ValueError
                        if part.get("type") == "output_text":
                            if (not set(part).issubset({"type", "text", "annotations", "logprobs"})
                                    or not isinstance(part.get("text"), str)
                                    or not isinstance(part.get("annotations", []), list)
                                    or not isinstance(part.get("logprobs", []), list)):
                                raise ValueError
                        elif part.get("type") != "refusal" or set(part) != {"type", "refusal"} or not isinstance(part["refusal"], str):
                            raise ValueError
                else:
                    raise ValueError
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ValueError("OpenAI response evidence is invalid or exceeds its storage limit.") from None
        return self

    @classmethod
    def from_payload(cls, payload: dict, model: str):
        # SDK optional None fields are not wire evidence.
        def compact(value):
            if isinstance(value, dict):
                return {key: compact(child) for key, child in value.items() if child is not None}
            if isinstance(value, list):
                return [compact(child) for child in value]
            return value
        try:
            return cls(model=model, response_id=payload.get("id"), items_json=json.dumps(
                compact(payload.get("output")), ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ValueError("OpenAI response evidence could not be retained safely.") from None

    def items(self) -> list[dict]:
        return json.loads(self.items_json)

    @property
    def call_ids(self) -> tuple[str, ...]:
        return tuple(item["call_id"] for item in self.items() if item["type"] == "function_call")

    @property
    def text(self) -> str:
        parts = [part for item in self.items() if item["type"] == "message" for part in item["content"]]
        refusals = [part["refusal"] for part in parts if part["type"] == "refusal"]
        return "".join(refusals or [part["text"] for part in parts if part["type"] == "output_text"])


class StoredOpenAIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    provider_message_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    replay: OpenAIReplay = Field(repr=False)


def neutral_messages(messages):
    """Validate the private extension, then remove it for generic chat adapters."""
    result = []
    for message in messages:
        value = deepcopy(message)
        if isinstance(value, dict) and REPLAY_KEY in value:
            if value.get("role") != "assistant":
                raise ValueError("OpenAI response evidence belongs to assistant messages.")
            try:
                OpenAIReplay.model_validate(value.pop(REPLAY_KEY))
            except (ValueError, TypeError):
                raise ValueError("OpenAI response evidence could not be loaded safely.") from None
        result.append(value)
    return result
