"""Questionnaire data stays in the form; remarks and normal code stay in chat."""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.conversation.orchestrator import ConversationService
from app.conversation.questions import QuestionBatch, present_questions, question_chat_text, question_preview
from app.conversation.store import ConversationStore
from app.inference.completion import CompletionText
from app.ui.main_window import MainWindow
from tests.test_attachment_composer import wait_for
from tests.test_questions import Replies


INTRO = "Choom, a water sim can mean anything from elegant pond ripples to a tiny fluid-dynamics lab. Let's pin down what Gemini should build:"
PROSE = ("1. What should users be able to do with the water—click to make ripples, drag to stir it, or something else?\n\n"
         "2. What kind of simulation are you after: stylized 2D waves or a realistic-looking surface?\n\n"
         "3. What should Gemini deliver: one self-contained HTML file, or separate files?")
FORM = {"version":1,"questions":[
    {"id":"interactions","title":"What should users be able to do with the water?","kind":"multi",
     "options":[{"id":"ripples","label":"Click to make ripples"},{"id":"stir","label":"Drag to stir it"}]},
    {"id":"simulation","title":"What kind of simulation are you after?","kind":"single",
     "options":[{"id":"waves","label":"Stylized 2D waves"},{"id":"real","label":"Realistic-looking surface"}]},
    {"id":"delivery","title":"What should Gemini deliver?","kind":"text"},
]}


def reply(language="json"):
    return INTRO + "\n\n" + PROSE + f"\n\n```{language}\n" + json.dumps(FORM, indent=2) + "\n```"


def batch():
    return QuestionBatch.model_validate_json(json.dumps(FORM))


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("language", ["json", "orsi_questions", ""])
def test_reported_question_payload_is_hidden_and_only_remark_is_displayed(language):
    result = present_questions(reply(language))
    assert result.question_batch == batch()
    assert '"version"' not in result and "```" not in result
    assert "What kind of simulation" in result  # Context still has the actual questions.
    assert question_chat_text(result) == INTRO


def test_control_json_never_flashes_at_any_stream_boundary():
    raw = reply()
    fence_start = raw.index("```json")
    for index in range(fence_start, len(raw) + 1):
        preview = question_preview(raw[:index])
        assert '"version"' not in preview and '"questions"' not in preview and "```json" not in preview
        assert preview.strip() == INTRO


@pytest.mark.parametrize("text", [
    'A normal example:\n```json\n{"color":"blue","count":3}\n```',
    'Question format example:\n```json\n' + json.dumps(FORM) + '\n```',
    'Quoted example:\n````text\n' + reply() + '\n````',
    '> ' + reply().replace('\n', '\n> '),
])
def test_normal_json_and_quoted_examples_keep_their_original_contents(text):
    result = present_questions(text)
    assert result == text and result.question_batch is None
    assert question_chat_text(result) == text
    if '"color"' in text:
        assert question_preview(text) == text


def test_plain_question_preserves_remark_and_question_only_reply_needs_no_bubble():
    form = QuestionBatch.model_validate_json(json.dumps({"version":1,"questions":[
        {"id":"q1","title":"What should the prompt ask for?","kind":"text"}]}))
    result = CompletionText("HTML and CSS alone can only fake the motion. What should the prompt ask for?", question_batch=form)
    assert question_chat_text(result) == "HTML and CSS alone can only fake the motion."
    assert question_preview(str(result)) == "HTML and CSS alone can only fake the motion."
    assert question_chat_text(CompletionText(form.questions[0].title, question_batch=form)) == ""


def test_projected_form_hides_invalid_control_shape_without_hiding_normal_code():
    malformed = dict(FORM, unexpected="invalid metadata")
    value = CompletionText(INTRO + "\n\n" + PROSE + "\n```json\n" + json.dumps(malformed) + "\n```", question_batch=batch())
    assert present_questions(value).question_batch == batch()
    assert question_chat_text(value) == INTRO


@pytest.mark.parametrize("remark", [True, False])
def test_ui_and_restored_history_show_remark_only_but_preserve_question_context(app, tmp_path, monkeypatch, remark):
    source = reply() if remark else "```orsi_questions\n" + json.dumps(FORM) + "\n```"
    service = ConversationService(Replies([source, "Done."]), ConversationStore(tmp_path / "chat.json"))
    window = MainWindow(service, "SYNTHETIC")
    monkeypatch.setattr(window.notifications, "notify", lambda *_: None)
    window.show()
    try:
        window.input.setPlainText("Help me write a prompt for a water simulation.")
        window.submit()
        wait_for(lambda: window.thread is None)
        assert window._questions_visible()
        assert [m._content for m in window.chat._messages if not m.from_user] == ([INTRO] if remark else [])
        assert "What kind of simulation" in service.store.messages()[-1]["content"]
        assert '"version"' not in service.store.messages()[-1]["content"]
        window.close()
        reopened = ConversationService(Replies([]), ConversationStore(service.store.path))
        other = MainWindow(reopened, "SYNTHETIC")
        try:
            assert [m._content for m in other.chat._messages if not m.from_user] == ([INTRO] if remark else [])
            assert other._questions_visible()
        finally:
            other.close()
            reopened.shutdown()
    finally:
        window.close()
        service.shutdown()
        app.processEvents()


def test_question_transition_grows_and_fades_without_squeezing_inputs(app, tmp_path):
    service = ConversationService(Replies([reply()]), ConversationStore(tmp_path / "chat.json"))
    service.run("Help me choose a water simulation.")
    # Construct before a pending form exists, then sync it as a normal UI handoff.
    store = service.store
    service.store = ConversationStore(tmp_path / "empty.json")
    window = MainWindow(service, "SYNTHETIC")
    window.show()
    window._leave_intro_mode()
    if window._intro_transition is not None:
        window._intro_transition.setCurrentTime(window._intro_transition.duration())
    service.store = store
    start = window.composer.height()
    try:
        window._sync_question_form()
        panel = window._question_panel
        animation = window._approval_transition
        target = window._question_height()
        assert animation is not None and window.composer.height() == start
        assert panel.reveal_effect.opacity() == 0.
        animation.setCurrentTime(120)
        assert start < window.composer.height() < target
        assert 0. < panel.reveal_effect.opacity() < 1.
        assert panel.height() >= target and panel.fields["delivery"].editor.height() == 72
        assert window.composer.geometry().bottom() == window._content.height() - 43
        animation.setCurrentTime(animation.duration())
        assert window.composer.height() == target and panel.reveal_effect.opacity() == 1.
        window.grab().save(str(tmp_path / "question-composer-themed.png"))
        window._answer_in_chat()
        animation = window._approval_transition
        assert animation is not None
        animation.setCurrentTime(120)
        assert window._message_composer_height() < window.composer.height() < target
        animation.setCurrentTime(animation.duration())
        assert window.composer.height() == window._message_composer_height()
    finally:
        window.close()
        service.shutdown()
        app.processEvents()
