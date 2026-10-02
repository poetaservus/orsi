"""Isolated Windows/Qt frame check; never opens a model or a saved conversation."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "windows"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def check():
    app = QApplication([])
    window = MainWindow(None, "FRAME-CHECK")
    window.resize(900, 640)  # Fits the monitor work area at both tested scales.
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.show()
    QTest.qWait(100)
    frame = window._window_frame
    api, hwnd = frame.api, int(window.winId())
    api.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    api.SendMessageW.restype = ctypes.c_ssize_t
    api.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    api.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    api.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]

    def rectangles():
        outer, client = wintypes.RECT(), wintypes.RECT()
        assert api.GetWindowRect(hwnd, ctypes.byref(outer))
        assert api.GetClientRect(hwnd, ctypes.byref(client))
        return outer, client

    def hit(point):
        ratio = window.devicePixelRatioF()
        native = wintypes.POINT(round(point.x() * ratio), round(point.y() * ratio))
        assert api.ClientToScreen(hwnd, ctypes.byref(native))
        packed = (native.x & 0xffff) | ((native.y & 0xffff) << 16)
        return api.SendMessageW(hwnd, 0x0084, 0, packed)

    try:
        assert frame.enabled
        style = frame.get_style(hwnd, -16)
        assert style & 0x00CF0000 == 0x00CF0000, hex(style)
        outer, client = rectangles()
        assert outer.right - outer.left == client.right, (outer.right - outer.left, client.right)
        assert outer.bottom - outer.top == client.bottom, (outer.bottom - outer.top, client.bottom)
        assert hit(QPoint(120, 20)) == 2
        for point, expected in [(QPoint(1, 1), 13), (QPoint(window.width()-2, 1), 14),
            (QPoint(1, window.height()-2), 16), (QPoint(window.width()-2, window.height()-2), 17)]:
            assert hit(point) == expected, (point, hit(point), expected)
        for button in (window.window_controls.minimize, window.window_controls.maximize,
                       window.window_controls.close_button):
            assert hit(button.mapTo(window, button.rect().center())) == 1
        for button in (window.new_session_button, window.settings_button):
            assert hit(button.mapTo(window, button.rect().center())) == 1
        assert hit(window.context_window.mapTo(window, window.context_window.rect().center())) == 1
        assert window.app_controls.pos() == QPoint(8, 8)
        assert abs(window.context_window.geometry().center().x() - window.rect().center().x()) <= 1
        original = window.geometry()
        # Native caption double-click, rather than merely toggling the Qt state.
        api.SendMessageW(hwnd, 0x00A3, 2, 0)
        QTest.qWait(100)
        assert window.isMaximized()
        assert window.window_controls.maximize.accessibleName() == "Restore"
        class MonitorInfo(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                        ("work", wintypes.RECT), ("flags", wintypes.DWORD)]
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        assert api.GetMonitorInfoW(api.MonitorFromWindow(hwnd, 2), ctypes.byref(info))
        _, client = rectangles()
        origin = wintypes.POINT(0, 0)
        assert api.ClientToScreen(hwnd, ctypes.byref(origin))
        assert (origin.x, origin.y, client.right, client.bottom) == (
            info.work.left, info.work.top, info.work.right-info.work.left, info.work.bottom-info.work.top), (
            origin.x, origin.y, client.right, client.bottom,
            info.work.left, info.work.top, info.work.right, info.work.bottom)
        assert hit(QPoint(1, window.height()-2)) == 1  # no resizing a maximized window
        window.window_controls.maximize.click()
        QTest.qWait(100)
        assert window.geometry() == original, (window.geometry(), original,
            window.normalGeometry(), window.isMaximized(), api.IsZoomed(hwnd))
        window.window_controls.maximize.click()
        QTest.qWait(100)
        assert window.isMaximized() and api.IsZoomed(hwnd)
        window.window_controls.maximize.click()
        QTest.qWait(100)
        assert not window.isMaximized() and not api.IsZoomed(hwnd)
        assert window.geometry() == original
        window.window_controls.maximize.click()
        QTest.qWait(100)
        window.window_controls.minimize.click()
        QTest.qWait(100)
        assert window.isMinimized()
        api.SendMessageW(hwnd, 0x0112, 0xF120, 0)  # SC_RESTORE after minimizing a maximized window
        QTest.qWait(100)
        assert window.isMaximized() and not window.isMinimized()
        window.window_controls.maximize.click()
        QTest.qWait(100)
        assert window.geometry() == original
        window.window_controls.minimize.click()
        app.processEvents()
        assert window.isMinimized()
        window.showNormal()
        QTest.qWait(100)
        assert frame.get_style(hwnd, -16) & 0x00CF0000 == 0x00CF0000
        if "--preview" in sys.argv:
            window.grab().save(str(Path("state/frameless-window-preview.png").resolve()))
        # Native system-menu close uses the same orderly Qt close event.
        api.SendMessageW(hwnd, 0x0112, 0xF060, 0)
        app.processEvents()
        assert not window.isVisible()
        print(json.dumps({"platform": app.platformName(), "scale": window.devicePixelRatioF(),
            "native_frame_removed": True, "resize_hits": True, "caption_double_click": True,
            "maximize_work_area": True, "restore_minimize_close": True, "native_snap_styles": True}))
    finally:
        window.close()


if __name__ == "__main__":
    check()
