from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from typing import Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.state.storage import JsonStore
from app.inference.completion import CompletionMetadata, CompletionText
from app.agent.contracts import AgentRunResult, AgentRunStatus, SettledCall


class TurnHistoryError(RuntimeError):
    """Durable history is unavailable; do not start another operation."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    timestamp: str = Field(default_factory=_now)
    completion: CompletionMetadata | None = None
    completion_history: list[CompletionMetadata] | None = None
    turn_id: str | None = None
    stopped: bool = False


class RecoveredCall(BaseModel):
    """Content-free journal evidence when a crash interrupted trace persistence."""
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    call_id: str
    capability: str
    state: str
    result_success: bool | None = None
    error_code: str | None = None


class TurnRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    turn_id: str = Field(pattern=r"^turn-[1-9][0-9]*$")
    user_index: int = Field(ge=0)
    assistant_index: int | None = Field(default=None, ge=0)
    started_at: str = Field(default_factory=_now)
    ended_at: str | None = None
    outcome: AgentRunResult | None = None
    settled_calls: list[SettledCall] = Field(default_factory=list, max_length=32)
    recovered_calls: list[RecoveredCall] = Field(default_factory=list, max_length=32)


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()),
                                pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    messages: list[ChatMessage] = Field(default_factory=list)
    session_status: Literal["active", "closed"] = "active"
    turns: list[TurnRecord] = Field(default_factory=list, max_length=10_000)

    @model_validator(mode="after")
    def validate_turns(self):
        turn_ids, call_ids, provider_ids = set(), set(), set()
        for turn in self.turns:
            if turn.turn_id in turn_ids or turn.user_index >= len(self.messages):
                raise ValueError("Turn identities and message positions must be valid.")
            turn_ids.add(turn.turn_id)
            if self.messages[turn.user_index].role != "user":
                raise ValueError("Turns must start with a user message.")
            if (turn.outcome is None) != (turn.ended_at is None):
                raise ValueError("Terminal turns require a durable outcome and end time.")
            if turn.assistant_index is not None and (turn.assistant_index >= len(self.messages)
                    or self.messages[turn.assistant_index].role != "assistant"):
                raise ValueError("Turn output must reference an assistant message.")
            for settled in turn.settled_calls:
                identity = (settled.provider_message_id, settled.call.provider_call_id)
                if settled.result.call_id in call_ids or identity in provider_ids:
                    raise ValueError("Settled calls require unique internal and scoped provider identities.")
                call_ids.add(settled.result.call_id)
                provider_ids.add(identity)
        return self


class ConversationStore:
    """Active session, visible messages, settled traces and durable turn outcomes.

    The crash journal remains the execution authority. History never replays a call.
    """

    def __init__(self, path: Path, *, start_fresh: bool = False):
        self.path = Path(path)
        self._store = JsonStore(self.path)
        self._lock = RLock()
        with self._lock:
            if self.path.exists() and self.path.stat().st_size > 64 * 1024 * 1024:
                raise TurnHistoryError("Conversation outcomes exceed the safe storage limit. History was preserved.")
            if start_fresh:
                self._conversation = Conversation()
            else:
                try:
                    if self.path.exists():
                        value = self._store.load()
                        if not isinstance(value, dict) or "conversation_id" not in value:
                            raise ValueError("Existing history must retain its session identity.")
                        self._conversation = Conversation.model_validate_json(json.dumps(value))
                    else:
                        self._conversation = Conversation()
                except (TypeError, ValueError) as exc:
                    raise TurnHistoryError("Conversation outcomes could not be loaded safely. History was preserved.") from exc
            # A prior process never resumes or replays an unfinished turn.
            for turn in self._conversation.turns:
                if turn.outcome is None:
                    turn.outcome = AgentRunResult(status=AgentRunStatus.INTERNAL_FAILURE,
                        message="This turn was interrupted. Retained call outcomes remain valid; unknown mutations require review.",
                        steps=0, capability_calls=len(turn.settled_calls), protocol_failures=0)
                    turn.ended_at = _now()
                    turn.assistant_index = len(self._conversation.messages)
                    self._conversation.messages.append(ChatMessage(role="assistant", turn_id=turn.turn_id,
                        content=self._stopped_text(turn.outcome), stopped=True))
            self._conversation.session_status = "active"
            self._save()

    @property
    def session_id(self) -> str:
        return self._conversation.conversation_id

    def turns(self) -> list[TurnRecord]:
        with self._lock:
            return deepcopy(self._conversation.turns)

    def visible_messages(self) -> list[ChatMessage]:
        with self._lock:
            return deepcopy(self._conversation.messages)

    def begin_turn(self, text: str) -> str:
        with self._lock:
            if any(turn.outcome is None for turn in self._conversation.turns):
                raise TurnHistoryError("An unfinished turn must be settled before another operation can run.")
            proposed = self._conversation.model_copy(deep=True)
            turn_id = f"turn-{len(proposed.turns) + 1}"
            proposed.turns.append(TurnRecord(turn_id=turn_id, user_index=len(proposed.messages)))
            proposed.messages.append(ChatMessage(role="user", content=text, turn_id=turn_id))
            proposed.session_status = "active"
            self._commit(proposed)
            return turn_id

    def record_settled(self, turn_id: str, settled: SettledCall) -> None:
        with self._lock:
            proposed = self._conversation.model_copy(deep=True)
            turn = self._turn(proposed, turn_id)
            if turn.outcome is not None:
                raise TurnHistoryError("A stopped turn cannot execute or retain another call.")
            turn.settled_calls.append(settled)
            self._commit(proposed)

    def finish_turn(self, turn_id: str, outcome: AgentRunResult, answer: str | None = None) -> str:
        with self._lock:
            proposed = self._conversation.model_copy(deep=True)
            turn = self._turn(proposed, turn_id)
            if turn.outcome is not None:
                raise TurnHistoryError("A terminal turn cannot be completed twice.")
            # The result also contains calls on an observer failure. Never lose that evidence.
            retained = {item.result.call_id for item in turn.settled_calls}
            turn.settled_calls.extend(item for item in outcome.settled_calls if item.result.call_id not in retained)
            turn.outcome = outcome.model_copy(update={"settled_calls": ()})
            turn.ended_at = _now()
            turn.assistant_index = len(proposed.messages)
            value = answer if answer is not None else self._stopped_text(outcome)
            value = CompletionText(value, outcome.completion, outcome.completion_history)
            proposed.messages.append(ChatMessage(role="assistant", content=str(value), turn_id=turn_id,
                stopped=outcome.status != AgentRunStatus.COMPLETED,
                completion=outcome.completion if outcome.completion != CompletionMetadata() else None,
                completion_history=list(outcome.completion_history) if outcome.completion_history else None))
            self._commit(proposed)
            return value

    def reconcile_journal(self, records) -> None:
        """Recover outcome evidence across the journal/history write boundary, never arguments."""
        with self._lock:
            proposed = self._conversation.model_copy(deep=True)
            changed = False
            for turn in proposed.turns:
                known = {item.result.call_id for item in turn.settled_calls}
                recovered = {item.call_id for item in turn.recovered_calls}
                for record in records:
                    if (record.session_id != proposed.conversation_id or record.turn_id != turn.turn_id
                            or record.call_id in known or record.call_id in recovered):
                        continue
                    turn.recovered_calls.append(RecoveredCall(call_id=record.call_id, capability=record.capability,
                        state=record.state.value, result_success=record.result_success,
                        error_code=record.error_code.value if record.error_code else None))
                    changed = True
            if changed:
                self._commit(proposed)

    def agent_messages(self, *, capability_names: tuple[str, ...] | None = None) -> list[dict]:
        with self._lock:
            turns = {turn.user_index: turn for turn in self._conversation.turns}
            stopped = {turn.assistant_index: turn for turn in self._conversation.turns
                       if turn.outcome is not None and turn.outcome.partial_text is not None}
            history = []
            for index, message in enumerate(self._conversation.messages):
                if index in stopped:
                    history.append({"role": "assistant", "content": self._stopped_text(stopped[index].outcome)})
                history.append({"role": message.role, "content": message.content})
                turn = turns.get(index)
                if turn is not None:
                    for settled in turn.settled_calls:
                        if capability_names is None or settled.call.capability in capability_names:
                            history.extend(settled.messages())
                        else:
                            if settled.assistant_text is not None:
                                history.append({"role": "assistant", "content": settled.assistant_text})
                            result = settled.result
                            output = json.dumps(result.output, ensure_ascii=False)[:2_000]
                            history.append({"role": "assistant", "content":
                                f"Retained settled call: {result.capability}, call {result.call_id}, "
                                f"success {result.success}, error {result.error.code.value if result.error else None}. "
                                f"Reported output (bounded): {output}. Do not replay this operation automatically."})
                    for recovered in turn.recovered_calls:
                        history.append({"role": "assistant", "content":
                            f"Retained call outcome: {recovered.capability}, call {recovered.call_id}, "
                            f"state {recovered.state}, success {recovered.result_success}. "
                            "Detailed trace was interrupted. Do not replay this operation automatically."})
            return history

    def close_session(self) -> None:
        with self._lock:
            proposed = self._conversation.model_copy(deep=True)
            proposed.session_status = "closed"
            self._commit(proposed)

    @staticmethod
    def _turn(conversation: Conversation, turn_id: str) -> TurnRecord:
        return next(turn for turn in conversation.turns if turn.turn_id == turn_id)

    @staticmethod
    def _stopped_text(outcome: AgentRunResult) -> str:
        return f"Turn stopped ({outcome.status.value}). {outcome.message or 'The response was stopped.'}"

    def _commit(self, proposed: Conversation) -> None:
        proposed.updated_at = _now()
        encoded = proposed.model_dump_json(exclude_none=True)
        if len(encoded.encode("utf-8")) > 64 * 1024 * 1024:
            raise TurnHistoryError("Conversation outcomes exceed the safe storage limit. Start a new session after review.")
        # Validate and save before adopting the new state.
        validated = Conversation.model_validate_json(encoded)
        try:
            self._store.save(validated.model_dump(mode="json", exclude_none=True))
        except OSError as exc:
            raise TurnHistoryError("Conversation outcomes could not be persisted safely. Review settled calls before retrying.") from exc
        self._conversation = validated

    def append(self, role: Literal["user", "assistant"], content: str) -> None:
        completion = getattr(content, "completion", None) if role == "assistant" else None
        history = getattr(content, "completion_history", None) if role == "assistant" else None
        text = str(content) if completion and completion.incomplete else str(content).strip()
        if not text:
            raise ValueError("Conversation messages cannot be empty.")
        with self._lock:
            proposed = self._conversation.model_copy(deep=True)
            informative = completion is not None and (completion != CompletionMetadata()
                or any(item != CompletionMetadata() for item in history or ()))
            proposed.messages.append(ChatMessage(role=role, content=text,
                completion=completion if informative else None,
                completion_history=list(history) if informative and history else None))
            self._commit(proposed)

    def messages(self) -> list[dict[str, str]]:
        with self._lock:
            return [
                {"role": message.role, "content": message.content}
                for message in self._conversation.messages
            ]

    def new_session(self, *, preserve_history: bool = False) -> None:
        """Start empty; startup archives the prior session before replacing it."""
        with self._lock:
            if preserve_history and (self._conversation.messages or self._conversation.turns):
                archived = self._conversation.model_copy(deep=True)
                archived.session_status = "closed"
                archive_path = self.path.parent / "archives" / f"{uuid.uuid4().hex}.json"
                try:
                    JsonStore(archive_path).save(archived.model_dump(mode="json", exclude_none=True))
                except OSError as exc:
                    raise TurnHistoryError(
                        "The previous conversation could not be archived safely. History was preserved."
                    ) from exc
            self._commit(Conversation())

    def _save(self) -> None:
        self._commit(self._conversation)
