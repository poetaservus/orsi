"""Bounded Responses SSE state; deltas never authorize tool execution.

Terminal handling adapts the pinned OpenCode Responses protocol. OpenAI's
documented typed events and complete response payload govern acceptance.
"""
from __future__ import annotations

import json
import logging
from time import monotonic

from app.inference.completion import CompletionMetadata, IncompleteResponseError, ResponseFailureReason

log = logging.getLogger(__name__)
# Allow a 128,000-token response with multiple deltas per token and control
# events while retaining finite protocol limits independent of model settings.
_MAX_EVENTS = 262_144
_MAX_EVENT_BYTES = 64 * 1024 * 1024
_MAX_TEXT_CHARS = 1_000_000
_TERMINALS = {"response.completed": "completed", "response.incomplete": "incomplete", "response.failed": "failed"}
_PASSIVE = {"response.in_progress", "response.content_part.done", "response.output_text.done",
    "response.output_text.annotation.added", "response.refusal.done", "response.function_call_arguments.done",
    "response.reasoning_summary_part.added", "response.reasoning_summary_part.done",
    "response.reasoning_summary_text.delta", "response.reasoning_summary_text.done",
    "response.reasoning_text.delta", "response.reasoning_text.done"}
_KNOWN_EVENTS = _PASSIVE | set(_TERMINALS) | {"response.created", "error",
    "response.output_item.added", "response.content_part.added", "response.output_text.delta",
    "response.refusal.delta", "response.function_call_arguments.delta", "response.output_item.done"}


class StreamProtocolError(ValueError):
    """A fixed validation category, never a provider-controlled message."""
    def __init__(self, failure_reason: ResponseFailureReason):
        metadata = CompletionMetadata(failure_reason=failure_reason)
        self.failure_reason = metadata.failure_reason
        super().__init__(metadata.failure_message)


class ResponsesStreamState:
    def __init__(self, observer=None):
        self.observer = observer
        self.started = False
        self.identity = None
        self.sequence = -1
        self.events = 0
        self.bytes = 0
        self.chars = 0
        self.texts, self.refusals = [], []
        self.items, self.parts = {}, {}
        self._last_publish = 0.0
        self.last_event = "none"

    @property
    def partial_text(self):
        return "".join(self.refusals or self.texts) or None

    def publish(self, *, force=False):
        if self.observer is None or not force and monotonic() - self._last_publish < 0.05:
            return
        self._last_publish = monotonic()
        try:
            self.observer(self.partial_text or "")
        except Exception:
            log.warning("OpenAI text preview observer failed.")
            self.observer = None

    def interrupted(self, reason="error", *, failure_reason: ResponseFailureReason = "stream_ended"):
        self.publish(force=True)
        completion = CompletionMetadata(finish_reason=reason, interrupted=True,
            failure_reason="cancelled" if reason == "cancelled" else failure_reason)
        log.warning("OpenAI stream interruption: reason=%s event=%s events=%s sequence=%s bytes=%s text_chars=%s",
            completion.failure_reason, self.last_event, self.events, self.sequence, self.bytes, self.chars)
        return IncompleteResponseError(completion.failure_message, completion, self.partial_text)

    def accept(self, event):
        value = event.model_dump(mode="json", exclude_none=True)
        kind = value.get("type")
        self.last_event = kind if isinstance(kind, str) and kind in _KNOWN_EVENTS else "unrecognized"
        self.events += 1
        self.bytes += len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if self.events > _MAX_EVENTS or self.bytes > _MAX_EVENT_BYTES:
            raise StreamProtocolError("protocol_limit")
        sequence, kind = value.get("sequence_number"), value.get("type")
        if type(sequence) is not int or sequence != self.sequence + 1:
            raise StreamProtocolError("invalid_sequence")
        self.sequence = sequence
        if kind == "response.created":
            payload = value.get("response")
            if self.started or not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
                raise StreamProtocolError("invalid_identity")
            self.started, self.identity = True, payload["id"]
            self.publish(force=True)
            return None
        if not self.started:
            raise StreamProtocolError("missing_creation")
        if kind in _TERMINALS:
            payload = value.get("response")
            if (not isinstance(payload, dict) or payload.get("id") != self.identity
                    or payload.get("status") != _TERMINALS[kind]):
                raise StreamProtocolError("invalid_terminal")
            output = payload.get("output")
            if isinstance(output, list):
                for index, item in self.items.items():
                    if index >= len(output) or not isinstance(output[index], dict) or any(
                            output[index].get(key) != item.get(key) for key in ("id", "type")):
                        raise StreamProtocolError("contradictory_output")
            self.publish(force=True)
            return payload
        if kind == "error":
            # Caller maps only known error codes; messages/params are private.
            return {"id": self.identity, "status": "failed", "error": {"code": value.get("code")}, "output": []}
        if kind == "response.output_item.added":
            index, item = value.get("output_index"), value.get("item")
            if (type(index) is not int or index != len(self.items) or index >= 64 or not isinstance(item, dict)
                    or item.get("type") not in {"message", "function_call", "reasoning"}
                    or not isinstance(item.get("id"), str)):
                raise StreamProtocolError("invalid_output_item")
            self.items[index] = item
        elif kind == "response.content_part.added":
            index, part_index, part = value.get("output_index"), value.get("content_index"), value.get("part")
            item = self.items.get(index)
            if (item is None or item.get("type") != "message" or type(part_index) is not int
                    or not 0 <= part_index < 64 or (index, part_index) in self.parts or not isinstance(part, dict)):
                raise StreamProtocolError("invalid_message_part")
            self.parts[index, part_index] = part.get("type")
        elif kind in {"response.output_text.delta", "response.refusal.delta"}:
            index, part_index = value.get("output_index"), value.get("content_index")
            item, delta = self.items.get(index), value.get("delta")
            expected = "output_text" if kind == "response.output_text.delta" else "refusal"
            if (item is None or item.get("id") != value.get("item_id")
                    or self.parts.get((index, part_index)) != expected or not isinstance(delta, str)):
                raise StreamProtocolError("invalid_text")
            self.chars += len(delta)
            if self.chars > _MAX_TEXT_CHARS:
                raise StreamProtocolError("text_limit")
            (self.texts if expected == "output_text" else self.refusals).append(delta)
            self.publish()
        elif kind == "response.function_call_arguments.delta":
            item = self.items.get(value.get("output_index"))
            if item is None or item.get("type") != "function_call" or item.get("id") != value.get("item_id"):
                raise StreamProtocolError("orphan_tool_arguments")
        elif kind == "response.output_item.done":
            item = self.items.get(value.get("output_index"))
            final = value.get("item")
            if item is None or not isinstance(final, dict) or any(final.get(key) != item.get(key) for key in ("id", "type")):
                raise StreamProtocolError("unknown_completed_item")
        elif kind not in _PASSIVE:
            raise StreamProtocolError("unsupported_event")
        return None
