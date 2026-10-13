"""Bounded presentation metadata for explicit assistant clarification handoffs.

This channel never grants execution authority or resolves an approval.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.inference.completion import CompletionText


QUESTION_MARKER = "```orsi_questions"
MAX_QUESTION_BYTES = 32768
QUESTION_GUIDANCE = (
    '\nClarifications: ask readable questions, then a final orsi_questions JSON fence: '
    'version:1,questions:list of objects with id,title,kind(text|single|multi|dropdown),required,'
    'options:list of id,label,allow_other(bool). Exclude approvals/examples/exact formats.'
)
_ID = r"^[A-Za-z0-9_-]{1,40}$"


class QuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    id: str = Field(pattern=_ID)
    label: str = Field(min_length=1, max_length=300)


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    id: str = Field(pattern=_ID)
    title: str = Field(min_length=1, max_length=1000)
    kind: Literal["single", "multi", "dropdown", "text"]
    required: bool = True
    options: tuple[QuestionOption, ...] = Field(default=(), max_length=50)
    allow_other: bool = False

    @model_validator(mode="after")
    def validate_question(self):
        if not self.title.strip() or any(not option.label.strip() for option in self.options):
            raise ValueError("Questions and options require readable labels.")
        if len({option.id for option in self.options}) != len(self.options):
            raise ValueError("Option identifiers must be unique within a question.")
        if any(option.id == "__other__" for option in self.options):
            raise ValueError("This option identifier is reserved for a custom answer.")
        if self.kind == "text":
            if self.options or self.allow_other:
                raise ValueError("Text questions cannot contain choices.")
        elif not self.options:
            raise ValueError("Choice questions require options.")
        return self


class QuestionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    version: Literal[1]
    questions: tuple[Question, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_batch(self):
        if len({question.id for question in self.questions}) != len(self.questions):
            raise ValueError("Question identifiers must be unique.")
        if len(self.model_dump_json().encode("utf-8")) > MAX_QUESTION_BYTES:
            raise ValueError("Question metadata exceeds its size limit.")
        return self

    def readable(self) -> str:
        lines = []
        for number, question in enumerate(self.questions, 1):
            lines.append(f"{number}. {question.title}" + (" (optional)" if not question.required else ""))
            lines.extend(f"   - {option.label}" for option in question.options)
        return "\n".join(lines)


def _marker_position(text: str) -> int | None:
    """Recognize only an unquoted top-level control fence, never nested code."""
    fence = None
    offset = 0
    for line in text.splitlines(keepends=True):
        value = line.rstrip("\r\n")
        if fence is None and value == QUESTION_MARKER:
            return offset
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", value)
        if match:
            delimiter, tail = match.groups()
            if fence is None:
                fence = delimiter
            elif delimiter[0] == fence[0] and len(delimiter) >= len(fence) and not tail.strip():
                fence = None
        offset += len(line)
    return None


def question_preview(text: str) -> str:
    """Hide control metadata, including a partially streamed marker prefix."""
    position = _marker_position(text)
    if position is not None:
        return text[:position].rstrip()
    start = text.rfind("\n") + 1
    tail = text[start:]
    if tail and QUESTION_MARKER.startswith(tail):
        return text[:start].rstrip()
    return text


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Question metadata contains a duplicate field.")
        value[key] = item
    return value


def present_questions(answer: str, *, allow_forms=True) -> CompletionText:
    """Project a completed response; malformed metadata leaves readable chat."""
    value = CompletionText(answer)
    position = _marker_position(str(value))
    if position is None:
        return value if allow_forms and not value.completion.incomplete else CompletionText(value, question_batch=None)
    readable = str(value)[:position].rstrip()
    suffix = str(value)[position + len(QUESTION_MARKER):].strip()
    batch = None
    if allow_forms and not value.completion.incomplete and suffix.endswith("```"):
        payload = suffix[:-3].strip()
        if len(payload.encode("utf-8")) <= MAX_QUESTION_BYTES:
            try:
                json.loads(payload, object_pairs_hook=_unique_object)
                # JSON-mode validation accepts JSON arrays as immutable tuples.
                batch = QuestionBatch.model_validate_json(payload)
            except (ValueError, RecursionError):
                pass
    return CompletionText(readable or (batch.readable() if batch else
        "Please answer in chat; the question form could not be displayed."),
        value.completion, value.completion_history, status_message=value.status_message,
        openai_response=value.openai_response, generated_images=value.generated_images,
        question_batch=batch)


def format_answers(batch: QuestionBatch, answers: dict[str, tuple[str, ...]], additional: str = "") -> str:
    """Canonical readable user reply, validated against the displayed batch."""
    if set(answers) != {question.id for question in batch.questions}:
        raise ValueError("Answers must match the current questions.")
    lines = []
    for number, question in enumerate(batch.questions, 1):
        values = answers[question.id]
        if not isinstance(values, tuple) or any(not isinstance(v, str) or not v.strip() or len(v) > 8000 for v in values):
            raise ValueError("Answers must contain bounded non-empty text.")
        if question.required and not values:
            raise ValueError("Complete required questions to continue.")
        if (question.kind != "multi" and len(values) > 1) or len(values) > 51:
            raise ValueError("Too many answers for this question.")
        labels = {option.label for option in question.options}
        if question.kind != "text" and not question.allow_other and any(v not in labels for v in values):
            raise ValueError("Choose an available answer.")
        lines.append(f"{number}. {question.title}\n" + ("\n".join(values) if values else "Skipped (optional)."))
    if len(additional) > 8000:
        raise ValueError("Additional information is too long.")
    if additional.strip():
        lines.append("Additional information:\n" + additional.strip())
    return "\n\n".join(lines)
