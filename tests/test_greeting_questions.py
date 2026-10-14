"""Greeting turns stay in chat across structured and extracted form paths."""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.agent.contracts import AgentRunResult, AgentRunStatus
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.conversation.questions import present_questions
from app.conversation.question_projection import project_questions
from app.inference.completion import CompletionMetadata, CompletionText
from app.inference.protocol import ModelResponse
from app.runtime.cancellation import CancellationSource
from app.ui.main_window import MainWindow
from tests.test_attachment_composer import wait_for
from tests.test_bounded_edit_recovery import RoomyScriptedModel
from tests.test_plain_questions import ProjectionModel
from tests.test_skill_activation import make_service
from tests.test_questions import Replies


GREETING_REPLY = "Hey. How can I help?"
SOCIAL_FORM = {"version": 1, "questions": [
    {"id": "q1", "title": "How can I help?", "kind": "text", "required": True}]}
TASK_REPLY = "Which style do you want?"
TASK_FORM = {"version": 1, "questions": [
    {"id": "style", "title": TASK_REPLY, "kind": "text", "required": True}]}


def structured(reply, form, language="orsi_questions"):
    return reply + "\n```" + language + "\n" + json.dumps(form) + "\n```"


@pytest.mark.parametrize("user_text", [
    "hey", "HEY!!!", "hey 👋", "hello ORSI", "Hey, O.R.S.I.!", "hi there",
    "Good morning, ORSI", "hey, how are you?", "How's it going?", "What's up?",
    "thanks!", "Thank you, ORSI.", "Szia, ORSI!", "Hogy vagy?", "Hallo ORSI", "Hoe gaat het?",
])
def test_social_turn_rejects_direct_form_but_preserves_reply_and_completion(user_text):
    value = CompletionText(structured(GREETING_REPLY, SOCIAL_FORM), CompletionMetadata(finish_reason="stop"))
    result = present_questions(value, request=user_text)
    assert result == GREETING_REPLY and result.question_batch is None
    assert result.completion == value.completion and result.completion_history == value.completion_history


@pytest.mark.parametrize("user_text", ["hey", "hello ORSI", "how are you?", "Szia!", "hallo"])
def test_social_turn_never_calls_plain_question_extractor(user_text):
    model = ProjectionModel(json.dumps(SOCIAL_FORM))
    assert project_questions(model, request=user_text, answer=GREETING_REPLY,
                             cancellation=CancellationSource().token) is None
    assert model.requests == []


def test_form_only_greeting_retains_readable_text_without_controls_or_error_message():
    result = present_questions(structured("", SOCIAL_FORM), request="hey")
    assert result == "1. How can I help?" and result.question_batch is None
    projected = CompletionText(GREETING_REPLY, question_batch=present_questions(
        structured(GREETING_REPLY, SOCIAL_FORM)).question_batch)
    assert present_questions(projected, request="hey") == GREETING_REPLY
    assert present_questions(projected, request="hey").question_batch is None


@pytest.mark.parametrize("mode", ["local", "cloud"])
@pytest.mark.parametrize("language", ["orsi_questions", "json", "", None])
def test_hey_keeps_real_composer_and_history_then_task_still_opens_form(tmp_path, monkeypatch, mode, language):
    app = QApplication.instance() or QApplication([])
    greeting = GREETING_REPLY if language is None else structured(GREETING_REPLY, SOCIAL_FORM, language)
    model = RoomyScriptedModel([ModelResponse.text(greeting),
                               ModelResponse.text(structured(TASK_REPLY, TASK_FORM))])
    model.mode = mode
    projections = []

    def respond(messages):
        projections.append(messages)
        return json.dumps(SOCIAL_FORM)  # A misclassifying extractor must never get this turn.

    monkeypatch.setattr(model, "respond", respond)
    service, _ = make_service(tmp_path, model=model, agent=True)
    window = MainWindow(service, "SYNTHETIC")
    monkeypatch.setattr(window.notifications, "notify", lambda *_: None)
    window.show()
    try:
        window.input.setPlainText("hey")
        window.submit()
        wait_for(lambda: window.thread is None)
        assert not window._questions_visible() and window._question_panel is None
        assert service.store.visible_messages()[-1].content == GREETING_REPLY
        assert service.store.visible_messages()[-1].question_batch is None
        assert [m._content for m in window.chat._messages if not m.from_user] == [GREETING_REPLY]
        assert projections == [] and service._turn_result.capability_calls == 0
        window._sync_question_form()  # Rebuilding the view cannot recover a rejected greeting form.
        assert not window._questions_visible()

        window.input.setPlainText("Hey, help me write a prompt for a website.")
        window.submit()
        wait_for(lambda: window.thread is None)
        assert window._questions_visible()
        assert window._question_panel.fields["style"].question.title == TASK_REPLY
        assert service.store.visible_messages()[-1].question_batch is not None
    finally:
        window.close()
        service.shutdown()
        app.processEvents()


@pytest.mark.parametrize("user_text", [
    "Hey, help me build a website.", "Hello ORSI, ask me questions about my project.",
    "hi.txt", "Create a greeting message.", "yes", "red", "HTML", "Tell me more",
    "Interview me about how I am doing.", "Szia, segíts egy weboldalhoz.",
])
def test_tasks_and_short_clarification_answers_keep_direct_and_plain_forms(user_text):
    result = present_questions(structured(TASK_REPLY, TASK_FORM), request=user_text)
    assert result.question_batch is not None
    model = ProjectionModel(json.dumps(TASK_FORM))
    batch = project_questions(model, request=user_text, answer=TASK_REPLY,
                              cancellation=CancellationSource().token)
    assert batch is not None and batch.questions[0].title == TASK_REPLY
    assert len(model.requests) == 1


@pytest.mark.parametrize("language", ["orsi_questions", None])
def test_chat_only_greeting_also_keeps_normal_chat(tmp_path, language):
    greeting = GREETING_REPLY if language is None else structured(GREETING_REPLY, SOCIAL_FORM)
    service = ConversationService(Replies([greeting]), ConversationStore(tmp_path / "chat.json"))
    try:
        answer = service.run("hey")
        assert answer == GREETING_REPLY and answer.question_batch is None
    finally:
        service.shutdown()


@pytest.mark.parametrize("user_text, expected_form", [("hey", False), ("Help me plan my website.", True)])
def test_old_saved_form_obeys_eligibility_on_reopen_without_rewriting_history(tmp_path, monkeypatch, user_text, expected_form):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "chat.json"
    store = ConversationStore(path)
    turn = store.begin_turn(user_text)
    reply = present_questions(structured(GREETING_REPLY, SOCIAL_FORM))
    # Construct a pre-fix history using the store's established persistence path.
    store.finish_turn(turn, AgentRunResult(status=AgentRunStatus.COMPLETED,
                                          assistant_text=str(reply), steps=1,
                                          capability_calls=0, protocol_failures=0), reply)
    saved = path.read_bytes()
    reopened = ConversationStore(path)
    reopened_bytes = path.read_bytes()  # Store loading activates the session and updates its timestamp.
    assert (reopened.visible_messages()[-1].question_batch is not None) is expected_form
    assert path.read_bytes() == reopened_bytes
    service = ConversationService(Replies([]), reopened)
    initialized = path.read_bytes()  # UI construction and presentation must leave this snapshot intact.
    window = MainWindow(service, "SYNTHETIC")
    monkeypatch.setattr(window.notifications, "notify", lambda *_: None)
    window.show()
    try:
        assert window._questions_visible() is expected_form
        assert (service.store.visible_messages()[-1].question_batch is not None) is expected_form
        assert path.read_bytes() == initialized
        assert service.store.messages()[-1]["content"] == GREETING_REPLY
        if not expected_form:
            assert [m._content for m in window.chat._messages if not m.from_user] == [GREETING_REPLY]
    finally:
        window.close()
        service.shutdown()
        app.processEvents()
    original, settled = json.loads(saved), json.loads(path.read_bytes())
    assert settled["messages"] == original["messages"] and settled["turns"] == original["turns"]
