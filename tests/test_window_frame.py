from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.window_frame import resize_edges


class WindowFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_caption_excludes_window_and_toolbar_controls(self):
        window = MainWindow(None, "TEST")
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        self.assertTrue(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(window._window_frame.is_caption(QPoint(120, 20)))
        self.assertFalse(window._window_frame.is_caption(QPoint(500, 100)))
        for button in (window.window_controls.minimize, window.window_controls.maximize,
                       window.window_controls.close_button):
            center = button.mapTo(window, button.rect().center())
            self.assertFalse(window._window_frame.is_caption(center))
        self.assertFalse(window._window_frame.is_caption(
            window.settings_button.mapTo(window, window.settings_button.rect().center())))
        self.assertLess(window.context_window.mapTo(window, window.context_window.rect().topRight()).x(),
                        window.window_controls.x())

    def test_all_resize_edges_and_maximized_exclusion(self):
        size = QSize(800, 600)
        cases = [(QPoint(1, 1), Qt.Edge.LeftEdge | Qt.Edge.TopEdge),
                 (QPoint(798, 1), Qt.Edge.RightEdge | Qt.Edge.TopEdge),
                 (QPoint(1, 598), Qt.Edge.LeftEdge | Qt.Edge.BottomEdge),
                 (QPoint(798, 598), Qt.Edge.RightEdge | Qt.Edge.BottomEdge),
                 (QPoint(1, 300), Qt.Edge.LeftEdge), (QPoint(798, 300), Qt.Edge.RightEdge),
                 (QPoint(400, 1), Qt.Edge.TopEdge), (QPoint(400, 598), Qt.Edge.BottomEdge)]
        for point, expected in cases:
            with self.subTest(point=point):
                self.assertEqual(resize_edges(point, size), expected)
                self.assertFalse(resize_edges(point, size, maximized=True))
        self.assertFalse(resize_edges(QPoint(400, 300), size))

    def test_controls_restore_geometry_minimize_and_use_existing_shutdown(self):
        class Service:
            shutdown_count = 0

            def shutdown(self):
                self.shutdown_count += 1

        class Inference:
            available_modes = ("local",)
            mode = "local"
            context_length = 0
            close_count = 0

            def close(self):
                self.close_count += 1

        service, inference = Service(), Inference()
        window = MainWindow(service, "TEST", inference=inference)
        window.show()
        self.app.processEvents()
        original = window.geometry()
        window.window_controls.maximize.click()
        self.app.processEvents()
        self.assertTrue(window.isMaximized())
        self.assertEqual(window.window_controls.maximize.accessibleName(), "Restore")
        window.window_controls.maximize.click()
        self.app.processEvents()
        self.assertFalse(window.isMaximized())
        self.assertEqual(window.geometry(), original)
        window.window_controls.minimize.click()
        self.app.processEvents()
        self.assertTrue(window.isMinimized())
        window.showNormal()
        window.window_controls.close_button.click()
        self.app.processEvents()
        self.assertFalse(window.isVisible())
        self.assertEqual(service.shutdown_count, 1)
        self.assertEqual(inference.close_count, 1)
