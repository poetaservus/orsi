from app.agent.goals import TaskGoal, observe_goal, verification_report
from app.agent.contracts import SettledCall
from app.agent.task_completion import completion_review_message, completion_review_schema
from app.inference.protocol import ModelCapabilityCall
from app.capabilities.contracts import CapabilityResult


def test_review_names_scope_skip_behavior_specific_requirements_and_frame_limits():
    goal = TaskGoal(goal_id='turn-1',objective='Fix the animation; skip browser verification.')
    message = completion_review_message(goal,None)
    text = message['content']
    assert 'Honor explicit instructions to skip browser verification' in text
    assert 'specific unmet user requirement' in text
    assert 'same state' in text and 'immediate upward scrolling' in text
    assert 'screenshot cannot establish smooth frame delivery' in text
    assert completion_review_schema([message])['properties']['goal_id']['enum'] == ['turn-1']


def test_summary_scope_reports_findings_without_requiring_unrequested_source_repairs():
    goal = TaskGoal(goal_id='turn-1',objective='Inspect and summarize this project.')
    for available in (False,True):
        text = completion_review_message(goal,None,browser_inspection_available=available)['content']
        assert 'inspection/summary requests, report' in text
        assert 'only when requested' in text


def inspection(output):
    return SettledCall(provider_message_id='response-1',
        call=ModelCapabilityCall(provider_call_id='call-1',capability='project.inspect',
            arguments=dict(project_path='C:/project',kind='browser')),
        result=CapabilityResult(call_id='receipt-1',capability='project.inspect',success=True,duration_ms=0,
            output=dict(project_path='C:/project',passed=False,**output)))


def test_assertions_visual_observations_and_timing_have_separate_durable_records():
    goal = observe_goal(TaskGoal(goal_id='turn-1',objective='Check reverse scrolling.'),inspection(dict(
        evidence_version=2,screenshot_path='C:/state/screenshot.png',screenshot_sha256='1'*64,
        checkpoints=[dict(label='partial',screenshot_path='C:/state/checkpoint-0.png',screenshot_sha256='2'*64)],
        checks=[dict(action='checkpoint',target='#hero',label='return',expectation='same_state',passed=False),
            dict(action='frame_timing',target='',passed=True,frame_timing={'samples':[]})])))
    evidence = goal.verification[0]
    assert evidence.command_passed is None
    assert len(evidence.interaction_assertions) == 1 and not evidence.interaction_assertions[0].passed
    assert len(evidence.visual_observations) == 2
    assert all(v.status == 'requires_review' for v in evidence.visual_observations)
    assert evidence.frame_timing_captured and not goal.behaviour_verified
    assert 'interaction assertions 0/1 passed' in verification_report(goal)
    assert 'smooth rendering unverified' in verification_report(goal)
    assert TaskGoal.model_validate_json(goal.model_dump_json()) == goal


def test_legacy_receipts_keep_their_original_evidence_projection():
    goal = observe_goal(TaskGoal(goal_id='turn-1',objective='Check the page.'),inspection(dict(
        screenshot_path='C:/state/screenshot.png',checks=[dict(action='visible',target='#hero',passed=True)])))
    item = goal.verification[0]
    assert item.screenshot_path and not item.visual_observations and not item.interaction_assertions


def test_explicit_skip_can_complete_without_a_browser_call(tmp_path):
    from tests.test_agent_runtime import build_runtime, run
    from app.inference.protocol import ModelResponse
    from app.agent.contracts import AgentRunStatus
    runtime, model, _, _, _ = build_runtime(tmp_path,[ModelResponse.text('Source reviewed. Browser behavior is unverified.')])
    try:
        result = runtime.run([{'role':'user','content':'Review the source and skip browser verification.'}],
            session_id='session',turn_id='turn-1',portable_root=tmp_path,allowed_read_roots=(tmp_path,),
            goal_request='Review the source and skip browser verification.')
        assert result.status == AgentRunStatus.COMPLETED and result.capability_calls == 0
        assert 'skip browser verification' in model.requests[-1][-1]['content']
    finally:
        runtime.shutdown()
