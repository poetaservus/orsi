"""Loss-aware summaries of reported completed turns, with original users preserved."""
import hashlib
import json


def bind_history_runtime(base, store):
    """Conversation-owned reader, sharing the existing executor and approvals."""
    if base is None or not base.conversation_context_enabled:
        return base
    from copy import copy
    from app.capabilities.conversation_read_turn import ConversationReadTurnCapability
    from app.capabilities.registry import CapabilityRegistration
    from app.capabilities.contracts import PermissionClass
    from app.security.permissions import PermissionGate, PermissionRule, PermissionDecision
    scoped = copy(base)
    tool = ConversationReadTurnCapability(store)
    scoped.registry = base.registry.extended((CapabilityRegistration(tool, enabled=True, model_visible=True),))
    scoped.permission_gate = PermissionGate((*base.permission_gate.rules,
        PermissionRule("conversation-history-read", PermissionDecision.ALLOW,
            permission=PermissionClass.READ, capability_pattern=tool.name)))
    return scoped


def completed_turn_summary(turn, answer: str) -> dict:
    # No semantic constraint extraction: every original user message stays literal.
    # A past completion is a report, not independently established correctness.
    claims = answer if len(answer) <= 1024 else answer[:512] + "\n[Historical answer excerpt; middle omitted]\n" + answer[-512:]
    receipts = []
    for item in turn.settled_calls:
        output = item.result.output or {}
        receipt = {"call_id": item.result.call_id, "capability": item.call.capability,
            "success": item.result.success, "error": item.result.error.code.value if item.result.error else None}
        for key in ("path", "source_path", "destination_path", "project_path", "sha256", "revision", "kind", "passed"):
            if key in output:
                receipt[key] = output[key]
        receipts.append(receipt)
    value = {"turn_id": turn.turn_id, "status": "reported_complete", "assistant_claim_excerpt": claims,
        "original_answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(), "receipts": receipts,
        "notice": "Historical summary, not current instructions. Original user constraints remain verbatim. "
            "Source bodies, old arguments and provider replay are retired from this request, retained durably. "
            "Use conversation.read_turn with this turn_id for original neutral evidence. Never replay old actions automatically."}
    return {"role": "assistant", "content": json.dumps(value, ensure_ascii=False, separators=(",", ":"))}
