from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any, Callable, Iterable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.capabilities.contracts import (
    Capability,
    CapabilityContext,
    CapabilityErrorCode,
    CapabilityExecutionError,
    PermissionClass,
)
from app.capabilities.path_policy import is_path_within
from app.runtime.cancellation import CancellationToken


_CAPABILITY_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_CAPABILITY_NAMESPACE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
_RULE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


class PermissionDecision(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    SHUTDOWN = "shutdown"


class AuthorizationCode(StrEnum):
    ALLOWED = "allowed"
    APPROVAL_REQUIRED = "approval_required"
    DENIED = "denied"
    APPROVAL_MISMATCH = "approval_mismatch"
    APPROVAL_EXPIRED = "approval_expired"
    APPROVAL_CONSUMED = "approval_consumed"
    CANCELLED = "cancelled"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True)
class PermissionRule:
    """One immutable rule. Later matching rules override earlier rules."""

    rule_id: str
    decision: PermissionDecision
    permission: PermissionClass | None = None
    capability_pattern: str = "*"
    resource_root: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str) or _RULE_ID.fullmatch(self.rule_id) is None:
            raise ValueError("Permission rule IDs must use lowercase stable identifier syntax.")
        if not isinstance(self.decision, PermissionDecision):
            raise TypeError("Permission rule decisions must be PermissionDecision values.")
        if self.permission is not None and not isinstance(self.permission, PermissionClass):
            raise TypeError("Permission rule classes must be PermissionClass values or None.")
        if not _valid_capability_pattern(self.capability_pattern):
            raise ValueError(
                "Capability patterns must be '*', namespace.*, or a full namespace.name."
            )
        if self.resource_root is not None:
            if not isinstance(self.resource_root, Path):
                raise TypeError("Permission resource roots must be pathlib.Path values.")
            try:
                canonical = self.resource_root.resolve(strict=False)
            except (OSError, RuntimeError, ValueError) as exc:
                raise ValueError("Permission resource roots must resolve safely.") from exc
            object.__setattr__(self, "resource_root", canonical)

    def matches(self, request: PermissionRequest) -> bool:
        if self.permission is not None and self.permission != request.permission:
            return False
        if not _capability_matches(request.capability, self.capability_pattern):
            return False
        if self.resource_root is None:
            return True
        if request.resource is None:
            return False
        return is_path_within(Path(request.resource), self.resource_root)


class PermissionRequest(BaseModel):
    """Canonical, hash-checked identity for one validated capability call."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    call_id: str = Field(min_length=1, max_length=128)
    capability: str = Field(min_length=3, max_length=128)
    permission: PermissionClass
    arguments_json: str = Field(min_length=2, max_length=2_000_000)
    arguments_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resource: str | None = Field(default=None, max_length=32_767)
    resource_identity: str | None = Field(default=None, max_length=256)
    approval_preview: str | None = Field(default=None, max_length=65_536)
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def build(
        cls,
        *,
        call_id: str,
        capability: str,
        permission: PermissionClass,
        arguments_json: str,
        resource: str | None,
        resource_identity: str | None = None,
        approval_preview: str | None = None,
    ) -> PermissionRequest:
        arguments_sha256 = _sha256(arguments_json)
        request_sha256 = _digest_json(
            {
                "approval_preview": approval_preview,
                "arguments_sha256": arguments_sha256,
                "call_id": call_id,
                "capability": capability,
                "permission": permission.value,
                "resource": resource,
                "resource_identity": resource_identity,
            }
        )
        return cls(
            call_id=call_id,
            capability=capability,
            permission=permission,
            arguments_json=arguments_json,
            arguments_sha256=arguments_sha256,
            resource=resource,
            resource_identity=resource_identity,
            approval_preview=approval_preview,
            request_sha256=request_sha256,
        )

    @model_validator(mode="after")
    def verify_digests(self):
        if _sha256(self.arguments_json) != self.arguments_sha256:
            raise ValueError("The argument digest does not match the canonical arguments.")
        expected = _digest_json(
            {
                "approval_preview": self.approval_preview,
                "arguments_sha256": self.arguments_sha256,
                "call_id": self.call_id,
                "capability": self.capability,
                "permission": self.permission.value,
                "resource": self.resource,
                "resource_identity": self.resource_identity,
            }
        )
        if expected != self.request_sha256:
            raise ValueError("The request digest does not match the capability call.")
        return self


@dataclass(frozen=True, slots=True)
class PreparedCapabilityCall:
    """Validated serialized arguments plus permission identity; no execution occurs."""

    capability: Capability
    request: PermissionRequest
    context: CapabilityContext

    def __post_init__(self) -> None:
        if not isinstance(self.capability, Capability):
            raise TypeError("Prepared calls require a Capability implementation.")
        if not isinstance(self.request, PermissionRequest):
            raise TypeError("Prepared calls require a canonical PermissionRequest.")
        if not isinstance(self.context, CapabilityContext):
            raise TypeError("Prepared calls require their original CapabilityContext.")
        if self.capability.name != self.request.capability:
            raise ValueError("The prepared capability does not match the request identity.")
        if self.capability.permission != self.request.permission:
            raise ValueError("The prepared permission class does not match the request identity.")
        if self.context.call_id != self.request.call_id:
            raise ValueError("The prepared context does not match the request call ID.")

    def validated_arguments(self) -> BaseModel:
        return self.capability.arguments_model.model_validate_json(
            self.request.arguments_json
        )


class PermissionEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    request: PermissionRequest
    decision: PermissionDecision
    matched_rule_id: str | None = Field(default=None, max_length=128)
    binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def build(
        cls,
        *,
        request: PermissionRequest,
        decision: PermissionDecision,
        matched_rule_id: str | None,
    ) -> PermissionEvaluation:
        binding_sha256 = _approval_binding(request, decision, matched_rule_id)
        return cls(
            request=request,
            decision=decision,
            matched_rule_id=matched_rule_id,
            binding_sha256=binding_sha256,
        )

    @model_validator(mode="after")
    def verify_binding(self):
        expected = _approval_binding(
            self.request,
            self.decision,
            self.matched_rule_id,
        )
        if expected != self.binding_sha256:
            raise ValueError("The permission binding does not match the evaluation.")
        return self


class PermissionAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    allowed: bool
    code: AuthorizationCode
    decision: PermissionDecision
    matched_rule_id: str | None = None
    approval_id: str | None = None
    approval_status: ApprovalStatus | None = None
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_authorization(self):
        expected_binding = _digest_json(
            {
                "decision": self.decision.value,
                "matched_rule_id": self.matched_rule_id,
                "request_sha256": self.request_sha256,
            }
        )
        if expected_binding != self.binding_sha256:
            raise ValueError("The authorization binding does not match its permission decision.")
        if self.allowed != (self.code == AuthorizationCode.ALLOWED):
            raise ValueError("Only an allowed authorization may use the allowed code.")
        if self.allowed and self.decision == PermissionDecision.DENY:
            raise ValueError("A DENY decision cannot authorize execution.")
        if self.allowed and self.matched_rule_id is None:
            raise ValueError("Authorized execution must be bound to an explicit rule.")
        if self.decision == PermissionDecision.ALLOW and (
            self.approval_id is not None or self.approval_status is not None
        ):
            raise ValueError("An ALLOW rule does not use an approval record.")
        if self.allowed and self.decision == PermissionDecision.ASK:
            if self.approval_id is None or self.approval_status != ApprovalStatus.CONSUMED:
                raise ValueError("An approved ASK decision must consume an exact approval.")
        return self


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    approval_id: str = Field(min_length=1, max_length=128)
    binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    call_id: str = Field(min_length=1, max_length=128)
    capability: str = Field(min_length=3, max_length=128)
    arguments_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    matched_rule_id: str = Field(min_length=1, max_length=128)
    status: ApprovalStatus
    expires_at: float = Field(ge=0)
    resource: str | None = Field(default=None, max_length=32_767)
    approval_preview: str | None = Field(default=None, max_length=65_536)


class ApprovalNotFoundError(LookupError):
    pass


class PermissionGate:
    """Immutable ordered rules with a fail-closed default decision."""

    def __init__(self, rules: Iterable[PermissionRule] = ()):
        validated: list[PermissionRule] = []
        seen: set[str] = set()
        for rule in rules:
            if not isinstance(rule, PermissionRule):
                raise TypeError("Permission gates accept only PermissionRule objects.")
            if rule.rule_id in seen:
                raise ValueError(f"Permission rule ID is duplicated: {rule.rule_id}")
            seen.add(rule.rule_id)
            validated.append(rule)
        self._rules = tuple(validated)

    @property
    def rules(self) -> tuple[PermissionRule, ...]:
        return self._rules

    def evaluate(self, prepared: PreparedCapabilityCall) -> PermissionEvaluation:
        if not isinstance(prepared, PreparedCapabilityCall):
            raise TypeError("Permission evaluation requires a prepared capability call.")
        matched: PermissionRule | None = None
        for rule in self._rules:
            if rule.matches(prepared.request):
                matched = rule

        decision = matched.decision if matched is not None else PermissionDecision.DENY
        return PermissionEvaluation.build(
            request=prepared.request,
            decision=decision,
            matched_rule_id=matched.rule_id if matched is not None else None,
        )


class ApprovalManager:
    """Thread-safe, in-memory lifecycle for call-specific ASK approvals."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = monotonic,
        id_factory: Callable[[], str] = lambda: uuid4().hex,
    ):
        self._clock = clock
        self._id_factory = id_factory
        self._records: dict[str, ApprovalRecord] = {}
        self._shutdown = False
        self._lock = Lock()

    @property
    def records(self) -> tuple[ApprovalRecord, ...]:
        with self._lock:
            return tuple(self._records[key] for key in sorted(self._records))

    def request(
        self,
        evaluation: PermissionEvaluation,
        *,
        ttl_seconds: float = 60.0,
        cancellation: CancellationToken | None = None,
        now: float | None = None,
    ) -> ApprovalRecord:
        if evaluation.decision != PermissionDecision.ASK:
            raise ValueError("Only ASK evaluations can create approval requests.")
        if evaluation.matched_rule_id is None:
            raise ValueError("ASK evaluations must be bound to an explicit rule.")
        ttl = _positive_duration(ttl_seconds)
        timestamp = self._timestamp(now)

        with self._lock:
            approval_id = self._new_id_locked()
            status = ApprovalStatus.PENDING
            if self._shutdown:
                status = ApprovalStatus.SHUTDOWN
            elif cancellation is not None and cancellation.is_cancelled:
                status = ApprovalStatus.CANCELLED
            record = ApprovalRecord(
                approval_id=approval_id,
                binding_sha256=evaluation.binding_sha256,
                call_id=evaluation.request.call_id,
                capability=evaluation.request.capability,
                arguments_sha256=evaluation.request.arguments_sha256,
                matched_rule_id=evaluation.matched_rule_id,
                status=status,
                expires_at=timestamp + ttl,
                resource=evaluation.request.resource,
                approval_preview=evaluation.request.approval_preview,
            )
            self._records[approval_id] = record
            return record

    def resolve(
        self,
        approval_id: str,
        status: ApprovalStatus,
        *,
        now: float | None = None,
    ) -> ApprovalRecord:
        if status not in {
            ApprovalStatus.APPROVED,
            ApprovalStatus.DENIED,
            ApprovalStatus.CANCELLED,
        }:
            raise ValueError("Approvals may resolve only as approved, denied, or cancelled.")
        timestamp = self._timestamp(now)
        with self._lock:
            record = self._record_locked(approval_id, timestamp)
            if record.status != ApprovalStatus.PENDING:
                return record
            if self._shutdown:
                status = ApprovalStatus.SHUTDOWN
            updated = record.model_copy(update={"status": status})
            self._records[approval_id] = updated
            return updated

    def get(self, approval_id: str) -> ApprovalRecord:
        with self._lock:
            return self._record_locked(approval_id, self._timestamp(None))

    def authorize(
        self,
        evaluation: PermissionEvaluation,
        *,
        approval_id: str | None = None,
        cancellation: CancellationToken | None = None,
        now: float | None = None,
    ) -> PermissionAuthorization:
        if evaluation.decision == PermissionDecision.ALLOW:
            return self._authorization(evaluation, True, AuthorizationCode.ALLOWED)
        if evaluation.decision == PermissionDecision.DENY:
            return self._authorization(evaluation, False, AuthorizationCode.DENIED)

        timestamp = self._timestamp(now)
        with self._lock:
            if cancellation is not None and cancellation.is_cancelled:
                record = None
                if approval_id is not None and approval_id in self._records:
                    record = self._record_locked(approval_id, timestamp)
                    if record.status in {
                        ApprovalStatus.PENDING,
                        ApprovalStatus.APPROVED,
                    }:
                        record = record.model_copy(
                            update={"status": ApprovalStatus.CANCELLED}
                        )
                        self._records[approval_id] = record
                return self._authorization(
                    evaluation,
                    False,
                    AuthorizationCode.CANCELLED,
                    record,
                )
            if approval_id is None:
                code = (
                    AuthorizationCode.SHUTDOWN
                    if self._shutdown
                    else AuthorizationCode.APPROVAL_REQUIRED
                )
                return self._authorization(evaluation, False, code)

            record = self._record_locked(approval_id, timestamp)
            if record.binding_sha256 != evaluation.binding_sha256:
                return self._authorization(
                    evaluation,
                    False,
                    AuthorizationCode.APPROVAL_MISMATCH,
                    record,
                )

            code_by_status = {
                ApprovalStatus.PENDING: AuthorizationCode.APPROVAL_REQUIRED,
                ApprovalStatus.APPROVED: AuthorizationCode.ALLOWED,
                ApprovalStatus.DENIED: AuthorizationCode.DENIED,
                ApprovalStatus.CANCELLED: AuthorizationCode.CANCELLED,
                ApprovalStatus.EXPIRED: AuthorizationCode.APPROVAL_EXPIRED,
                ApprovalStatus.CONSUMED: AuthorizationCode.APPROVAL_CONSUMED,
                ApprovalStatus.SHUTDOWN: AuthorizationCode.SHUTDOWN,
            }
            code = code_by_status[record.status]
            allowed = record.status == ApprovalStatus.APPROVED
            if allowed:
                record = record.model_copy(
                    update={"status": ApprovalStatus.CONSUMED}
                )
                self._records[approval_id] = record
            return self._authorization(
                evaluation,
                allowed,
                code,
                record,
            )

    def shutdown(self, *, now: float | None = None) -> tuple[ApprovalRecord, ...]:
        timestamp = self._timestamp(now)
        with self._lock:
            self._shutdown = True
            for approval_id in tuple(self._records):
                record = self._record_locked(approval_id, timestamp)
                if record.status in {
                    ApprovalStatus.PENDING,
                    ApprovalStatus.APPROVED,
                }:
                    self._records[approval_id] = record.model_copy(
                        update={"status": ApprovalStatus.SHUTDOWN}
                    )
            return tuple(self._records[key] for key in sorted(self._records))

    def _record_locked(self, approval_id: str, timestamp: float) -> ApprovalRecord:
        record = self._records.get(str(approval_id))
        if record is None:
            raise ApprovalNotFoundError("The approval request does not exist.")
        if record.status in {
            ApprovalStatus.PENDING,
            ApprovalStatus.APPROVED,
        } and timestamp >= record.expires_at:
            record = record.model_copy(update={"status": ApprovalStatus.EXPIRED})
            self._records[record.approval_id] = record
        return record

    def _new_id_locked(self) -> str:
        for _ in range(8):
            candidate = str(self._id_factory())
            if candidate and len(candidate) <= 128 and candidate not in self._records:
                return candidate
        raise RuntimeError("A unique approval ID could not be generated.")

    def _timestamp(self, value: float | None) -> float:
        timestamp = self._clock() if value is None else value
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            raise TypeError("Approval timestamps must be finite numbers.")
        timestamp = float(timestamp)
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("Approval timestamps must be finite non-negative numbers.")
        return timestamp

    @staticmethod
    def _authorization(
        evaluation: PermissionEvaluation,
        allowed: bool,
        code: AuthorizationCode,
        record: ApprovalRecord | None = None,
    ) -> PermissionAuthorization:
        return PermissionAuthorization(
            allowed=allowed,
            code=code,
            decision=evaluation.decision,
            matched_rule_id=evaluation.matched_rule_id,
            approval_id=record.approval_id if record is not None else None,
            approval_status=record.status if record is not None else None,
            request_sha256=evaluation.request.request_sha256,
            binding_sha256=evaluation.binding_sha256,
        )


def prepare_capability_call(
    capability: Capability,
    raw_arguments: Any,
    context: CapabilityContext,
) -> PreparedCapabilityCall:
    """Validate and canonicalize a call without invoking its execute method."""
    if not isinstance(capability, Capability):
        raise TypeError("Prepared calls require a Capability implementation.")
    arguments = capability.validate_arguments(raw_arguments)
    arguments_json = json.dumps(
        arguments.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    resource = capability.permission_resource(arguments, context)
    approval_preview = capability.approval_preview(arguments, context)
    if approval_preview is not None and not isinstance(approval_preview, str):
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The approval preview was not valid text.",
        )
    request = PermissionRequest.build(
        call_id=context.call_id,
        capability=capability.name,
        permission=capability.permission,
        arguments_json=arguments_json,
        resource=str(resource) if resource is not None else None,
        resource_identity=capability.permission_resource_identity(arguments, context),
        approval_preview=approval_preview,
    )
    return PreparedCapabilityCall(
        capability=capability,
        request=request,
        context=context,
    )


def _valid_capability_pattern(pattern: object) -> bool:
    if not isinstance(pattern, str) or len(pattern) > 128:
        return False
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return _CAPABILITY_NAMESPACE.fullmatch(pattern[:-2]) is not None
    return _CAPABILITY_NAME.fullmatch(pattern) is not None


def _capability_matches(capability: str, pattern: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return capability.startswith(pattern[:-1])
    return capability == pattern


def _approval_binding(
    request: PermissionRequest,
    decision: PermissionDecision,
    matched_rule_id: str | None,
) -> str:
    return _digest_json(
        {
            "decision": decision.value,
            "matched_rule_id": matched_rule_id,
            "request_sha256": request.request_sha256,
        }
    )


def _digest_json(value: dict[str, Any]) -> str:
    return _sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _positive_duration(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Approval lifetimes must be finite numbers.")
    duration = float(value)
    if not math.isfinite(duration) or duration <= 0 or duration > 3_600:
        raise ValueError("Approval lifetimes must be between 0 and 3600 seconds.")
    return duration
