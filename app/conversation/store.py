from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.state.storage import JsonStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    timestamp: str = Field(default_factory=_now)


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    messages: list[ChatMessage] = Field(default_factory=list)


class ConversationStore:
    """One atomic text conversation. No action, tool, or audit event types exist here."""

    def __init__(self, path: Path, *, start_fresh: bool = False):
        self.path = Path(path)
        self._store = JsonStore(self.path)
        self._lock = RLock()
        with self._lock:
            if start_fresh:
                self._conversation = Conversation()
            else:
                value = self._store.load()
                try:
                    self._conversation = Conversation.model_validate(value) if value else Conversation()
                except (TypeError, ValueError):
                    self._conversation = Conversation()
            self._save()

    def append(self, role: Literal["user", "assistant"], content: str) -> None:
        text = str(content).strip()
        if not text:
            raise ValueError("Conversation messages cannot be empty.")
        with self._lock:
            self._conversation.messages.append(ChatMessage(role=role, content=text))
            self._conversation.updated_at = _now()
            self._save()

    def messages(self) -> list[dict[str, str]]:
        with self._lock:
            return [
                {"role": message.role, "content": message.content}
                for message in self._conversation.messages
            ]

    def new_session(self) -> None:
        """Replace the only stored conversation; no session archive is retained."""
        with self._lock:
            self._conversation = Conversation()
            self._save()

    def _save(self) -> None:
        self._store.save(self._conversation.model_dump(mode="json"))
