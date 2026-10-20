"""Validate review claims against settled receipts, not the reviewer's assertions."""
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    call_id: str = Field(min_length=1, max_length=128)
    claim: Literal['passed', 'failed', 'running', 'completed', 'succeeded', 'ready', 'unverified']
    visual_sha256: tuple[str, ...] = Field(default=(), max_length=5)
    readiness_call_id: str | None = Field(default=None, min_length=1, max_length=128)


def review_receipts(calls):
    """Keep each project check and the latest observation of each shell session."""
    records = {}
    for item in calls:
        name, output = item.call.capability, item.result.output or {}
        if name not in {'project.verify', 'project.inspect', 'shell.run'}:
            continue
        session = output.get('session_id') or call_session(item)
        key = ('session', session) if name == 'shell.run' and isinstance(session, str) else ('call', item.result.call_id)
        records[key] = item
    return tuple(records.values())


def call_session(item):
    return item.call.arguments.get('session_id') if item.call.arguments.get('action') in {'status', 'stop'} else None


def screenshot_digests(output):
    checkpoints = output.get('checkpoints', [])
    return {observation['screenshot_sha256'] for observation in [
        *(checkpoints if isinstance(checkpoints, list) else []), output]
        if isinstance(observation, dict) and isinstance(observation.get('screenshot_sha256'), str)}


def receipt_claim(item):
    result, output = item.result, item.result.output or {}
    if not result.success:
        return 'failed'
    if item.call.capability in {'project.verify', 'project.inspect'}:
        return 'passed' if output.get('passed') is True else 'failed'
    if output.get('running') is True:
        return 'running'
    if output.get('command_completed') is True:
        return 'failed' if output.get('command_succeeded') is False else 'completed'
    return 'unverified'


def evidence_catalog(calls, goal=None):
    return [{'call_id': item.result.call_id, 'capability': item.call.capability,
             'observed': 'unverified' if goal is not None and any(check.call_id == item.result.call_id and check.stale
                 for check in goal.verification) else receipt_claim(item),
             'superseded_by': goal.superseded_verification.get(item.result.call_id) if goal is not None else None}
            for item in review_receipts(calls)]


def compile_review_evidence(goal, calls):
    """The runtime owns receipt bookkeeping; the model assesses task coverage."""
    entries = []
    for item in review_receipts(calls):
        claim = receipt_claim(item)
        if any(check.call_id == item.result.call_id and check.stale for check in goal.verification):
            claim = 'unverified'
        elif claim == 'completed' and (item.result.output or {}).get('command_succeeded') is True:
            claim = 'succeeded'
        entries.append(ReviewEvidence(call_id=item.result.call_id, claim=claim))
    return tuple(entries)


def validate_review_evidence(review, goal, calls, delivered_visuals=()):
    if review.evidence_origin == 'runtime' and review.evidence != compile_review_evidence(goal, calls):
        raise ValueError('Completion evidence must match the runtime ledger.')
    records = {item.result.call_id: item for item in calls}
    latest_ids = {item.result.call_id for item in review_receipts(calls)}
    screenshots = set().union(*(screenshot_digests(item.result.output or {}) for item in calls
        if item.call.capability == 'project.inspect' and item.result.success))
    if not set(delivered_visuals) <= screenshots:
        raise ValueError('Visual assessment delivery must match original inspection receipts.')
    references = [claim.call_id for claim in review.evidence]
    if len(references) != len(set(references)):
        raise ValueError('Completion evidence must not repeat a receipt.')
    if not set(references) <= records.keys():
        raise ValueError('Completion evidence references an unknown current-turn receipt.')
    if review.status == 'ready' and not latest_ids <= set(references):
        raise ValueError('Account for each project check and latest shell outcome in evidence, including failed or unverified checks.')
    for claim in review.evidence:
        item = records.get(claim.call_id)
        output = item.result.output or {}
        if item.call.capability == 'shell.run' and claim.claim != 'unverified' and claim.call_id not in latest_ids:
            raise ValueError('Completion evidence must use the latest shell session outcome.')
        observed = receipt_claim(item)
        verification = next((check for check in goal.verification if check.call_id == claim.call_id), None)
        if claim.claim == 'passed':
            if observed != 'passed' or verification is None or verification.stale:
                raise ValueError('A passed claim requires a current passing project receipt.')
        elif claim.claim in {'failed', 'running'} and claim.claim != observed:
            raise ValueError('Completion evidence does not match the recorded tool outcome.')
        elif claim.claim == 'completed' and (not item.result.success or output.get('command_completed') is not True):
            raise ValueError('Completion evidence does not match the recorded tool outcome.')
        elif claim.claim == 'succeeded' and (not item.result.success or output.get('command_completed') is not True
                                            or output.get('command_succeeded') is not True):
            raise ValueError('Completion evidence requires confirmed command success, not just terminal execution.')
        elif claim.claim == 'ready':
            readiness = records.get(claim.readiness_call_id)
            ready_output = (readiness.result.output or {}) if readiness is not None else {}
            workdir, project = output.get('workdir'), ready_output.get('project_path')
            session = output.get('session_id') or call_session(item)
            first_observation = next((index for index, candidate in enumerate(calls)
                if session and ((candidate.result.output or {}).get('session_id') or call_session(candidate)) == session), len(calls))
            inspection_index = next((index for index, candidate in enumerate(calls)
                if candidate.result.call_id == claim.readiness_call_id), -1)
            if (observed != 'running' or readiness is None or readiness.call.capability != 'project.inspect'
                    or inspection_index < first_observation
                    or receipt_claim(readiness) != 'passed' or ready_output.get('inspection_complete') is not True
                    or readiness.call.arguments.get('server_executable') is not None
                    or not isinstance(workdir, str) or not isinstance(project, str)
                    or os.path.normcase(os.path.normpath(workdir)) != os.path.normcase(os.path.normpath(project))
                    or any(check.call_id == readiness.result.call_id and check.stale for check in goal.verification)):
                raise ValueError('Server readiness requires a passing current inspection of the same project; liveness alone is insufficient.')
        if claim.readiness_call_id is not None and claim.claim != 'ready':
            raise ValueError('Readiness evidence belongs only to a ready server claim.')
        known = screenshot_digests(output)
        if not set(claim.visual_sha256) <= known & set(delivered_visuals):
            raise ValueError('Visual assessment requires the exact screenshot delivered to this model turn.')
