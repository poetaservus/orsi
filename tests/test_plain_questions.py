"""Regression for the actual plain-text clarification that missed the composer."""
from copy import deepcopy
import json
import os
from threading import Event, Timer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.question_projection import project_questions, projection_candidate
from app.conversation.store import ConversationStore
from app.inference.completion import CompletionMetadata, CompletionText
from app.inference.engine import InferenceEngine
from app.inference.protocol import ModelResponse
from app.runtime.cancellation import CancellationSource, TaskCancelled
from app.settings.agent import AgentFeatureConfig
from app.ui.main_window import MainWindow
from tests.test_attachment_composer import wait_for


REQUEST = "i need a prompt to generate a sand simulation in CSS and HTML"
REPLY = ("A moving sand simulation usually needs JavaScript; HTML and CSS alone can only fake the motion. "
         "What should the prompt ask for?")
TITLE = "What should the prompt ask for?"
FORM = {"version": 1, "questions": [{"id": "q1", "title": TITLE, "kind": "text", "required": True}]}


class ProjectionModel(InferenceEngine):
    context_length = 16384
    max_response_tokens = 1024

    def __init__(self, response):
        self.response = response
        self.requests = []

    def respond(self, messages):
        self.requests.append(deepcopy(messages))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def project(model, answer=REPLY, **kwargs):
    return project_questions(model, request=REQUEST, answer=answer,
                             cancellation=CancellationSource().token, **kwargs)


def test_plain_question_is_projected_without_invented_options_or_rewritten_text():
    model = ProjectionModel(json.dumps(FORM))
    batch = project(model)
    assert batch.questions[0].title == TITLE and batch.questions[0].kind == "text"
    assert batch.questions[0].options == () and len(model.requests) == 1
    assert [m["role"] for m in model.requests[0]] == ["system", "user"]
    assert json.loads(model.requests[0][1]["content"]) == {"current_request": REQUEST, "assistant_reply": REPLY}


@pytest.mark.parametrize("value", ["null", "not JSON", '{"version":2}',
    json.dumps({"version":1,"questions":[{"id":"q1","title":"Something the assistant never asked?","kind":"text"}]}),
    json.dumps({"version":1,"questions":[{"id":"q1","title":TITLE,"kind":"single",
        "options":[{"id":"invented","label":"A fabricated choice"}]}]}),
    json.dumps(FORM).replace('"version": 1', '"version": 2, "version": 1'),
    CompletionText(json.dumps(FORM), CompletionMetadata(finish_reason="length")),
    RuntimeError("Synthetic provider failure")], ids=["none", "invalid", "version", "invented_question",
        "invented_choice", "duplicate", "incomplete", "provider_error"])
def test_invalid_unavailable_or_unfaithful_projection_leaves_chat_available(value):
    assert project(ProjectionModel(value)) is None


def test_choice_and_multilingual_projection_must_match_the_visible_reply():
    answer = "Melyik stílust szeretnéd?\n- Minimalista\n- Színes"
    form = {"version":1,"questions":[{"id":"style","title":"Melyik stílust szeretnéd?", "kind":"single",
        "options":[{"id":"a","label":"Minimalista"},{"id":"b","label":"Színes"}],"allow_other":True}]}
    assert project(ProjectionModel(json.dumps(form)), answer).questions[0].options[1].label == "Színes"
    # Text inside code/quotes is not provenance for new controls.
    assert project(ProjectionModel(json.dumps(form)), "```text\n" + answer + "\n```") is None


@pytest.mark.parametrize("answer", ["Completed.", "```html\n<p>What?</p>\n```", "> What should I do?",
    "Example: `What should I do?`", "1. Melt butter.\n2. Add sugar."])
def test_only_visible_question_candidates_need_a_presentation_request(answer):
    assert not projection_candidate(answer)


def test_size_or_context_limits_skip_projection_before_request():
    model = ProjectionModel(json.dumps(FORM))
    assert project(model, "?" * 17000) is None and model.requests == []
    model.context_length = 32
    assert project(model) is None and model.requests == []


@pytest.mark.parametrize("cancelled", [False, True])
def test_timeout_and_cancellation_release_the_presentation_request(cancelled):
    class Blocking(ProjectionModel):
        def __init__(self):
            super().__init__(None)
            self.release = Event()
            self.stopped = False

        def respond(self, messages):
            self.release.wait(2)
            return "null"

        def cancel_current_request(self):
            self.stopped = True
            self.release.set()
            return True
    source = CancellationSource()
    model = Blocking()
    timer = Timer(.03, source.cancel) if cancelled else None
    if timer:
        timer.start()
    try:
        if cancelled:
            with pytest.raises(TaskCancelled):
                project_questions(model, request=REQUEST, answer=REPLY, cancellation=source.token)
        else:
            assert project_questions(model, request=REQUEST, answer=REPLY, cancellation=source.token,
                                     timeout_seconds=.03) is None
        assert model.stopped and model.release.is_set()
    finally:
        if timer:
            timer.cancel()
        model.release.set()


@pytest.mark.parametrize("mode", ["local", "cloud"])
def test_plain_clarification_reaches_real_composer_after_review(tmp_path, monkeypatch, mode):
    from tests.test_bounded_edit_recovery import RoomyScriptedModel
    from tests.test_current_task_completion import review
    from tests.test_skill_activation import make_service
    app = QApplication.instance() or QApplication([])
    model = RoomyScriptedModel([ModelResponse.text(REPLY), review()], auto_review=False)
    model.mode = mode
    projected = []
    def respond(messages):
        projected.append(deepcopy(messages))
        return json.dumps(FORM)
    monkeypatch.setattr(model, "respond", respond)
    service, _ = make_service(tmp_path, model=model, agent=True)
    window = MainWindow(service, "SYNTHETIC")
    monkeypatch.setattr(window.notifications, "notify", lambda *_: None)
    window.show()
    try:
        window.input.setPlainText(REQUEST)
        window.submit()
        wait_for(lambda: window.thread is None)
        assert window._questions_visible() and window._question_panel.fields["q1"].editor is not None
        assert service.store.visible_messages()[-1].content == REPLY
        assert service.store.visible_messages()[-1].question_batch.questions[0].title == TITLE
        assert len(projected) == 1 and len(model.requests) == 2
        assert len(window.chat._messages) == 2
    finally:
        window.close()
        service.shutdown()
        app.processEvents()


def test_screenshot_flow_through_real_luna_sdk_streaming_and_answer_submission(tmp_path, monkeypatch):
    from tests.test_openai_tools import scripted_sdk
    from tests.test_openai_phase1 import config, response
    from app.settings.openai_cloud import OpenAIModelProfile
    app = QApplication.instance() or QApplication([])
    texts = [REPLY, json.dumps({"goal_id":"turn-1","status":"ready","remaining":[]}),
             json.dumps(FORM), "```text\nCreate a JavaScript sand simulation with HTML and CSS.\n```",
             json.dumps({"goal_id":"turn-2","status":"ready","remaining":[]})]
    payloads = []
    for index, text in enumerate(texts):
        value = response(text, id=f"resp_question_{index}")
        value["output"][0]["id"] = f"msg_question_{index}"
        payloads.append(value)
    engine, client, bodies, _ = scripted_sdk(monkeypatch, payloads,
        engine_config=config(profiles=(OpenAIModelProfile(id="gpt-6-luna", reasoning_effort="medium"),)))
    runtime = build_agent_runtime(engine, config=AgentFeatureConfig(filesystem_stat_enabled=True),
                                  portable_root=tmp_path, state_directory=tmp_path / "runtime")
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"), agent_runtime=runtime,
                                  portable_root=tmp_path, automatic_skills_enabled=False)
    window = MainWindow(service, "SYNTHETIC")
    monkeypatch.setattr(window.notifications, "notify", lambda *_: None)
    previews = []
    original_preview = window._stream_preview
    # Record the worker's preview stream before the widget replaces it at handoff.
    monkeypatch.setattr(window, "_stream_preview", lambda text: (previews.append(text), original_preview(text)))
    window.show()
    try:
        window.input.setPlainText(REQUEST)
        window.submit()
        wait_for(lambda: window.thread is None)
        assert window._questions_visible() and len(bodies) == 3
        wait_for(lambda: window._approval_transition is None)
        assert not window._question_panel.fields["q1"].editor.visibleRegion().isEmpty()
        assert window._question_panel.fields["q1"].question.title == TITLE
        assert bodies[0]["model"] == "gpt-6-luna" and bodies[0]["reasoning"]["effort"] == "medium"
        assert "tools" not in bodies[2] or not bodies[2]["tools"]
        assert all('"version"' not in preview and '"questions"' not in preview for preview in previews)
        window.grab().save(str(tmp_path / "plain-question-composer.png"))
        window._question_panel.fields["q1"].editor.setPlainText("Use JavaScript for real falling sand, with HTML and CSS.")
        expected = window._question_panel.answer_text()
        window._question_panel.send.click()
        wait_for(lambda: window.thread is None)
        assert window._question_panel is None and len(bodies) == 5
        assert service.store.messages()[-2]["content"] == expected and len(service.store.messages()) == 4
        assert service.store.visible_messages()[1].content == REPLY
        assistants = [item for item in bodies[3]["input"] if item.get("role") == "assistant"]
        assert len(assistants) == 1
    finally:
        window.close()
        service.shutdown()
        app.processEvents()
    assert client.is_closed() and engine._runner is None
