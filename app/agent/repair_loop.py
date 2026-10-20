"""Require a source-grounded hypothesis after an executed project defect check.

This enforces an explanation's structure and receipt, not its semantic truth.
Inspection setup failures need inspection correction, not speculative edits.
"""
import os

from app.agent.edit_progress import EditRejection
from app.agent.feedback import canonical_json
from app.capabilities.repair_diagnosis import RepairDiagnosis
from app.agent.contracts import SettledCall
from app.agent.source_evidence import source_read_proof


def _under(path, project):
    try:
        return os.path.commonpath((os.path.normcase(os.path.abspath(path)), project)) == project
    except (ValueError, TypeError):
        return False


def _scope(check):
    return canonical_json({key:check.get(key) for key in ('action','target','label','expectation')})


class RepairLoopTracker:
    def __init__(self):
        self._failures = {}
        self._reads = {}
        self._source_calls = []
        self._source_steps = {}

    def before(self, call, *, step):
        if call.capability not in {'filesystem.edit_text','filesystem.write_text'}:
            return None
        for project, failure in self._failures.items():
            if not _under(call.arguments.get('path'), project):
                continue
            try:
                diagnosis = RepairDiagnosis.model_validate(call.arguments.get('repair_diagnosis'))
            except ValueError:
                diagnosis = None
            fresh = any(failure['step'] < start_step <= read_step < step and _under(path, project)
                for path, (start_step, read_step) in self._reads.items())
            if diagnosis is None or diagnosis.evidence_receipt != failure['receipt'] or not fresh:
                return EditRejection('inspection_diagnosis',
                    f"No edit executed after failed inspection {failure['receipt']}. Receive a complete current source read "
                    'after that check and before the retry. Supply repair_diagnosis as five strings in order: '
                    '[evidence_receipt, failure, evidence-supported suspected_cause, proposed_change, confirming_observation]. '
                    'Existing approval, redundant-edit and rollback limits still apply.')
        return None

    @staticmethod
    def _feedback(failure):
        return (f"Project check {failure['receipt']} found {failure['kind']}. "
            'Before another source repair, identify what failed, the current receipt/source evidence supporting '
            'the suspected cause, which change addresses it, and which observation would confirm or disprove it. '
            'Use repair_diagnosis=[evidence_receipt, failure, suspected_cause, proposed_change, confirming_observation] '
            'on the edit/write call. Preserve existing approval and rollback limits.')

    def observe(self, call, result, *, step):
        output = result.output if isinstance(result.output, dict) else {}
        settled = SettledCall(provider_message_id=f'step-{step}', call=call, result=result)
        proof = source_read_proof(settled, self._source_calls)
        self._source_calls.append(settled)
        self._source_steps[result.call_id] = step
        if call.capability == 'filesystem.read_text' and result.success:
            path = output.get('path')
            if isinstance(path, str):
                if proof is not None:
                    self._reads[path] = (self._source_steps[proof.call_ids[0]], step)
                elif (output.get('source_complete') is True and not output.get('truncated_by_bytes')
                        and not output.get('truncated_by_lines')):
                    self._reads[path] = (step, step)
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
        checks = output.get('checks', [])
        failed = [c for c in checks if c.get('passed') is False]
        if failed and all(c.get('failure_kind') in {'selector_error','target_not_found','checkpoint_reference_unavailable','observation_unavailable'} for c in failed):
            return ('Inspection selector/target/capture checks failed. Correct or verify the selector and readiness wait before retrying. '
                'A selector error alone does not justify an animation repair. Do not treat a corrected inspection as a source fix.')
        problems = output.get('problems', [])
        if output.get('passed') is False and (failed or problems):
            failure = dict(receipt=result.call_id, step=step,
                kind='interaction_assertion_failed' if failed else 'visual_or_runtime_defect',
                scopes={_scope(c) for c in failed}, problems={p.get('kind') for p in problems})
            self._failures[project] = failure
            return self._feedback(failure)
        previous = self._failures.get(project)
        if previous and output.get('passed') is True:
            # Empty/loading-only checks cannot erase a failed interaction scope.
            passed = {_scope(c) for c in checks if c.get('passed') is True}
            if previous['scopes'] <= passed and not (previous['problems'] & {p.get('kind') for p in problems}):
                self._failures.pop(project)
        return None
