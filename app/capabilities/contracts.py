from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.runtime.cancellation import CancellationToken, TaskCancelled


log = logging.getLogger(__name__)


class PermissionClass(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    SYSTEM = "system"


class CapabilityErrorCode(StrEnum):
    INVALID_ARGUMENTS = "invalid_arguments"
    UNKNOWN_CAPABILITY = "unknown_capability"
    DISABLED_CAPABILITY = "disabled_capability"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    INACCESSIBLE = "inaccessible"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    INTERNAL_ERROR = "internal_error"


class CapabilityFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: CapabilityErrorCode
    message: str = Field(min_length=1, max_length=500)
    details: list[dict[str, Any]] = Field(default_factory=list, max_length=32)


class CapabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    call_id: str = Field(min_length=1, max_length=128)
    capability: str = Field(min_length=1, max_length=128)
    success: bool
    output: dict[str, Any] | None = None
    error: CapabilityFailure | None = None
    duration_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_outcome(self):
        if self.success and self.error is not None:
            raise ValueError("A successful result cannot contain an error.")
        if not self.success and self.error is None:
            raise ValueError("A failed result must contain an error.")
        return self


@dataclass(frozen=True)
class CapabilityContext:
    call_id: str
    session_id: str
    turn_id: str
    portable_root: Path
    allowed_read_roots: tuple[Path, ...]
    cancellation: CancellationToken


class CapabilityExecutionError(RuntimeError):
    def __init__(self, code: CapabilityErrorCode, message: str):
        super().__init__(message)
        self.code = code


class CapabilityArgumentError(ValueError):
    """Structured validation failure raised before any capability can execute."""

    def __init__(self, failure: CapabilityFailure):
        super().__init__(failure.message)
        self.failure = failure


ArgumentsT = TypeVar("ArgumentsT", bound=BaseModel)


class Capability(ABC, Generic[ArgumentsT]):
    name: ClassVar[str]
    description: ClassVar[str]
    arguments_model: ClassVar[type[BaseModel]]
    permission: ClassVar[PermissionClass]
    timeout_seconds: ClassVar[float]

    def validate_arguments(self, raw_arguments: Any) -> ArgumentsT:
        """Validate untrusted arguments without executing capability code."""
        try:
            return self.arguments_model.model_validate(raw_arguments)
        except ValidationError as exc:
            details = [
                {
                    "location": [str(item) for item in error["loc"]],
                    "type": error["type"],
                    "message": error["msg"],
                }
                for error in exc.errors(include_url=False, include_input=False)[:32]
            ]
            raise CapabilityArgumentError(
                CapabilityFailure(
                    code=CapabilityErrorCode.INVALID_ARGUMENTS,
                    message="The capability arguments did not match the required schema.",
                    details=details,
                )
            ) from exc

    def permission_resource(
        self,
        arguments: ArgumentsT,
        context: CapabilityContext,
    ) -> Path | None:
        """Return the canonical resource used for permission matching, if any."""
        del arguments, context
        return None

    def invoke(self, raw_arguments: Any, context: CapabilityContext) -> CapabilityResult:
        started = perf_counter()
        try:
            arguments = self.validate_arguments(raw_arguments)
        except CapabilityArgumentError as exc:
            return self._failure(
                context,
                started,
                exc.failure.code,
                exc.failure.message,
                details=exc.failure.details,
            )

        try:
            context.cancellation.raise_if_cancelled()
            output = self.execute(arguments, context)
            context.cancellation.raise_if_cancelled()
            return CapabilityResult(
                call_id=context.call_id,
                capability=self.name,
                success=True,
                output=output,
                duration_ms=self._duration_ms(started),
                metadata={
                    "permission": self.permission.value,
                    "result_schema_version": 1,
                },
            )
        except TaskCancelled:
            return self._failure(
                context,
                started,
                CapabilityErrorCode.CANCELLED,
                "The capability call was cancelled.",
            )
        except CapabilityExecutionError as exc:
            return self._failure(context, started, exc.code, str(exc))
        except Exception:
            log.exception("Unhandled capability failure: %s", self.name)
            return self._failure(
                context,
                started,
                CapabilityErrorCode.INTERNAL_ERROR,
                "The capability failed unexpectedly.",
            )

    @abstractmethod
    def execute(self, arguments: ArgumentsT, context: CapabilityContext) -> dict[str, Any]:
        raise NotImplementedError

    def _failure(
        self,
        context: CapabilityContext,
        started: float,
        code: CapabilityErrorCode,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> CapabilityResult:
        return CapabilityResult(
            call_id=context.call_id,
            capability=self.name,
            success=False,
            error=CapabilityFailure(code=code, message=message, details=details or []),
            duration_ms=self._duration_ms(started),
            metadata={
                "permission": self.permission.value,
                "result_schema_version": 1,
            },
        )

    @staticmethod
    def _duration_ms(started: float) -> int:
        return max(0, int((perf_counter() - started) * 1000))
