"""Require a source-grounded hypothesis after an executed project defect check.

This enforces an explanation's structure and receipt, not its semantic truth.
Inspection setup failures need inspection correction, not speculative edits.
"""
import os
import re

from app.agent.edit_progress import EditRejection
from app.agent.feedback import canonical_json
from app.capabilities.repair_diagnosis import RepairDiagnosis
from app.agent.contracts import SettledCall
from app.agent.source_evidence import source_read_proof, path_key, invalidate_read_cache


def _under(path, project):
    try:
        return os.path.commonpath((os.path.normcase(os.path.abspath(path)), project)) == project
    except (ValueError, TypeError):
        return False


def _scope(check):
    return canonical_json({key:check.get(key) for key in
        ('action','target','label','expectation','value','reference','properties','state')})


def _checks(call, output):
    """Include the requested assertion value without recording source in logs."""
    steps = call.arguments.get('steps', [])
    checks = []
    for index, check in enumerate(output.get('checks', [])):
        check = dict(check)
        if index < len(steps) and all(steps[index].get(key) == check.get(key) for key in ('action', 'target')):
            for key in ('value', 'reference', 'properties', 'state'):
                if key in steps[index]:
                    check[key] = steps[index][key]
        checks.append(check)
    return checks


SETUP_FAILURES = {'selector_error', 'target_not_found', 'checkpoint_reference_unavailable',
    'observation_unavailable', 'action_incompatible'}


class RepairLoopTracker:
    def __init__(self):
        self._failures = {}
        self._reads = {}
        self._source_calls = []
        self._source_steps = {}
        self._diagnoses = {}
        self.refresh_project = None

    def source_changed(self, project):
        """A proven settled project revision renews its bounded reassessment."""
        self._diagnoses.pop(project, None)
        for failure in self._failures.get(project, []):
            failure['source_changed'] = True
            failure['exhausted'] = False

    def prerequisite(self, call, *, step):
        """Return only fixed diagnostic categories and runtime-owned receipts."""
        for project, failures in self._failures.items():
            if not _under(call.arguments.get('path'), project):
                continue
            failure = max(failures, key=lambda item: item['step'])
            if any(item.get('exhausted') for item in failures):
                return 'current_evidence_required', failure['receipt']
            if call.capability == 'filesystem.read_text':
                return 'source_read_required', failure['receipt']
            if call.capability not in {'filesystem.edit_text', 'filesystem.write_text'}:
                return None
            try:
                diagnosis = RepairDiagnosis.model_validate(call.arguments.get('repair_diagnosis'))
            except ValueError:
                diagnosis = None
            if diagnosis is None or diagnosis.evidence_receipt not in failure['receipts']:
                return 'repair_diagnosis_required', failure['receipt']
            if not any(failure['step'] < start <= end < step and _under(path, project)
                    for path, (start, end) in self._reads.items()):
                return 'source_read_required', failure['receipt']
        return None

    @staticmethod
    def _failure_scope(output):
        checks = [{key: c.get(key) for key in ('action', 'target', 'label', 'expectation', 'failure_kind',
                'value', 'reference', 'properties', 'state')}
            for c in output.get('checks', []) if c.get('passed') is False
            and c.get('failure_kind') not in SETUP_FAILURES]
        problems = sorted({p.get('kind') for p in output.get('problems', []) if isinstance(p.get('kind'), str)})
        return canonical_json({'checks': checks, 'problems': problems}) if checks or problems else None

    def before(self, call, *, step):
        if call.capability not in {'filesystem.edit_text','filesystem.write_text'}:
            return None
        for project, failures in self._failures.items():
            if not _under(call.arguments.get('path'), project):
                continue
            failure = max(failures, key=lambda item: item['step'])
            if any(item.get('exhausted') for item in failures):
                return EditRejection('inspection_recovery_exhausted',
                    'No edit executed. A different unresolved inspection exceeded the bounded reassessment '
                    'allowance for this unchanged project revision. Report the outstanding checks or complete '
                    'the matching inspection; repeated source reads cannot renew this allowance.')
            try:
                diagnosis = RepairDiagnosis.model_validate(call.arguments.get('repair_diagnosis'))
            except ValueError:
                diagnosis = None
            fresh = any(failure['step'] < start_step <= read_step < step and _under(path, project)
                for path, (start_step, read_step) in self._reads.items())
            if diagnosis is None or diagnosis.evidence_receipt not in failure['receipts'] or not fresh:
                missing = ('a valid five-part repair_diagnosis' if diagnosis is None else
                    'the active inspection receipt in repair_diagnosis' if diagnosis.evidence_receipt not in failure['receipts'] else
                    'a complete current source read received after the active inspection')
                return EditRejection('inspection_diagnosis',
                    f"No edit executed after failed inspection {failure['receipt']}. Missing prerequisite: {missing}. Receive a complete current source read "
                    'after that check and before the retry. Supply repair_diagnosis as five strings in order: '
                    '[evidence_receipt, failure, evidence-supported suspected_cause, proposed_change, confirming_observation]. '
                    'Existing approval, redundant-edit and rollback limits still apply.')
        return None

    @staticmethod
    def _feedback(failure):
        if failure.get('exhausted'):
            return (f"Project check {failure['receipt']} exposed another unresolved scope after the bounded "
                'reassessment allowance for this revision was used. No source repair is admitted for that scope. '
                'Complete its matching inspection or report the outstanding work; further reads do not renew this allowance.')
        return (f"Project check {failure['receipt']} found {failure['kind']}. "
            'Before another source repair, identify what failed, the current receipt/source evidence supporting '
            'the suspected cause, which change addresses it, and which observation would confirm or disprove it. '
            'Use repair_diagnosis=[evidence_receipt, failure, suspected_cause, proposed_change, confirming_observation] '
            'on the edit/write call. Preserve existing approval and rollback limits.')

    def observe(self, call, result, *, step):
        self.refresh_project = None
        output = result.output if isinstance(result.output, dict) else {}
        settled = SettledCall(provider_message_id=f'step-{step}', call=call, result=result)
        proof = source_read_proof(settled, self._source_calls)
        self._source_calls.append(settled)
        self._source_steps[result.call_id] = step
        invalidate_read_cache(self._reads, call, result)
        if call.capability == 'filesystem.read_text' and result.success:
            path = output.get('path')
            if isinstance(path, str):
                if proof is not None:
                    self._reads[path_key(path)] = (self._source_steps[proof.call_ids[0]], step)
                elif (output.get('source_complete') is True and not output.get('truncated_by_bytes')
                        and not output.get('truncated_by_lines')):
                    self._reads[path_key(path)] = (step, step)
            return None
        if call.capability != 'project.inspect':
            return None
        if not result.success:
            return 'Inspection arguments/execution failed. Correct the reported tool/setup error before retrying; no browser behavior was established.'
        if output.get('inspection_complete') is not True:
            return 'Preview startup/navigation was unavailable. Correct preview setup before inspecting; this is not evidence of an animation defect.'
        project = output.get('project_path')
        if not isinstance(project,str):
            return None
        project = os.path.normcase(os.path.abspath(project))
        checks = _checks(call, output)
        failed = [c for c in checks if c.get('passed') is False]
        problems = output.get('problems', [])
        if failed and not problems and all(c.get('failure_kind') in SETUP_FAILURES for c in failed):
            return ('Inspection selector/target/capture checks failed. Correct or verify the selector and readiness wait before retrying. '
                'A selector error alone does not justify an animation repair. Do not treat a corrected inspection as a source fix.')
        signature = self._failure_scope({**output, 'checks': checks})
        diagnoses = self._diagnoses.setdefault(project, [])
        snapshot = output.get('screenshot_sha256')
        captured = isinstance(snapshot, str) and re.fullmatch(r'[0-9a-f]{64}', snapshot)
        admitted = (bool(captured) or signature is not None) and (not diagnoses or
            signature is not None and signature not in diagnoses and len(diagnoses) < 2)
        if admitted:
            diagnoses.append(signature)
            self.refresh_project = project
        if output.get('passed') is False and (failed or problems):
            previous = self._failures.get(project, [])
            equivalent = next((item for item in previous if item['signature'] == signature
                and not item.get('source_changed')), None)
            if equivalent is not None:
                # A repeated observation is history, not a new prerequisite. Keep
                # the receipt/read boundary whose matching allowance was granted.
                equivalent['receipts'].add(result.call_id)
                return self._feedback(max(previous, key=lambda item: item['step']))
            failure = dict(receipt=result.call_id, receipts={result.call_id}, step=step,
                kind='interaction_assertion_failed' if failed else 'visual_or_runtime_defect',
                scopes={_scope(c) for c in failed if c.get('failure_kind') not in SETUP_FAILURES},
                problems={p.get('kind') for p in problems}, signature=signature, exhausted=not admitted)
            # Preserve older unresolved scopes. A later narrow pass may discharge
            # its own checks, but cannot erase a different known defect.
            self._failures[project] = [*previous, failure]
            return self._feedback(failure)
        previous = self._failures.get(project, [])
        if previous and output.get('passed') is True:
            # Empty/loading-only checks cannot erase a failed interaction scope.
            passed = {_scope(c) for c in checks if c.get('passed') is True}
            remaining = []
            for failure in previous:
                failure['scopes'] -= passed
                failure['problems'] &= {p.get('kind') for p in problems}
                if failure['scopes'] or failure['problems']:
                    remaining.append(failure)
            if remaining:
                self._failures[project] = remaining
            else:
                self._failures.pop(project, None)
        return None
