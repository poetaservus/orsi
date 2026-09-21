from __future__ import annotations

from pathlib import Path
import re


def grounded_text_read_answer(
    user_text: str,
    assistant_text: str,
    observed_results: list[tuple],
) -> str | None:
    """Return exact read output when a direct-read answer is missing or misleading."""
    call_and_result = _latest_successful_text_read(observed_results)
    if call_and_result is None:
        return None
    call, result = call_and_result
    output = result.output or {}
    file_text = output.get("text")
    if not isinstance(file_text, str):
        return None
    if not _should_ground_text_read_answer(user_text, assistant_text, file_text):
        return None
    return _render_text_result(call, result)


def _latest_successful_text_read(observed_results: list[tuple]) -> tuple | None:
    for call, result in reversed(observed_results):
        if call.capability != "filesystem.read_text" or not result.success:
            continue
        output = result.output or {}
        if isinstance(output.get("text"), str):
            return call, result
    return None


def _should_ground_text_read_answer(
    user_text: str,
    assistant_text: str,
    file_text: str,
) -> bool:
    lowered_answer = " ".join(str(assistant_text).casefold().split())
    if re.search(
        r"\b(?:cannot|can't|can\s+not)\s+show\s+the\s+full\s+content\b",
        lowered_answer,
    ):
        return True
    if re.search(r"\bcapability restrictions?\b", lowered_answer):
        return True
    if file_text and file_text in assistant_text:
        return False
    return _is_direct_content_read_request(user_text)


def _is_direct_content_read_request(text: str) -> bool:
    lowered = " ".join(str(text).casefold().split())
    if re.search(
        r"\b(?:summari[sz]e|summary|analy[sz]e|explain|review|classify|compare|extract|parse)\b",
        lowered,
    ):
        return False
    if re.match(
        r"(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
        r"(?:read|show|display|print|paste|open)\b",
        lowered,
    ):
        return True
    if re.search(
        r"\b(?:read|show|display|print|paste)\b.{0,120}"
        r"\b(?:contents?|content|file|it|this|that)\b",
        lowered,
    ):
        return True
    return re.search(
        r"\bwhat\s+does\s+(?:it|this|that|the\s+file)\s+say\b",
        lowered,
    ) is not None


def _render_text_result(call, result) -> str:
    output = result.output or {}
    text = output.get("text")
    if not isinstance(text, str):
        return "The text-file read returned an invalid result."
    name = _safe_filename(Path(str(call.arguments.get("path", "file"))).name)
    if not text:
        answer = f"{name} is empty."
    else:
        fence = _markdown_code_fence(text)
        closing_prefix = "" if text.endswith(("\n", "\r")) else "\n"
        answer = (
            f"Here is the content of {name}:\n\n"
            f"{fence}text\n{text}{closing_prefix}{fence}"
        )
    if output.get("truncated_by_bytes") is True or output.get("truncated_by_lines") is True:
        answer += "\n\nThe displayed content was truncated by the configured read limit."
    return answer


def _markdown_code_fence(text: str) -> str:
    longest_run = max(
        (len(match.group(0)) for match in re.finditer(r"`+", text)),
        default=0,
    )
    return "`" * max(3, longest_run + 1)


def _safe_filename(value: str) -> str:
    return _safe_text(value).replace("\\", "\\\\").replace("`", "\\`").replace("*", "\\*")


def _safe_text(value: str) -> str:
    return "".join(character if character >= " " else "�" for character in str(value))
