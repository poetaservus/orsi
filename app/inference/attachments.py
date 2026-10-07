"""Provider-neutral references to user inputs; never tool or skill instructions."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AttachmentError(ValueError):
    """An attachment cannot be stored or admitted without losing its meaning."""


class AttachmentReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True,
                              revalidate_instances="always")

    id: str = Field(pattern=r"^att-[0-9a-f]{32}$")
    name: str = Field(min_length=1, max_length=255)
    kind: Literal["image", "file"]
    media_type: str = Field(pattern=r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$", max_length=127)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_name(self):
        if self.name in {".", ".."} or any(c in self.name for c in '/\\:') or any(
                ord(c) < 32 or ord(c) == 127 for c in self.name):
            raise ValueError("Attachment names must be plain display filenames.")
        return self


def attachment_references(values) -> tuple[AttachmentReference, ...]:
    """Freeze one ordered selection. Metadata is never an arbitrary path."""
    if not isinstance(values, (tuple, list)):
        raise TypeError("Attachments require an ordered list or tuple.")
    references = tuple(AttachmentReference.model_validate(value) for value in values)
    if len({value.id for value in references}) != len(references):
        raise AttachmentError("The same attachment was selected more than once.")
    return references


def has_attachments(messages) -> bool:
    return any(bool(message.get("attachments")) for message in messages)
