"""Essential structured-question, actual adapter and composer handoff checks."""
from copy import deepcopy
import json
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.conversation.questions import (
    QUESTION_MARKER, QuestionBatch, format_answers, present_questions, question_preview,
)
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.completion import CompletionMetadata, CompletionText
from app.inference.engine import InferenceEngine
from app.inference.protocol import ModelResponse
from app.ui.main_window import MainWindow
from app.ui.questions import QuestionComposer
from tests.test_attachment_composer import wait_for


def payload():
    return {"version": 1, "questions": [
        {"id": "work", "title": "What work should it showcase?", "kind": "single", "required": True,
         "options": [{"id": "photo", "label": "Photography"}, {"id": "design", "label": "Design"}], "allow_other": True},
        {"id": "style", "title": "Which style?", "kind": "dropdown", "required": True,
         "options": [{"id": "minimal", "label": "Minimal"}, {"id": "color", "label": "Colorful"}]},
        {"id": "features", "title": "Which sections?", "kind": "multi", "required": False,
         "options": [{"id": "gallery", "label": "Gallery"}, {"id": "contact", "label": "Contact"}]},
        {"id": "audience", "title": "Who is the audience?", "kind": "text", "required": True},
    ]}


def batch():
    return QuestionBatch.model_validate_json(json.dumps(payload()))


def handoff(value=None):
    return "Please answer these questions.\n1. Work? 2. Style? 3. Sections? 4. Audience?\n\n" + QUESTION_MARKER + "\n" + json.dumps(payload() if value is None else value) + "\n```"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("damage", ["duplicate_question", "duplicate_option", "extra", "wrong_kind", "empty", "huge", "reserved"])
def test_invalid_metadata_preserves_readable_questions_without_controls(damage):
    value = payload()
    if damage == "duplicate_question":
        value["questions"].append(deepcopy(value["questions"][0]))
    elif damage == "duplicate_option":
        value["questions"][0]["options"].append(deepcopy(value["questions"][0]["options"][0]))
    elif damage == "extra":
        value["execute"] = "anything"
    elif damage == "wrong_kind":
        value["questions"][0]["kind"] = "approval"
    elif damage == "empty":
        value["questions"] = []
    elif damage == "huge":
        value["questions"][0]["title"] = "x" * 40000
    else:
        value["questions"][0]["options"][0]["id"] = "__other__"
    result = present_questions(handoff(value))
    assert result.question_batch is None and "1. Work?" in result
    assert QUESTION_MARKER not in result


def test_final_envelope_streaming_bounds_and_metadata_are_preserved():
    raw = handoff()
    value = CompletionText(raw, CompletionMetadata(finish_reason="stop"))
    result = present_questions(value)
    assert result.question_batch == batch()
    assert result.completion == value.completion and result.completion_history == value.completion_history
    assert CompletionText(result).question_batch == batch()
    assert present_questions(result, allow_forms=False).question_batch is None
    assert str(result) == raw.split(QUESTION_MARKER)[0].rstrip()
    for index in range(raw.index("```"), len(raw) + 1):
        assert question_preview(raw[:index]).rstrip() == str(result)
    assert present_questions(raw + "\nUnexpected trailing text").question_batch is None
    assert present_questions(CompletionText(raw, CompletionMetadata(finish_reason="length"))).question_batch is None
    assert present_questions(raw, allow_forms=False).question_batch is None
    duplicate = raw.replace('"version": 1', '"version": 2, "version": 1')
    assert present_questions(duplicate).question_batch is None


@pytest.mark.parametrize("text", ["Would you like help?", "Example:\n````text\n" + handoff() + "\n````",
                                     "Quoted:\n> " + handoff().replace("\n", "\n> ")])
def test_ordinary_or_quoted_questions_do_not_activate_a_form(text):
    assert str(present_questions(text)) == text
    assert present_questions(text).question_batch is None
    # Only an incomplete last-line delimiter prefix may be buffered.
    assert question_preview(text) == text


def fill(panel):
    panel.fields["work"].buttons[0].click()
    panel.fields["style"].combo.setCurrentIndex(1)
    panel.fields["features"].buttons[0].click()
    panel.fields["features"].buttons[1].click()
    panel.fields["audience"].editor.setPlainText("Prospective clients")
    panel.additional.setPlainText("Keep it monochrome.")


def test_mixed_controls_validation_custom_answer_and_keyboard(app):
    panel = QuestionComposer(batch())
    panel.show()
    app.processEvents()
    assert not panel.send.isEnabled() and panel.required_count.text() == "3 required"
    assert not any(button.isChecked() for field in panel.fields.values() for button in field.buttons)
    assert panel.fields["style"].combo.currentData() is None
    fill(panel)
    assert panel.send.isEnabled() and panel.required_count.text() == "Ready"
    answer = panel.answer_text()
    assert "Photography" in answer and "Minimal" in answer and "Gallery\nContact" in answer
    assert "Prospective clients" in answer and "Keep it monochrome." in answer
    panel.fields["work"].other_button.click()
    assert not panel.send.isEnabled()
    panel.fields["work"].other_text.setText("Sculpture")
    assert panel.send.isEnabled() and "Sculpture" in panel.answer_text()
    sent = []
    panel.send_requested.connect(lambda: sent.append(True))
    editor = panel.fields["audience"].editor
    editor.setFocus()
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert sent == []  # Multiline input must not submit.
    QTest.keyClick(editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert sent == [True]
    panel.close()


def test_answer_validation_rejects_missing_unknown_or_oversized_answers():
    answers = {q.id: () for q in batch().questions}
    with pytest.raises(ValueError):
        format_answers(batch(), answers)
    answers.update(work=("Photography",), style=("Not an option",), audience=("Clients",))
    with pytest.raises(ValueError):
        format_answers(batch(), answers)
    answers["style"] = ("Minimal",)
    assert "Skipped (optional)." in format_answers(batch(), answers)
    with pytest.raises(ValueError):
        format_answers(batch(), answers, "x" * 8001)


def test_long_single_choice_uses_dropdown_and_optional_questions_can_be_skipped(app):
    value = {"version": 1, "questions": [{"id": "q", "title": "Pick one", "kind": "single", "required": False,
        "options": [{"id": str(i), "label": f"Choice {i}"} for i in range(6)]}]}
    panel = QuestionComposer(QuestionBatch.model_validate_json(json.dumps(value)))
    try:
        assert panel.fields["q"].combo is not None and panel.fields["q"].combo.currentData() is None
        assert panel.send.isEnabled() and "Skipped (optional)." in panel.answer_text()
    finally:
        panel.close()


def test_approval_panel_keeps_its_own_authority_and_restores_question_values(app, tmp_path):
    from tests.test_inline_approvals import ApprovalService, record
    original = ConversationService(Replies([handoff()]), ConversationStore(tmp_path / "chat.json"))
    original.run("Ask questions first")
    service = ApprovalService()
    service.store = original.store
    window = MainWindow(service, "SYNTHETIC")
    window.show()
    try:
        panel = window._question_panel
        fill(panel)
        window._show_approval(record())
        assert window._composer_stack.currentWidget() is window._approval_panel
        panel.send.click()
        assert service.decisions == [] and window.thread is None
        window._approval_panel.finish(True)
        assert service.decisions == [("one", True)]
        assert window._questions_visible() and "Photography" in panel.answer_text()
    finally:
        window.close()
        original.shutdown()
        app.processEvents()


def test_streaming_and_incomplete_responses_never_show_control_json(tmp_path):
    class Streaming(Replies):
        supports_text_streaming = True

        def set_text_observer(self, observer):
            self.observer = observer

        def respond(self, messages):
            result = super().respond(messages)
            for index in range(1, len(result) + 1):
                self.observer(str(result)[:index])
            return result
    previews = []
    model = Streaming([CompletionText(handoff(), CompletionMetadata(finish_reason="length"))])
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"))
    try:
        result = service.run("Ask questions first", text_observer=previews.append)
        assert result.completion.incomplete and result.question_batch is None
        assert all(QUESTION_MARKER not in preview and '"version"' not in preview for preview in previews)
        assert QUESTION_MARKER not in service.store.visible_messages()[-1].content
        assert service.store.visible_messages()[-1].stopped
    finally:
        service.shutdown()


@pytest.mark.parametrize("mode", ["local", "cloud"])
@pytest.mark.parametrize("personality", ["original", "choom"])
def test_reviewed_interview_form_submission_preserves_draft_history_and_policy(app, tmp_path, monkeypatch, mode, personality):
    from tests.test_bounded_edit_recovery import RoomyScriptedModel
    from tests.test_current_task_completion import review
    from tests.test_skill_activation import make_service
    from tests.test_personality_loading import assert_selected
    model = RoomyScriptedModel([ModelResponse.text(handoff()), review(),
                               ModelResponse.text("Here is the completed prompt."), review(goal_id="turn-2")], auto_review=False)
    model.mode = mode
    service, _ = make_service(tmp_path, model=model, agent=True)
    service.select_personality(personality)
    definitions = service.agent_runtime.registry.model_definitions()
    permissions = service.agent_runtime.permission_gate
    window = MainWindow(service, "SYNTHETIC")
    monkeypatch.setattr(window.notifications, "notify", lambda *_: None)
    window.show()
    try:
        window.input.setPlainText("Refine a prompt for a portfolio website.")
        window.submit()
        wait_for(lambda: window.thread is None)
        panel = window._question_panel
        assert panel is not None and window._questions_visible()
        window.input.setPlainText("Preserve this unsent draft")
        window.skill_picker.select_name("style")
        fill(panel)
        window._answer_in_chat()
        assert window.input.toPlainText() == "Preserve this unsent draft" and not window.questions_back.isHidden()
        window.questions_back.click()
        assert panel.fields["work"].buttons[0].isChecked()
        expected = panel.answer_text()
        panel.send.click()
        panel.send.click()  # One durable answer even if the user clicks twice.
        wait_for(lambda: window.thread is None)
        assert window._question_panel is None and window._composer_stack.currentWidget() is window._message_composer
        assert window.input.toPlainText() == "Preserve this unsent draft"
        assert window.skill_picker.selected_name == "style"
        visible = service.store.visible_messages()
        assert len(visible) == 4 and visible[1].question_batch == batch() and visible[2].content == expected
        assert QUESTION_MARKER not in visible[1].content
        assert service.store.messages()[2] == {"role": "user", "content": expected}
        assert any(m.get("content") == expected for m in model.requests[2])
        assert len(model.requests) == 4
        for request in model.requests:
            assert_selected(request, personality)
        assert service.agent_runtime.registry.model_definitions() == definitions
        assert service.agent_runtime.permission_gate is permissions
        reopened = ConversationStore(service.store.path)
        assert reopened.visible_messages()[1].question_batch == batch()
        window.create_new_session()
        assert window._question_panel is None and not service.store.messages()
    finally:
        window.close()
        service.shutdown()
        app.processEvents()


class Replies(InferenceEngine):
    context_length = 131072
    max_response_tokens = 1024

    def __init__(self, replies):
        self.replies = iter(replies)

    def respond(self, messages):
        return next(self.replies)


def test_pending_form_restores_resizes_and_rejects_stale_submission(app, tmp_path):
    service = ConversationService(Replies([handoff()]), ConversationStore(tmp_path / "chat.json"))
    service.run("Ask questions first")
    service = ConversationService(Replies(["Ordinary chat"]), ConversationStore(service.store.path))
    window = MainWindow(service, "SYNTHETIC")
    window.show()
    try:
        assert window._question_panel is not None
        window.resize(760, 600)
        app.processEvents()
        assert window.composer.height() <= 460
        assert window._question_panel.scroll.verticalScrollBar().maximum() > 0
        assert window.chat._layout.contentsMargins().bottom() >= window.composer.height() + 42
        fill(window._question_panel)
        window.grab().save(str(tmp_path / "question-composer.png"))
        service.new_session()  # A stale view cannot send into the replacement session.
        window._send_question_answers()
        assert window._question_panel is None and not service.store.messages()
    finally:
        window.close()
        service.shutdown()
        app.processEvents()


def test_pre_admission_failure_keeps_answers_and_attachments(app, tmp_path, monkeypatch):
    service = ConversationService(Replies([handoff(), "Done"]), ConversationStore(tmp_path / "chat.json"))
    service.run("Ask questions first")
    window = MainWindow(service, "SYNTHETIC")
    monkeypatch.setattr(window.notifications, "notify", lambda *_: None)
    window.show()
    try:
        window.input.setPlainText("Unsent draft")
        source = tmp_path / "draft.txt"
        source.write_text("Unsent attachment", encoding="utf-8")
        window.attachment_tray.add_paths([source])
        wait_for(lambda: window.attachment_tray.ready)
        references = window.attachment_tray.references
        panel = window._question_panel
        fill(panel)
        expected = panel.answer_text()
        original = service.run
        def reject(*args, **kwargs):
            raise RuntimeError("Synthetic admission rejection")
        monkeypatch.setattr(service, "run", reject)
        panel.send.click()
        wait_for(lambda: window.thread is None)
        assert window._question_panel is panel and panel.answer_text() == expected and panel.send.isEnabled()
        assert window.input.toPlainText() == "Unsent draft" and window.attachment_tray.references == references
        monkeypatch.setattr(service, "run", original)
        panel.send.click()
        wait_for(lambda: window.thread is None)
        assert window._question_panel is None and service.store.messages()[-2]["content"] == expected
        assert window.attachment_tray.references == references and window.input.toPlainText() == "Unsent draft"
    finally:
        window.close()
        service.shutdown()
        app.processEvents()


def test_answering_in_chat_restores_rejected_draft_and_consumes_form_on_success(app, tmp_path, monkeypatch):
    service = ConversationService(Replies([handoff(), "Done"]), ConversationStore(tmp_path / "chat.json"))
    service.run("Ask questions first")
    window = MainWindow(service, "SYNTHETIC")
    monkeypatch.setattr(window.notifications, "notify", lambda *_: None)
    window.show()
    try:
        window._answer_in_chat()
        window.input.setPlainText("Photography for prospective clients; minimal style.")
        original = service.run
        monkeypatch.setattr(service, "run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Synthetic rejection")))
        window.submit()
        wait_for(lambda: window.thread is None)
        assert window.input.toPlainText() == "Photography for prospective clients; minimal style."
        assert window._question_panel is not None and not window._questions_visible()
        monkeypatch.setattr(service, "run", original)
        window.submit()
        wait_for(lambda: window.thread is None)
        assert window._question_panel is None and window.questions_back.isHidden()
        assert service.store.messages()[-1]["content"] == "Done"
    finally:
        window.close()
        service.shutdown()
        app.processEvents()


@pytest.mark.parametrize("backend", ["python", "native", "compatible", "responses"])
def test_actual_adapter_final_text_supports_questions_without_new_tool_schemas(tmp_path, monkeypatch, backend):
    bodies = []
    replies = iter([handoff(), "Thanks for the answers."])
    if backend == "python":
        from app.inference.llama_backend import LlamaCppInferenceEngine
        engine = object.__new__(LlamaCppInferenceEngine)
        engine.model = SimpleNamespace(create_chat_completion=lambda **body: (
            bodies.append(body) or {"choices": [{"message": {"content": next(replies)}}]}), close=lambda: None)
        engine.config = SimpleNamespace(temperature=.1, max_tokens=1024)
    elif backend == "native":
        from tests.test_llama_server_inference import completion, scripted_engine
        engine, bodies = scripted_engine([completion({"role": "assistant", "content": reply}) for reply in replies])
        monkeypatch.setattr(engine, "close", lambda: None)
    elif backend == "compatible":
        from app.inference.cloud_backend import OpenAICompatibleInferenceEngine
        from tests.test_cloud_inference import cloud_config
        engine = OpenAICompatibleInferenceEngine(cloud_config(), api_key="synthetic-never-live")
        monkeypatch.setattr(engine, "_request_completion", lambda body, **kwargs: (
            bodies.append(body) or {"choices": [{"message": {"content": next(replies)}}]}))
    else:
        from tests.test_openai_tools import scripted_sdk
        from tests.test_openai_phase1 import response
        next_response = response("Thanks for the answers.", id="resp_second")
        next_response["output"][0]["id"] = "msg_second"
        engine, client, bodies, _ = scripted_sdk(monkeypatch, [response(handoff()), next_response])
    if backend in {"python", "native"}:
        engine.context_length, engine.max_response_tokens = 16384, 1024
        monkeypatch.setattr(engine, "count_message_tokens", lambda messages: InferenceEngine.count_message_tokens(engine, messages))
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    try:
        result = service.run("Ask me about a portfolio")
        assert result.question_batch == batch() and QUESTION_MARKER not in result
        assert service.store.visible_messages()[-1].question_batch == batch()
        assert "orsi_questions" in str(bodies[0])
        assert "tools" not in bodies[0] or not bodies[0]["tools"]
        answers = format_answers(batch(), {"work": ("Photography",), "style": ("Minimal",),
                                           "features": (), "audience": ("Clients",)})
        assert service.run(answers) == "Thanks for the answers."
        messages = bodies[-1]["input" if backend == "responses" else "messages"]
        assert len([m for m in messages if m.get("role") == "assistant"]) == 1
        assert service.store.messages()[-2]["content"] == answers
    finally:
        service.shutdown()
    if backend == "responses":
        assert client.is_closed() and engine._runner is None
