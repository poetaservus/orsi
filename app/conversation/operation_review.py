"""Content-free snapshots for human review; never a model-callable tool."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InterruptedOperation:
    call_id: str
    session_id: str
    turn_id: str
    capability: str
    permission: str
    updated_at_ms: int


@dataclass(frozen=True, slots=True)
class OperationReview:
    operations: tuple[InterruptedOperation, ...] = ()
    restart_required: bool = False

    @property
    def required(self) -> bool:
        return self.restart_required or bool(self.operations)
