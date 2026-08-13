from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from app.capabilities import (
    ApprovalManager,
    ApprovalNotFoundError,
    ApprovalStatus,
    AuthorizationCode,
    Capability,
    CapabilityArgumentError,
    CapabilityContext,
    FilesystemStatCapability,
    PermissionClass,
    PermissionDecision,
    PermissionGate,
    PermissionRule,
    prepare_capability_call,
)
from app.runtime.cancellation import CancellationSource


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: str


class InertCapability(Capability[EchoArguments]):
    name = "test.inert"
    description = "A capability that records whether test code executed it."
    arguments_model = EchoArguments
    permission = PermissionClass.READ
    timeout_seconds = 1.0

    def __init__(self):
        self.execution_count = 0

    def execute(self, arguments, context):
        self.execution_count += 1
        return {"value": arguments.value}


def context(
    root: Path,
    *,
    call_id: str = "call-1",
    cancellation=None,
) -> CapabilityContext:
    return CapabilityContext(
        call_id=call_id,
        session_id="session-1",
        turn_id="turn-1",
        portable_root=root,
        allowed_read_roots=(root,),
        cancellation=cancellation or CancellationSource().token,
    )


def prepared_inert(tmp_path: Path, value: str = "hello", *, call_id: str = "call-1"):
    capability = InertCapability()
    prepared = prepare_capability_call(
        capability,
        {"value": value},
        context(tmp_path, call_id=call_id),
    )
    return capability, prepared


def ask_evaluation(tmp_path: Path, value: str = "hello", *, call_id: str = "call-1"):
    _, prepared = prepared_inert(tmp_path, value, call_id=call_id)
    gate = PermissionGate(
        [
            PermissionRule(
                "ask-test-read",
                PermissionDecision.ASK,
                permission=PermissionClass.READ,
                capability_pattern="test.*",
            )
        ]
    )
    return gate.evaluate(prepared)


def test_preparation_validates_and_serializes_without_executing(tmp_path: Path):
    capability, prepared = prepared_inert(tmp_path)

    assert capability.execution_count == 0
    assert prepared.request.arguments_json == '{"value":"hello"}'
    assert prepared.validated_arguments() == EchoArguments(value="hello")


def test_preparation_rejects_invalid_arguments_without_executing(tmp_path: Path):
    capability = InertCapability()

    with pytest.raises(CapabilityArgumentError) as caught:
        prepare_capability_call(capability, {"wrong": True}, context(tmp_path))

    assert capability.execution_count == 0
    assert caught.value.failure.code.value == "invalid_arguments"


def test_gate_defaults_to_deny_when_no_rule_matches(tmp_path: Path):
    _, prepared = prepared_inert(tmp_path)

    evaluation = PermissionGate().evaluate(prepared)

    assert evaluation.decision == PermissionDecision.DENY
    assert evaluation.matched_rule_id is None


@pytest.mark.parametrize(
    "decision",
    [PermissionDecision.ALLOW, PermissionDecision.ASK, PermissionDecision.DENY],
)
def test_gate_returns_each_explicit_decision(tmp_path: Path, decision):
    _, prepared = prepared_inert(tmp_path)
    gate = PermissionGate(
        [PermissionRule("explicit-rule", decision, capability_pattern="test.inert")]
    )

    evaluation = gate.evaluate(prepared)

    assert evaluation.decision == decision
    assert evaluation.matched_rule_id == "explicit-rule"


def test_last_matching_rule_wins_like_opencode(tmp_path: Path):
    _, prepared = prepared_inert(tmp_path)
    gate = PermissionGate(
        [
            PermissionRule("general-allow", PermissionDecision.ALLOW),
            PermissionRule(
                "specific-deny",
                PermissionDecision.DENY,
                capability_pattern="test.inert",
            ),
        ]
    )

    evaluation = gate.evaluate(prepared)

    assert evaluation.decision == PermissionDecision.DENY
    assert evaluation.matched_rule_id == "specific-deny"


def test_rules_are_scoped_by_permission_and_capability(tmp_path: Path):
    _, prepared = prepared_inert(tmp_path)
    gate = PermissionGate(
        [
            PermissionRule(
                "wrong-permission",
                PermissionDecision.ALLOW,
                permission=PermissionClass.WRITE,
                capability_pattern="test.*",
            ),
            PermissionRule(
                "wrong-capability",
                PermissionDecision.ALLOW,
                permission=PermissionClass.READ,
                capability_pattern="filesystem.*",
            ),
        ]
    )

    assert gate.evaluate(prepared).decision == PermissionDecision.DENY


@pytest.mark.skipif(os.name != "nt", reason="Case-insensitive path matching is Windows-specific.")
def test_resource_rules_use_canonical_containment_and_windows_case_folding(
    tmp_path: Path,
):
    allowed = tmp_path / "Allowed"
    allowed.mkdir()
    target = allowed / "sample.txt"
    target.write_text("content", encoding="utf-8")
    prepared = prepare_capability_call(
        FilesystemStatCapability(),
        {"path": str(target)},
        context(tmp_path),
    )
    case_variant = Path(str(allowed).swapcase())
    gate = PermissionGate(
        [
            PermissionRule(
                "allow-stat-root",
                PermissionDecision.ALLOW,
                permission=PermissionClass.READ,
                capability_pattern="filesystem.stat",
                resource_root=case_variant,
            )
        ]
    )

    assert gate.evaluate(prepared).decision == PermissionDecision.ALLOW


def test_resource_rule_rejects_prefix_sibling(tmp_path: Path):
    allowed = tmp_path / "work"
    sibling = tmp_path / "work-secret"
    allowed.mkdir()
    sibling.mkdir()
    prepared = prepare_capability_call(
        FilesystemStatCapability(),
        {"path": str(sibling / "secret.txt")},
        context(tmp_path),
    )
    gate = PermissionGate(
        [
            PermissionRule(
                "allow-work",
                PermissionDecision.ALLOW,
                capability_pattern="filesystem.*",
                resource_root=allowed,
            )
        ]
    )

    assert gate.evaluate(prepared).decision == PermissionDecision.DENY


def test_approved_request_is_bound_to_exact_call_arguments_and_rule(tmp_path: Path):
    evaluation = ask_evaluation(tmp_path)
    manager = ApprovalManager(clock=lambda: 10.0, id_factory=lambda: "approval-1")
    request = manager.request(evaluation, ttl_seconds=30.0)
    approved = manager.resolve(request.approval_id, ApprovalStatus.APPROVED)

    accepted = manager.authorize(evaluation, approval_id=approved.approval_id)
    changed_arguments = ask_evaluation(tmp_path, value="changed")
    changed_call = ask_evaluation(tmp_path, call_id="call-2")
    changed_rule = PermissionGate(
        [PermissionRule("different-ask", PermissionDecision.ASK)]
    ).evaluate(prepared_inert(tmp_path)[1])

    assert accepted.allowed
    assert accepted.code == AuthorizationCode.ALLOWED
    assert accepted.approval_status == ApprovalStatus.CONSUMED
    for changed in (changed_arguments, changed_call, changed_rule):
        rejected = manager.authorize(changed, approval_id=approved.approval_id)
        assert not rejected.allowed
        assert rejected.code == AuthorizationCode.APPROVAL_MISMATCH


def test_approval_cannot_execute_the_same_call_twice(tmp_path: Path):
    evaluation = ask_evaluation(tmp_path)
    manager = ApprovalManager(id_factory=lambda: "approval-once")
    request = manager.request(evaluation, now=1.0)
    manager.resolve(request.approval_id, ApprovalStatus.APPROVED, now=2.0)

    first = manager.authorize(evaluation, approval_id=request.approval_id, now=2.0)
    replay = manager.authorize(evaluation, approval_id=request.approval_id, now=2.0)

    assert first.allowed
    assert not replay.allowed
    assert replay.code == AuthorizationCode.APPROVAL_CONSUMED


def test_approval_expires_even_after_it_was_approved(tmp_path: Path):
    evaluation = ask_evaluation(tmp_path)
    manager = ApprovalManager(id_factory=lambda: "approval-expiring")
    request = manager.request(evaluation, ttl_seconds=5.0, now=10.0)
    manager.resolve(request.approval_id, ApprovalStatus.APPROVED, now=11.0)

    authorization = manager.authorize(
        evaluation,
        approval_id=request.approval_id,
        now=15.0,
    )

    assert not authorization.allowed
    assert authorization.code == AuthorizationCode.APPROVAL_EXPIRED
    assert authorization.approval_status == ApprovalStatus.EXPIRED


def test_denial_and_missing_approval_are_fail_closed(tmp_path: Path):
    evaluation = ask_evaluation(tmp_path)
    manager = ApprovalManager(id_factory=lambda: "approval-denied")

    required = manager.authorize(evaluation)
    request = manager.request(evaluation, now=1.0)
    manager.resolve(request.approval_id, ApprovalStatus.DENIED, now=2.0)
    denied = manager.authorize(evaluation, approval_id=request.approval_id, now=2.0)

    assert required.code == AuthorizationCode.APPROVAL_REQUIRED
    assert not denied.allowed
    assert denied.code == AuthorizationCode.DENIED


def test_cancellation_resolves_a_pending_approval(tmp_path: Path):
    source = CancellationSource()
    evaluation = ask_evaluation(tmp_path)
    manager = ApprovalManager(id_factory=lambda: "approval-cancelled")
    request = manager.request(evaluation, now=1.0)
    source.cancel("stop")

    authorization = manager.authorize(
        evaluation,
        approval_id=request.approval_id,
        cancellation=source.token,
        now=2.0,
    )

    assert authorization.code == AuthorizationCode.CANCELLED
    assert authorization.approval_status == ApprovalStatus.CANCELLED


def test_shutdown_resolves_all_pending_approvals(tmp_path: Path):
    evaluation = ask_evaluation(tmp_path)
    ids = iter(["approval-a", "approval-b"])
    manager = ApprovalManager(id_factory=lambda: next(ids))
    first = manager.request(evaluation, now=1.0)
    second = manager.request(evaluation, now=1.0)

    records = manager.shutdown(now=2.0)

    assert {record.status for record in records} == {ApprovalStatus.SHUTDOWN}
    for request in (first, second):
        authorization = manager.authorize(
            evaluation,
            approval_id=request.approval_id,
            now=2.0,
        )
        assert authorization.code == AuthorizationCode.SHUTDOWN


def test_unknown_approval_has_a_stable_failure(tmp_path: Path):
    evaluation = ask_evaluation(tmp_path)

    with pytest.raises(ApprovalNotFoundError) as caught:
        ApprovalManager().authorize(evaluation, approval_id="missing", now=1.0)

    assert str(caught.value) == "The approval request does not exist."


def test_permission_rules_are_immutable_and_ids_are_unique():
    rule = PermissionRule("one", PermissionDecision.DENY)

    with pytest.raises(AttributeError):
        rule.rule_id = "changed"
    with pytest.raises(ValueError, match="duplicated"):
        PermissionGate([rule, rule])
