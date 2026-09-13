from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QWidget

    from app.ui.chat import ChatView
    from app.ui.main_window import MainWindow
    from app.main import request_full_local_read_acknowledgement
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
        self.assertEqual(window.input.placeholderText(), "Ask O.R.S.I.")
        self.assertEqual(window.activity.text(), "Ready · Chat only")
        self.assertFalse(hasattr(window, "undo"))
        visible_text = [label.text() for label in window.findChildren(QLabel)]
        self.assertNotIn("HOSTNAME-SHOULD-NOT-APPEAR", visible_text)
        window.close()

    def test_context_window_bar_is_visible_on_chat_surface_and_shows_capacity(self):
        class FakeInference:
            available_modes = ("local",)
            mode = "local"
            context_length = 32768

            @staticmethod
            def consume_notice():
                return None

        window = MainWindow(None, "TEST-HOST", inference=FakeInference())

        self.assertEqual(window.context_window.title.text(), "Context Window")
        self.assertEqual(window.context_window.size.text(), "32,768")
        self.assertEqual(
            window.context_window.status.text(),
            "O.R.S.I. v0.4.0-dev // Local // Context Window: 0%",
        )
        self.assertEqual(window.context_window.bar.maximum(), 32768)
        self.assertIs(window.context_window.parentWidget(), window.topbar)
        self.assertFalse(window.context_window.isHidden())
        window.settings_button.click()
        self.assertFalse(window.settings_panel.isHidden())
        self.assertIs(window.context_window.parentWidget(), window.topbar)
        window.close()

    def test_context_window_bar_uses_conversation_estimate(self):
        class FakeService:
            @staticmethod
            def estimated_context_tokens():
                return 1200

        class FakeInference:
            available_modes = ("local",)
            mode = "local"
            context_length = 8192

            @staticmethod
            def consume_notice():
                return None

        window = MainWindow(FakeService(), "TEST-HOST", inference=FakeInference())
        self.assertEqual(window.context_window.bar.value(), 1200)
        self.assertIn("1,200 of 8,192 tokens", window.context_window.toolTip())
        self.assertIn("Context Window: 15%", window.context_window.status.text())
        window.close()

    def test_new_session_button_clears_chat_context_and_persisted_session(self):
        class FakeService:
            used = 1200
            reset_count = 0

            def estimated_context_tokens(self):
                return self.used

            def new_session(self):
                self.reset_count += 1
                self.used = 0

        class FakeInference:
            available_modes = ("local",)
            mode = "local"
            context_length = 8192

            @staticmethod
            def consume_notice():
                return None

        service = FakeService()
        window = MainWindow(service, "TEST-HOST", inference=FakeInference())
        window.chat.add_message("User", "Old conversation")

        window.new_session_button.click()
        QApplication.processEvents()

        self.assertEqual(service.reset_count, 1)
        self.assertEqual(window.chat._messages, [])
        self.assertEqual(window.context_window.bar.value(), 0)
        self.assertEqual(window.new_session_button.accessibleName(), "New session")
        self.assertEqual(window.settings_button.accessibleName(), "Settings")
        self.assertTrue(window.settings_button.isEnabled())
        window.close()

    def test_composer_preserves_large_multiline_pastes_and_shift_enter(self):
        window = MainWindow(None, "TEST-HOST")
        self.assertEqual(window.composer.height(), 74)
        self.assertEqual(window.input.height(), 58)
        self.assertEqual(window.send.size().width(), 46)
        self.assertIs(window.model_selector.parentWidget(), window.settings_panel)
        pasted = ("A full paragraph.\n\n" * 3000).rstrip()
        window.input.setPlainText(pasted)

        self.assertEqual(window.input.toPlainText(), pasted)
        self.assertGreater(len(window.input.toPlainText()), 32767)

        window.input.clear()
        QTest.keyClick(
            window.input,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.ShiftModifier,
        )
        self.assertEqual(window.input.toPlainText(), "\n")
        window.close()

    def test_reference_layout_matches_mockup_geometry(self):
        window = MainWindow(None, "TEST-HOST")
        window.resize(1920, 1080)
        window.show()
        QApplication.processEvents()

        self.assertEqual(window.topbar.height(), 68)
        self.assertEqual(window.composer.width(), 1040)
        self.assertEqual(window.composer.height(), 74)
        self.assertEqual(window.composer.y(), window._content.height() - 118)
        self.assertLessEqual(abs(window.composer.x() - 440), 1)
        self.assertLessEqual(
            abs(window._content.width() - window.composer.geometry().right() - 1 - 440),
            1,
        )
        middle_panel = window._content.middle_panel_rect()
        self.assertFalse(window._content._background.isNull())
        self.assertEqual(middle_panel.width(), 1120)
        self.assertEqual(middle_panel.x(), 400)
        self.assertEqual(
            window.topbar.width() - window.context_window.geometry().right() - 1,
            22,
        )
        self.assertIn("O.R.S.I. v0.4.0-dev // Local", window.context_window.status.text())
        self.assertTrue(window.settings_panel.isHidden())
        window.close()

    def test_compact_window_reserves_a_non_overlapping_context_header(self):
        window = MainWindow(None, "TEST-HOST")
        window.resize(1280, 700)
        window.show()
        QApplication.processEvents()

        self.assertEqual(window._content_layout.contentsMargins().top(), 0)
        self.assertEqual(window.topbar.height(), 68)
        self.assertLess(window.context_window.geometry().bottom(), window.topbar.height())
        middle_panel = window._content.middle_panel_rect()
        panel_right_space = window._content.width() - middle_panel.right() - 1
        self.assertLessEqual(abs(middle_panel.x() - panel_right_space), 1)
        composer_right_space = window._content.width() - window.composer.geometry().right() - 1
        self.assertLessEqual(abs(window.composer.x() - composer_right_space), 1)
        window.chat.add_message("Agent", "A compact response")
        QApplication.processEvents()
        response_left = window.chat._messages[0].mapTo(window._content, QPoint(0, 0)).x()
        self.assertGreaterEqual(response_left, middle_panel.x())
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

    def test_agent_status_and_cloud_disclosure_name_the_metadata_boundary(self):
        class FakeService:
            agent_enabled = True
            agent_error = None
            shutdown_called = False

            @staticmethod
            def estimated_context_tokens():
                return 0

            def shutdown(self):
                self.shutdown_called = True

        class FakeInference:
            available_modes = ("local", "cloud")
            mode = "cloud"
            context_length = 8192
            cloud_has_api_key = True
            cloud_provider_name = "Test Cloud"

            @staticmethod
            def consume_notice():
                return None

        service = FakeService()
        window = MainWindow(service, "TEST-HOST", inference=FakeInference())

        self.assertEqual(
            window.activity.text(),
            "Ready · Cloud · Agent · Portable-root read · Metadata only",
        )
        disclosure = window._cloud_privacy_message()
        self.assertIn("conversation and any filesystem.stat metadata results", disclosure)
        self.assertIn("cannot read file content", disclosure)
        self.assertIn("cannot", disclosure)

        window.close()
        self.assertTrue(service.shutdown_called)

    def test_full_local_status_and_cloud_disclosure_are_continuously_visible(self):
        class FakeService:
            agent_enabled = True
            agent_error = None
            host_read_scope = "full_local"

            @staticmethod
            def estimated_context_tokens():
                return 0

        class FakeInference:
            available_modes = ("local", "cloud")
            mode = "local"
            context_length = 8192
            cloud_has_api_key = True
            cloud_provider_name = "Test Cloud"

            @staticmethod
            def consume_notice():
                return None

        window = MainWindow(FakeService(), "TEST-HOST", inference=FakeInference())

        self.assertEqual(
            window.activity.text(),
            "Ready · Local · Agent · Full local read · Metadata only",
        )
        disclosure = window._cloud_privacy_message()
        self.assertIn("enabled local filesystem drives", disclosure)
        self.assertIn("current Windows account", disclosure)
        self.assertIn("cannot read file content", disclosure)
        window.close()

    def test_full_local_read_acknowledgement_is_explicit_and_defaults_to_no(self):
        with patch(
            "PySide6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ) as question:
            self.assertTrue(request_full_local_read_acknowledgement())

        args = question.call_args.args
        self.assertEqual(args[1], "Enable Full local read access?")
        self.assertIn("current Windows account", args[2])
        self.assertIn("metadata only", args[2])
        self.assertEqual(args[-1], QMessageBox.StandardButton.No)

        with patch(
            "PySide6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ):
            self.assertFalse(request_full_local_read_acknowledgement())

    def test_listing_status_warning_and_cloud_disclosure_name_directory_data(self):
        class FakeService:
            agent_enabled = True
            agent_error = None
            host_read_scope = "full_local"
            agent_capabilities = ("filesystem.list", "filesystem.stat")

            @staticmethod
            def estimated_context_tokens():
                return 0

        class FakeInference:
            available_modes = ("local", "cloud")
            mode = "local"
            context_length = 8192
            cloud_has_api_key = True
            cloud_provider_name = "Test Cloud"

            @staticmethod
            def consume_notice():
                return None

        window = MainWindow(FakeService(), "TEST-HOST", inference=FakeInference())
        self.assertEqual(
            window.activity.text(),
            "Ready · Local · Agent · Full local read · Metadata + listing",
        )
        disclosure = window._cloud_privacy_message()
        self.assertIn("filesystem.list directory names and types", disclosure)
        self.assertIn("Directory and file names may be confidential", disclosure)
        self.assertIn("cannot read file content", disclosure)
        window.close()

        with patch(
            "PySide6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ) as question:
            self.assertTrue(
                request_full_local_read_acknowledgement(
                    filesystem_list_enabled=True
                )
            )
        warning = question.call_args.args[2]
        self.assertIn("bounded names and types", warning)
        self.assertIn("cannot read file content", warning)

    def test_find_status_and_cloud_disclosure_name_exact_lookup(self):
        class FakeService:
            agent_enabled = True
            agent_error = None
            host_read_scope = "full_local"
            agent_capabilities = ("filesystem.find", "filesystem.stat")

            @staticmethod
            def estimated_context_tokens():
                return 0

        class FakeInference:
            available_modes = ("local", "cloud")
            mode = "local"
            context_length = 8192
            cloud_has_api_key = True
            cloud_provider_name = "Test Cloud"

            @staticmethod
            def consume_notice():
                return None

        window = MainWindow(FakeService(), "TEST-HOST", inference=FakeInference())
        self.assertEqual(
            window.activity.text(),
            "Ready · Local · Agent · Full local read · Metadata + find",
        )
        disclosure = window._cloud_privacy_message()
        self.assertIn("filesystem.find matching file and folder names", disclosure)
        self.assertIn("resolve exact file or folder names", disclosure)
        self.assertIn("Directory and file names may be confidential", disclosure)
        self.assertIn("cannot read file content", disclosure)
        window.close()

    def test_text_read_status_warning_and_cloud_disclosure_name_file_content(self):
        class FakeService:
            agent_enabled = True
            agent_error = None
            host_read_scope = "full_local"
            agent_capabilities = (
                "filesystem.list",
                "filesystem.read_text",
                "filesystem.stat",
            )

            @staticmethod
            def estimated_context_tokens():
                return 0

        class FakeInference:
            available_modes = ("local", "cloud")
            mode = "local"
            context_length = 8192
            cloud_has_api_key = True
            cloud_provider_name = "Test Cloud"

            @staticmethod
            def consume_notice():
                return None

        window = MainWindow(FakeService(), "TEST-HOST", inference=FakeInference())
        self.assertEqual(
            window.activity.text(),
            "Ready · Local · Agent · Full local read · Metadata + listing + text",
        )
        disclosure = window._cloud_privacy_message()
        self.assertIn("filesystem.read_text file content", disclosure)
        self.assertIn("read bounded text", disclosure)
        self.assertIn("File content and directory or file names may be confidential", disclosure)
        window.close()

        with patch(
            "PySide6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ) as question:
            self.assertTrue(
                request_full_local_read_acknowledgement(
                    filesystem_list_enabled=True,
                    filesystem_read_text_enabled=True,
                )
            )
        warning = question.call_args.args[2]
        self.assertIn("bounded content", warning)
        self.assertNotIn("cannot read file content", warning)

    def test_search_status_warning_and_cloud_disclosure_name_matching_snippets(self):
        class FakeService:
            agent_enabled = True
            agent_error = None
            host_read_scope = "full_local"
            agent_capabilities = (
                "filesystem.list",
                "filesystem.read_text",
                "filesystem.search",
                "filesystem.stat",
            )

            @staticmethod
            def estimated_context_tokens():
                return 0

        class FakeInference:
            available_modes = ("local", "cloud")
            mode = "local"
            context_length = 8192
            cloud_has_api_key = True
            cloud_provider_name = "Test Cloud"

            @staticmethod
            def consume_notice():
                return None

        window = MainWindow(FakeService(), "TEST-HOST", inference=FakeInference())
        self.assertEqual(
            window.activity.text(),
            "Ready · Local · Agent · Full local read · Metadata + listing + text + search",
        )
        disclosure = window._cloud_privacy_message()
        self.assertIn("filesystem.search matching snippets", disclosure)
        self.assertIn("search bounded text snippets", disclosure)
        self.assertIn("File content, snippets, and directory or file names may be confidential", disclosure)
        window.close()

        with patch(
            "PySide6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ) as question:
            self.assertTrue(
                request_full_local_read_acknowledgement(
                    filesystem_list_enabled=True,
                    filesystem_read_text_enabled=True,
                    filesystem_search_enabled=True,
                )
            )
        warning = question.call_args.args[2]
        self.assertIn("search for literal text snippets", warning)
        self.assertIn("background-indexing", warning)

    def test_agent_start_failure_falls_back_visibly_to_chat_only(self):
        class FakeService:
            agent_enabled = False
            agent_error = "Agent mode could not start safely. Chat-only mode remains available."

            @staticmethod
            def estimated_context_tokens():
                return 0

        class FakeInference:
            available_modes = ("local",)
            mode = "local"
            context_length = 8192

            @staticmethod
            def consume_notice():
                return None

        window = MainWindow(FakeService(), "TEST-HOST", inference=FakeInference())

        self.assertEqual(window.activity.text(), "Agent unavailable · Chat only")
        self.assertEqual(
            window.chat._messages[0].label.text(),
            "Agent mode could not start safely. Chat-only mode remains available.",
        )
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

    def test_assistant_code_uses_readonly_box_and_working_copy_button(self):
        chat = ChatView()
        chat.add_message(
            "Agent",
            "Use this:\n\n```python\nprint('hello')\n```\n\nThen run it.",
        )
        message = chat._messages[0]

        self.assertEqual(len(message._code_blocks), 1)
        block = message._code_blocks[0]
        self.assertEqual(block.language.text(), "python")
        self.assertEqual(block.editor.toPlainText(), "print('hello')")
        self.assertTrue(block.editor.isReadOnly())

        block.copy_button.click()

        self.assertEqual(QApplication.clipboard().text(), "print('hello')")
        self.assertEqual(block.copy_button.text(), "Copied")
        self.assertEqual(
            [label.text() for label in message._text_labels],
            ["Use this:", "Then run it."],
        )
        chat.close()

    def test_user_fenced_text_remains_a_plain_message(self):
        chat = ChatView()
        content = "```python\nprint('not generated')\n```"
        chat.add_message("User", content)

        self.assertEqual(chat._messages[0]._code_blocks, [])
        self.assertEqual(chat._messages[0].label.text(), content)
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
