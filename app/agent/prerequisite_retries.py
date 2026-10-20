"""One model-requested retry after a rejected mutation's prerequisites change.

This grants repetition accounting only. Dispatch, approvals, rollback and edit
preflight still run normally; settled or uncertain mutations are never replayed.
"""
from dataclasses import dataclass

from app.agent.contracts import SettledCall
from app.agent.feedback import call_fingerprint
from app.agent.source_evidence import path_key, source_read_proof, invalidate_read_cache


def repetition_fingerprint(call):
    if call.capability not in {'filesystem.edit_text', 'filesystem.write_text'}:
        return call_fingerprint(call)
    # Explanatory prose is not a different operation or evidence of progress.
    return call_fingerprint(call.model_copy(update={'arguments': {key: value
        for key, value in call.arguments.items() if key not in {'repair_diagnosis', 'reversal_reason'}}}))


@dataclass(frozen=True)
class _Rejected:
    step: int
    reason: str


class PrerequisiteRetries:
    def __init__(self):
        self._rejected = {}
        self._used = set()
        self._reads = {}
        self._calls = []
        self._steps = {}
        self._blocked_paths = set()

    def renew(self, call, *, step, repair_rejection):
        key = repetition_fingerprint(call)
        rejected = self._rejected.get(key)
        path = path_key(call.arguments.get('path'))
        read = self._reads.get(path)
        if (rejected is None or key in self._used or path in self._blocked_paths or read is None
                or repair_rejection is not None or not rejected.step < read[0] <= read[1] < step):
            return False
        self._used.add(key)
        return True

    def reason(self, call):
        rejected = self._rejected.get(repetition_fingerprint(call))
        return rejected.reason if rejected else None

    def observe(self, call, result, *, step):
        path = path_key(call.arguments.get('path'))
        settled = SettledCall(provider_message_id=f'step-{step}', call=call, result=result)
        proof = source_read_proof(settled, self._calls)
        self._calls.append(settled)
        self._steps[result.call_id] = step
        invalidate_read_cache(self._reads, call, result)
        if call.capability == 'filesystem.read_text' and result.success:
            if proof is not None:
                self._reads[path] = (self._steps[proof.call_ids[0]], step)
            return
        if call.capability not in {'filesystem.edit_text', 'filesystem.write_text'}:
            return
        if result.error is not None and result.error.code.value in {'permission_denied', 'outcome_unknown'}:
            self._blocked_paths.add(path)
        reason = result.metadata.get('edit_recovery')
        if not result.success and reason in {'inspection_diagnosis', 'fresh_source_required',
                'read_before_patch_required', 'target_not_in_read', 'read_digest_mismatch',
                'revision_reversal', 'revision_cycle'}:
            self._rejected.setdefault(repetition_fingerprint(call), _Rejected(step, reason))
        elif result.success:
            self._rejected.pop(repetition_fingerprint(call), None)
            self._reads.pop(path, None)
