"""Focused presentation checks; helpers receive no vault or provider data."""
import os
from pathlib import Path
import subprocess
import sys
from time import sleep

import pytest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from app.ui.profile_loading import ProfileLoadingCover
from app.ui.settings_motion import SettingsPageTransition


@pytest.fixture
def qt():
    return QApplication.instance() or QApplication([])


def test_page_transition_keeps_latest_navigation_and_clears_on_hide_resize(qt):
    stack = QStackedWidget()
    for name in ("First", "Second", "Third"):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QPushButton(name))
        stack.addWidget(page)
    transition = SettingsPageTransition(stack)
    try:
        stack.resize(400, 300)
        stack.show()
        qt.processEvents()
        stack.setCurrentIndex(1)
        assert stack.currentIndex() == 1 and transition.cover.isVisible()
        QTest.qWait(30)
        assert 0 < transition.cover.opacity < 1
        stack.setCurrentIndex(2)
        assert stack.currentIndex() == 2
        clicked = []
        button = stack.currentWidget().findChild(QPushButton)
        button.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert clicked == [True]
        QTest.qWait(140)
        assert transition.cover.isHidden() and transition.cover.picture.isNull()
        stack.setCurrentIndex(0)
        stack.resize(420, 320)
        qt.processEvents()
        assert transition.cover.picture.isNull()
        stack.setCurrentIndex(1)
        stack.hide()
        assert transition.cover.picture.isNull()
    finally:
        stack.close()


def helper_window(pid):
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL("user32", use_last_error=True)
    windows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    def visit(window, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == pid and user.IsWindowVisible(window):
            windows.append(window)
        return True
    user.EnumWindows(callback_type(visit), 0)
    assert len(windows) == 1
    user.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    assert user.GetWindowLongPtrW(windows[0], -20) & 0x8  # WS_EX_TOPMOST
    return windows[0]


@pytest.mark.skipif(os.name != "nt", reason="Native Windows loading presentation")
@pytest.mark.parametrize("gui_runtime", [False, True])
def test_loading_logo_keeps_animating_while_parent_is_blocked_and_exits(qt, monkeypatch, gui_runtime):
    if qt.platformName() != "windows":
        pytest.skip("Requires the native Windows platform")
    if gui_runtime:
        monkeypatch.setattr(sys, "executable", str(Path(sys.executable).with_name("pythonw.exe")))
    previous = QWidget()
    previous.setGeometry(100, 100, 760, 600)
    previous.show()
    qt.processEvents()
    cover = ProfileLoadingCover(previous)
    try:
        cover.present()
        assert cover.fallback is None and cover.process.poll() is None
        process = cover.process
        handle = helper_window(process.pid)
        first = qt.primaryScreen().grabWindow(handle).toImage()
        sleep(.85)  # Deliberately do not pump the parent's UI events.
        second = qt.primaryScreen().grabWindow(handle).toImage()
        assert not first.isNull() and first.size() == second.size()
        assert bytes(first.constBits()) != bytes(second.constBits())
        cover.dismiss(reveal=previous)
        assert process.poll() == 0 and cover.process is None
    finally:
        cover.abort()
        cover.deleteLater()
        previous.close()


def test_loading_helper_exits_when_parent_pipe_closes(qt):
    previous = QWidget()
    previous.resize(500, 400)
    cover = ProfileLoadingCover(previous)
    try:
        cover.present()
        assert cover.fallback is None
        process = cover.process
        process.stdin.close()
        assert process.wait(timeout=3) == 0
    finally:
        cover.abort()
        cover.deleteLater()
        previous.close()


def test_loading_helper_failure_keeps_profile_presentation_available(qt, monkeypatch):
    import app.ui.profile_loading as loading
    def fail(*args, **kwargs):
        raise OSError("Synthetic helper failure")
    monkeypatch.setattr(loading.subprocess, "Popen", fail)
    previous = QWidget()
    previous.resize(500, 400)
    cover = ProfileLoadingCover(previous)
    try:
        cover.present()
        assert cover.fallback.isVisible() and not cover.fallback._logo.isNull()
        cover.dismiss()
        assert cover.process is None and cover.fallback is None
    finally:
        cover.abort()
        cover.deleteLater()
        previous.close()


def test_loading_helper_exits_if_parent_closes_before_first_paint(qt):
    process = subprocess.Popen([sys.executable, "-m", "app.main", "--profile-loading", "100", "100", "500", "400"],
        cwd=Path(__file__).resolve().parents[1], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        process.stdin.close()
        assert process.wait(timeout=5) == 0, process.stderr.read()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        process.stdout.close()
        process.stderr.close()
