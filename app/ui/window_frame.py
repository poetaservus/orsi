"""Quiet client-side controls with native Windows moving and sizing."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QApplication, QHBoxLayout, QPushButton, QWidget


CAPTION_HEIGHT = 34
RESIZE_MARGIN = 7


def resize_edges(position: QPoint, size, maximized: bool = False) -> Qt.Edges:
    edges = Qt.Edge(0)
    if maximized:
        return edges
    if position.x() < RESIZE_MARGIN:
        edges |= Qt.Edge.LeftEdge
    elif position.x() >= size.width() - RESIZE_MARGIN:
        edges |= Qt.Edge.RightEdge
    if position.y() < RESIZE_MARGIN:
        edges |= Qt.Edge.TopEdge
    elif position.y() >= size.height() - RESIZE_MARGIN:
        edges |= Qt.Edge.BottomEdge
    return edges


class WindowButton(QPushButton):
    def __init__(self, action: str, window, parent):
        super().__init__(parent)
        self.action = action
        self.window = window
        self.setObjectName("windowControl")
        self.setFixedSize(34, 28)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName(action.capitalize())
        self.setToolTip(action.capitalize())

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#cbd0da"), 1.2))
        painter.translate((self.width() - 10) / 2, (self.height() - 10) / 2)
        if self.action == "minimize":
            painter.drawLine(0, 7, 10, 7)
        elif self.action == "close":
            painter.drawLine(1, 1, 9, 9)
            painter.drawLine(9, 1, 1, 9)
        elif self.window.isMaximized():
            painter.drawLine(3, 0, 10, 0)
            painter.drawLine(10, 0, 10, 7)
            painter.drawLine(10, 7, 8, 7)
            painter.drawRect(0, 3, 7, 7)
        else:
            painter.drawRect(0, 0, 10, 10)


class WindowControls(QWidget):
    def __init__(self, window, parent):
        super().__init__(parent)
        self.window = window
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.minimize = WindowButton("minimize", window, self)
        self.maximize = WindowButton("maximize", window, self)
        self.close_button = WindowButton("close", window, self)
        for button in (self.minimize, self.maximize, self.close_button):
            layout.addWidget(button)
        self.setFixedSize(106, 28)
        self.setStyleSheet("""
            QPushButton#windowControl { background: transparent; border: none; border-radius: 5px; }
            QPushButton#windowControl:hover { background: rgba(255,255,255,18); }
            QPushButton#windowControl:pressed { background: rgba(255,255,255,30); }
        """)
        self.minimize.clicked.connect(window.showMinimized)
        self.maximize.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(window.close)

    def toggle_maximized(self):
        frame = self.window._window_frame
        if frame.enabled:
            frame.api.ShowWindow(frame.hwnd, 9 if frame.api.IsZoomed(frame.hwnd) else 3)
            return
        if self.window.isMaximized():
            self.window.showNormal()
        else:
            self.window.showMaximized()

    def refresh(self):
        name = "Restore" if self.window.isMaximized() else "Maximize"
        self.maximize.setAccessibleName(name)
        self.maximize.setToolTip(name)
        self.maximize.update()


class DragStrip(QWidget):
    """Qt's native window-manager operation also supports non-Windows platforms."""
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().window_controls.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class WindowsFrame:
    """Keep native resize/Snap styles, while allocating the frame to our client area.

    This helper is inactive for offscreen Qt tests and non-Windows platforms.
    Windows receives HTCAPTION/edge hits, so its own move/resize loop handles
    snapping, dragging out of maximization, double-click and the system menu.
    """
    def __init__(self, window):
        self.window = window
        self.hwnd = None
        self.enabled = sys.platform == "win32" and QApplication.platformName() == "windows"
        if not self.enabled:
            return
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        pointer = ctypes.c_ssize_t
        self.get_style = getattr(self.api, "GetWindowLongPtrW", self.api.GetWindowLongW)
        self.get_style.argtypes = [wintypes.HWND, ctypes.c_int]
        self.get_style.restype = pointer
        self.set_style = getattr(self.api, "SetWindowLongPtrW", self.api.SetWindowLongW)
        self.set_style.argtypes = [wintypes.HWND, ctypes.c_int, pointer]
        self.set_style.restype = pointer
        self.api.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.api.SetWindowPos.restype = wintypes.BOOL
        self.api.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self.api.IsZoomed.argtypes = [wintypes.HWND]
        self.api.IsZoomed.restype = wintypes.BOOL
        self.api.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.ShowWindow.restype = wintypes.BOOL
        self.api.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        self.api.MonitorFromWindow.restype = wintypes.HANDLE
        self.api.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        self.api.GetMonitorInfoW.restype = wintypes.BOOL

    def configure(self):
        if not self.enabled:
            return
        hwnd = int(self.window.winId())
        if self.hwnd == hwnd:
            return
        self.hwnd = hwnd
        # WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX.
        # WM_NCCALCSIZE removes their visible frame, retaining native behavior.
        self.set_style(hwnd, -16, self.get_style(hwnd, -16) | 0x00CF0000)
        self.api.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0037)  # FRAMECHANGED, NOMOVE/SIZE/ZORDER/ACTIVATE

    def handle(self, message):
        if not self.enabled:
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0083:  # WM_NCCALCSIZE; first RECT for either parameter form
            if self.api.IsZoomed(msg.hWnd):
                class MonitorInfo(ctypes.Structure):
                    _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                                ("work", wintypes.RECT), ("flags", wintypes.DWORD)]
                info = MonitorInfo()
                info.size = ctypes.sizeof(info)
                monitor = self.api.MonitorFromWindow(msg.hWnd, 2)
                if self.api.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    rect = wintypes.RECT.from_address(msg.lParam)
                    rect.left, rect.top = info.work.left, info.work.top
                    rect.right, rect.bottom = info.work.right, info.work.bottom
            return True, 0
        if msg.message == 0x0084:  # WM_NCHITTEST; signed coordinates also support left-hand monitors
            point = wintypes.POINT(ctypes.c_short(msg.lParam & 0xffff).value,
                                   ctypes.c_short((msg.lParam >> 16) & 0xffff).value)
            if not self.api.ScreenToClient(msg.hWnd, ctypes.byref(point)):
                return False, 0
            ratio = self.window.devicePixelRatioF()
            pos = QPoint(round(point.x / ratio), round(point.y / ratio))
            edges = resize_edges(pos, self.window.size(), self.window.isMaximized())
            hits = {
                Qt.Edge.LeftEdge: 10, Qt.Edge.RightEdge: 11, Qt.Edge.TopEdge: 12,
                Qt.Edge.TopEdge | Qt.Edge.LeftEdge: 13, Qt.Edge.TopEdge | Qt.Edge.RightEdge: 14,
                Qt.Edge.BottomEdge: 15, Qt.Edge.BottomEdge | Qt.Edge.LeftEdge: 16,
                Qt.Edge.BottomEdge | Qt.Edge.RightEdge: 17,
            }
            if edges:
                return True, hits[edges]
            if self.is_caption(pos):
                return True, 2  # HTCAPTION
            return True, 1  # HTCLIENT
        return False, 0

    def is_caption(self, pos):
        if not (0 <= pos.y() < CAPTION_HEIGHT and 0 <= pos.x() < self.window.width()):
            return False
        child = self.window.childAt(pos)
        while child is not None and child is not self.window:
            if isinstance(child, QAbstractButton) or child in (
                getattr(self.window, "context_window", None),
                getattr(self.window, "window_controls", None),
            ):
                return False
            child = child.parentWidget()
        # The outer edge band belongs to native sizing.
        return pos.y() >= RESIZE_MARGIN
