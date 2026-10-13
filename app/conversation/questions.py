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


def question_preview(text: str) -> str:
    """Buffer potential control JSON; never stream a questionnaire's payload."""
    for start, end, language, payload, complete in _fences(text):
        if language == "orsi_questions" or language in {"json", ""} and (
                not complete or _parse_batch(payload) is not None):
            text = text[:start].rstrip()
            break
    start = text.rfind("\n") + 1
    tail = text[start:]
    closing = any(complete and first <= start < end for first, end, _, _, complete in _fences(text))
    if tail and not closing and any(marker.startswith(tail) for marker in (QUESTION_MARKER, "```json")):
        text = text[:start].rstrip()
    # A question list is held until the final handoff establishes its metadata.
    # Ordinary lists are still rendered in full if the settled reply has no form.
    protected = [(start, end) for start, end, *_ in _fences(text)]
    for match in re.finditer(r"(?m)^\s*\d+[.)]\s+", text):
        if not any(start <= match.start() < end for start, end in protected):
            return text[:match.start()].rstrip()
    words = ("what", "which", "who", "whose", "how", "where", "when", "why",
             "can", "could", "would", "do", "does", "should", "will")
    for match in re.finditer(r"(?im)(?:^|(?<=[.!])\s+)([A-Za-z]+)(?:\s|$)", text):
        start = match.start(1)
        if any(first <= start < end for first, end in protected):
            continue
        line_start = text.rfind("\n", 0, start) + 1
        if text[line_start:start].lstrip().startswith(">"):
            continue
        word = match.group(1).lower()
        if word in words or match.end() == len(text) and any(candidate.startswith(word) for candidate in words):
            return text[:start].rstrip()
    return text


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Question metadata contains a duplicate field.")
        value[key] = item
    return value


def _fences(text):
    """Top-level Markdown fences with byte-independent character offsets."""
    opened = None
    offset = 0
    for line in text.splitlines(keepends=True):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*?)[\r\n]*$", line)
        if match:
            delimiter, label = match.groups()
            if opened is None:
                opened = (offset, offset + len(line), delimiter, label.strip().lower())
            elif delimiter[0] == opened[2][0] and len(delimiter) >= len(opened[2]) and not label.strip():
                yield opened[0], offset + len(line), opened[3], text[opened[1]:offset].strip(), True
                opened = None
        offset += len(line)
    if opened is not None:
        yield opened[0], len(text), opened[3], text[opened[1]:].strip(), False


def _parse_batch(payload):
    try:
        if len(payload.encode("utf-8")) <= MAX_QUESTION_BYTES:
            json.loads(payload, object_pairs_hook=_unique_object)
            return QuestionBatch.model_validate_json(payload)
    except (ValueError, RecursionError, UnicodeError):
        pass
    return None


def _looks_like_batch(payload):
    try:
        value = json.loads(payload, object_pairs_hook=_unique_object)
        return isinstance(value, dict) and "version" in value and isinstance(value.get("questions"), list)
    except (ValueError, RecursionError):
        return False


def _question_prose(text):
    for start, end, *_ in reversed(list(_fences(text))):
        text = text[:start] + text[end:]
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))
    text = re.sub(r"`+[^`]*`+", "", text)
    return any(mark in text for mark in ("?", "？", "؟"))


def present_questions(answer: str, *, allow_forms=True) -> CompletionText:
    """Project a completed response; malformed metadata leaves readable chat."""
    value = CompletionText(answer)
    batch = value.question_batch if allow_forms and not value.completion.incomplete else None
    readable = str(value)
    removed = False
    for start, end, language, payload, complete in reversed(list(_fences(str(value)))):
        parsed = _parse_batch(payload) if complete else None
        dedicated = language == "orsi_questions"
        generic = language in {"json", ""} and (
            parsed is not None and _question_prose(str(value)[:start])
            or batch is not None and _looks_like_batch(payload))
        if dedicated or generic:
            readable = readable[:start] + readable[end:]
            removed = True
            if allow_forms and not value.completion.incomplete and complete and not str(value)[end:].strip():
                batch = parsed or batch
    if not removed:
        return CompletionText(value, question_batch=batch)
    readable = readable.strip()
    return CompletionText(readable or (batch.readable() if batch else
        "Please answer in chat; the question form could not be displayed."),
        value.completion, value.completion_history, status_message=value.status_message,
        openai_response=value.openai_response, generated_images=value.generated_images,
        question_batch=batch)


def question_chat_text(answer: str, batch: QuestionBatch | None = None) -> CompletionText:
    """Only the introduction belongs in chat; full questions stay in history."""
    batch = batch or getattr(answer, "question_batch", None)
    if batch is None:
        return CompletionText(answer)
    value = present_questions(CompletionText(answer, question_batch=batch))
    text = str(value)
    starts = []
    for question in batch.questions:
        # The metadata title may omit choices following a dash in the prose.
        title = question.title.rstrip(" ?？؟:")
        pattern = r"\s+".join(re.escape(word) for word in title.split())
        match = re.search(pattern, text, flags=re.IGNORECASE) if pattern else None
        if match:
            start = match.start()
            line_start = text.rfind("\n", 0, start) + 1
            if re.fullmatch(r"\s*(?:\d+[.)]|[-*])?\s*", text[line_start:start]):
                start = line_start
            starts.append(start)
    for match in re.finditer(r"(?m)^\s*\d+[.)]\s+", text):
        end = text.find("\n\n", match.end())
        if _question_prose(text[match.start():end if end >= 0 else len(text)]):
            starts.append(match.start())
    remark = text[:min(starts)].rstrip() if starts else text
    return CompletionText(remark, value.completion, value.completion_history,
        status_message=value.status_message, openai_response=value.openai_response,
        generated_images=value.generated_images, question_batch=batch)


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
