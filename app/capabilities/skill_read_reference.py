"""Opt-in scoped adapter. Conversation/catalog wiring belongs to Phase 4."""
from pydantic import BaseModel, ConfigDict, Field

from app.capabilities.contracts import (Capability, CapabilityExecutionError, CapabilityErrorCode,
                                        PermissionClass, ExecutionIsolation)
from app.runtime.skills.reference_reader import (
    DEFAULT_EXCERPT_BYTES, MAX_EXCERPT_BYTES, DEFAULT_EXCERPT_LINES, MAX_EXCERPT_LINES,
    ReferenceErrorCode, ReferenceReadError, SkillReferenceReader, ReferenceBinding,
)
from app.runtime.cancellation import TaskCancelled


class SkillReadReferenceArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=240, description="Copy the canonical references/...md inventory identifier exactly.")
    version: str = Field(pattern=r"^[0-9a-f]{64}$", description="Copy the active package inventory version exactly.")
    offset: int = Field(default=0, ge=0, le=16 * 1024, description="Start at zero; for continuation copy next_offset from the previous result.")
    max_bytes: int = Field(default=DEFAULT_EXCERPT_BYTES, ge=4, le=MAX_EXCERPT_BYTES)
    max_lines: int = Field(default=DEFAULT_EXCERPT_LINES, ge=1, le=MAX_EXCERPT_LINES)


class SkillReadReferenceCapability(Capability[SkillReadReferenceArguments]):
    name = "skill.read_reference"
    description = "Read one bounded Markdown excerpt from the active skill inventory; no host search or link expansion."
    arguments_model = SkillReadReferenceArguments
    permission = PermissionClass.READ
    timeout_seconds = 3.0
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE

    def __init__(self, reader: SkillReferenceReader, binding: ReferenceBinding, *, session_id: str, turn_id: str):
        self._reader, self._binding = reader, binding
        self._session_id, self._turn_id = session_id, turn_id

    def execute(self, arguments, context) -> dict:
        if (context.session_id, context.turn_id) != (self._session_id, self._turn_id):
            raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                                           "Skill reference authority does not belong to this conversation turn.")
        try:
            return self._reader.read(self._binding, arguments.path, version=arguments.version,
                                     offset=arguments.offset, max_bytes=arguments.max_bytes,
                                     max_lines=arguments.max_lines, cancellation=context.cancellation)
        except ReferenceReadError as error:
            code = {ReferenceErrorCode.DISABLED: CapabilityErrorCode.DISABLED_CAPABILITY,
                    ReferenceErrorCode.STALE: CapabilityErrorCode.PERMISSION_DENIED,
                    ReferenceErrorCode.UNSAFE: CapabilityErrorCode.PERMISSION_DENIED,
                    ReferenceErrorCode.MISSING: CapabilityErrorCode.NOT_FOUND,
                    ReferenceErrorCode.INVALID_REQUEST: CapabilityErrorCode.INVALID_ARGUMENTS,
                    ReferenceErrorCode.LIMIT_EXCEEDED: CapabilityErrorCode.OUTPUT_LIMITED,
                    ReferenceErrorCode.INVALID_PACKAGE: CapabilityErrorCode.INVALID_OUTPUT,
                    ReferenceErrorCode.INACCESSIBLE: CapabilityErrorCode.INACCESSIBLE}[error.code]
            raise CapabilityExecutionError(code, str(error)) from None
        except TaskCancelled:
            raise
        except Exception:
            # A future storage adapter must not leak host paths, vault details or
            # reference contents through the generic capability traceback logger.
            raise CapabilityExecutionError(CapabilityErrorCode.INTERNAL_ERROR,
                                           "Skill reference reading failed unexpectedly.") from None
