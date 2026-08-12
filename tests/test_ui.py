from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

    from app.ui.chat import ChatView
    from app.ui.main_window import MainWindow
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_window_is_explicitly_chat_only_and_has_no_action_controls(self):
        window = MainWindow(None, "HOSTNAME-SHOULD-NOT-APPEAR")
        self.assertEqual(window.windowTitle(), "O.R.S.I")
        self.assertEqual(window.input.placeholderText(), "Ask O.R.S.I")
        self.assertEqual(window.activity.text(), "Ready · Chat only")
        self.assertFalse(hasattr(window, "undo"))
        visible_text = [label.text() for label in window.findChildren(QLabel)]
        self.assertNotIn("HOSTNAME-SHOULD-NOT-APPEAR", visible_text)
        window.close()

    def test_cloud_selector_warns_and_keeps_key_in_memory(self):
        class FakeInference:
            available_modes = ("local", "cloud")
            mode = "local"
            cloud_has_api_key = False
            cloud_provider_name = "Test Cloud"

            def set_mode(self, mode):
                self.mode = mode

            def set_cloud_api_key(self, key):
                self.cloud_has_api_key = bool(key)
                self.received_key = key

            @staticmethod
            def consume_notice():
                return None

        inference = FakeInference()
        window = MainWindow(None, "TEST-HOST", inference=inference)
        cloud_index = window.model_selector.findData("cloud")

        with patch(
            "app.ui.main_window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch(
            "app.ui.main_window.QInputDialog.getText",
            return_value=("session-only-key", True),
        ):
            window.model_selector.setCurrentIndex(cloud_index)

        self.assertEqual(inference.mode, "cloud")
        self.assertEqual(inference.received_key, "session-only-key")
        self.assertEqual(window.activity.text(), "Ready · Cloud · Chat only")
        window.close()

    def test_messages_have_no_name_tags_and_use_requested_sides(self):
        chat = ChatView()
        chat.add_message("User", "A user message")
        chat.add_message("Agent", "An O.R.S.I reply")

        self.assertEqual(chat._messages[0].objectName(), "userMessage")
        self.assertEqual(chat._messages[1].objectName(), "orsiMessage")
        self.assertEqual(chat._messages[0].label.text(), "A user message")
        self.assertEqual(chat._messages[1].label.text(), "An O.R.S.I reply")
        chat.close()

    def test_thinking_dots_start_and_stop(self):
        chat = ChatView()
        chat.set_thinking(True)
        self.assertTrue(chat.thinking_dots.is_running)
        chat.set_thinking(False)
        self.assertFalse(chat.thinking_dots.is_running)
        self.assertTrue(chat.thinking_dots.isHidden())
        chat.close()

    def test_worker_renders_plain_conversation_reply(self):
        class FakeService:
            @staticmethod
            def run(message, activity):
                activity("Thinking...")
                return f"Reply to {message}"

        window = MainWindow(FakeService(), "TEST-HOST")
        window.input.setText("hello")
        window.submit()

        for _ in range(100):
            QApplication.processEvents()
            if window.thread is None:
                break
            QTest.qWait(10)

        self.assertIsNone(window.thread)
        self.assertEqual(window.chat._messages[1].label.text(), "Reply to hello")
        self.assertFalse(window.chat.thinking_dots.is_running)
        window.close()

    def test_stop_calls_conversation_cancellation(self):
        class FakeService:
            cancelled = False

            def cancel_current_task(self):
                self.cancelled = True

        service = FakeService()
        window = MainWindow(service, "TEST-HOST")
        window._set_busy(True)
        window.cancel_current_task()
        self.assertTrue(service.cancelled)
        self.assertFalse(window.stop.isEnabled())
        window._set_busy(False)
        window.close()


if __name__ == "__main__":
    unittest.main()
