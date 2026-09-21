from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


_CAPABILITY_NAME = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
)
_MAX_SCHEMA_BYTES = 256 * 1024


class ModelCapabilityDefinition(BaseModel):
    """Provider-neutral strict function definition exported by the registry."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(min_length=3, max_length=128)
    description: str = Field(min_length=1, max_length=2_000)
    input_schema: dict[str, Any]

    @model_validator(mode="after")
    def validate_definition(self):
        if _CAPABILITY_NAME.fullmatch(self.name) is None:
            raise ValueError("Model capability names must use namespace.name syntax.")
        if not self.description.strip():
            raise ValueError("Model capability descriptions cannot be blank.")
        if (
            self.input_schema.get("type") != "object"
            or self.input_schema.get("additionalProperties") is not False
        ):
            raise ValueError(
                "Model capability schemas must be strict objects that forbid unknown fields."
            )
        if _json_size(self.input_schema) > _MAX_SCHEMA_BYTES:
            raise ValueError("The model capability schema exceeds its safe size limit.")
        return self


def _json_size(value: Any) -> int:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Model capability schemas must contain bounded JSON data.") from exc
    return len(encoded)
