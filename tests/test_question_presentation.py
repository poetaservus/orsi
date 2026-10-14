"""Questionnaire data stays in the form; remarks and normal code stay in chat."""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from app.conversation.orchestrator import ConversationService
from app.conversation.questions import QuestionBatch, present_questions, question_chat_text, question_preview
from app.conversation.store import ConversationStore
from app.inference.completion import CompletionText
from app.ui.main_window import MainWindow
from app.ui.questions import QuestionComposer
from tests.test_attachment_composer import wait_for
from tests.test_questions import Replies, fill, payload


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


@pytest.mark.parametrize("size", [(760, 600), (1280, 900)])
def test_larger_question_text_wraps_and_stays_reachable_across_themes(app, size):
    value = payload()
    long_choice = "Read & compare 🌊 detailed examples before choosing the approach that feels most comfortable for this project. " * 2
    value["questions"][0]["options"][0]["label"] = long_choice
    value["questions"][2]["options"][0]["label"] = long_choice
    value["questions"][0]["title"] = "Which kind of work would you like to showcase, and how should visitors explore the details of your favorite projects?"
    window = MainWindow(None, "SYNTHETIC")
    window.resize(*size)
    window.show()
    panel = window._question_panel = QuestionComposer(QuestionBatch.model_validate_json(json.dumps(value)), window.composer)
    window._composer_stack.addWidget(panel)
    window._show_questions()
    if window._approval_transition is not None:
        window._approval_transition.setCurrentTime(window._approval_transition.duration())
    fill(panel)
    expected = panel.answer_text()
    try:
        for theme in ("original", "conformist", "ocean", "original"):
            window.theme_controller.select(theme)
            app.processEvents()
            viewport = panel.scroll.viewport()
            assert panel.scroll.horizontalScrollBar().maximum() == 0
            assert panel.body.width() <= viewport.width()
            assert panel.fields["audience"].editor.font().pixelSize() == 16
            assert panel.fields["audience"].editor.font().family() == window.theme_controller.current.family
            assert panel.fields["style"].combo.font().pixelSize() == 16
            for control in (panel.findChild(QLabel, "questionsHeader"), panel.required_count,
                            panel.hint, panel.chat_button, panel.send):
                assert control.font().pixelSize() == 16
                assert control.font().family() == window.theme_controller.current.family
                assert panel.rect().contains(control.geometry())
            for field in panel.fields.values():
                title = field.findChild(QLabel, "questionTitle")
                assert title.font().pixelSize() == 18
                assert title.font().family() == window.theme_controller.current.family
                assert title.height() >= title.heightForWidth(title.width())
                for button in field.buttons:
                    assert button.font().pixelSize() == 16
                    assert button.font().family() == window.theme_controller.current.family
                    assert button.height() >= button.heightForWidth(button.width())
                for control in (field.editor, field.combo, *field.buttons):
                    if control is not None:
                        panel.scroll.verticalScrollBar().setValue(control.mapTo(panel.body, QPoint()).y())
                        app.processEvents()
                        bounds = control.rect().translated(control.mapTo(viewport, QPoint()))
                        assert viewport.rect().contains(bounds)
            choice = panel.fields["work"].buttons[0]
            assert "\n" in choice.text()
            assert choice.text().replace("\n", " ").replace("&&", "&") == long_choice.rstrip()
            panel.fields["work"].buttons[1].click()
            panel.scroll.verticalScrollBar().setValue(choice.mapTo(panel.body, QPoint()).y())
            app.processEvents()
            QTest.mouseClick(choice, Qt.MouseButton.LeftButton, pos=QPoint(40, choice.height() - 12))
            assert choice.isChecked()  # The last wrapped line is part of the choice's hit target.
            checkbox = panel.fields["features"].buttons[0]
            panel.scroll.verticalScrollBar().setValue(checkbox.mapTo(panel.body, QPoint()).y())
            app.processEvents()
            for expected_checked in (False, True):
                QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton, pos=QPoint(40, checkbox.height() - 12))
                assert checkbox.isChecked() is expected_checked
            assert panel.answer_text() == expected and panel.send.isEnabled()
            assert panel.rect().contains(panel.send.geometry())
            assert window.composer.height() <= size[1] - 140
        if size[1] == 900:
            assert window.composer.height() > 520
    finally:
        window.close()
        app.processEvents()


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
        assert panel.reveal_effect.isEnabled()
        animation.setCurrentTime(120)
        assert start < window.composer.height() < target
        assert 0. < panel.reveal_effect.opacity() < 1.
        assert panel.height() >= target and panel.fields["delivery"].editor.height() == 96
        assert window.composer.geometry().bottom() == window._content.height() - 43
        animation.setCurrentTime(animation.duration())
        assert window.composer.height() == target and panel.reveal_effect.opacity() == 1.
        assert not panel.reveal_effect.isEnabled()
        # Keep keyboard focus and selection while visually inspecting both kinds
        # of focused choice without the former full-row white border.
        window.activateWindow()
        app.processEvents()
        radio = panel.fields["simulation"].buttons[0]
        radio.setFocus()
        app.processEvents()
        QTest.keyClick(radio, Qt.Key.Key_Space)
        assert radio.isChecked() and radio.hasFocus()
        window.grab().save(str(tmp_path / "question-radio-focused.png"))
        checkbox = panel.fields["interactions"].buttons[0]
        QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton, pos=QPoint(8, checkbox.height() // 2))
        assert checkbox.isChecked() and checkbox.hasFocus()
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


def test_transition_reuses_blur_then_returns_to_live_transcript_painting(app, tmp_path, monkeypatch):
    window = MainWindow(None, "SYNTHETIC")
    window.resize(1200, 820)
    window.show()
    window._leave_intro_mode()
    if window._intro_transition is not None:
        window._intro_transition.setCurrentTime(window._intro_transition.duration())
    for _ in range(12):
        window.chat.add_message("Agent", "Synthetic transcript for transition rendering.\n" * 10)
    app.processEvents()
    panel = window._question_panel = QuestionComposer(batch(), window.composer)
    window._composer_stack.addWidget(panel)
    app.processEvents()
    sizes = []
    original = window.bottom_glass._soften

    def soften(pixmap):
        sizes.append(pixmap.size())
        return original(pixmap)

    monkeypatch.setattr(window.bottom_glass, "_soften", soften)
    try:
        window._show_questions()
        animation = window._approval_transition
        animation.pause()
        animation.setCurrentTime(160)
        app.processEvents()
        app.processEvents()
        glass = window.bottom_glass
        cached = glass._blurred_backdrop().toImage()
        count = len(sizes)
        assert glass._transition_blur is not None
        assert glass._blurred_backdrop().toImage() == cached and len(sizes) == count
        # Blank composer clearance must not be included in the expensive blur.
        assert sizes[-1].height() < glass.height()
        animation.setCurrentTime(animation.duration())
        app.processEvents()
        assert not glass._reuse_blur and glass._transition_blur is None
        count = len(sizes)
        glass._blurred_backdrop()
        glass._blurred_backdrop()
        assert len(sizes) == count + 2
        # A return followed by a resize cancels both the animation and its cache.
        window._answer_in_chat()
        window._approval_transition.setCurrentTime(100)
        window._show_questions()
        window.resize(850, 650)
        assert window._approval_transition is None and glass._transition_blur is None
        assert not glass._reuse_blur and not panel.reveal_effect.isEnabled()
        assert window.composer.geometry().bottom() == window._content.height() - 43
    finally:
        window.close()
        app.processEvents()
