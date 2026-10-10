"""Native Windows notifications with silent balloons and an owned tray handle."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget

from app.ui.branding import APP_ICON


class GUID(ctypes.Structure):
    _fields_ = [("data1", wintypes.DWORD), ("data2", wintypes.WORD),
                ("data3", wintypes.WORD), ("data4", ctypes.c_byte * 8)]


class NotifyIconData(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class WindowsNotifications(QWidget):
    clicked = Signal()
    callback_message = 0x8000 + 102

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Tool)
        self._installed = False
        self._closed = False
        self.shell = ctypes.WinDLL("shell32", use_last_error=True)
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.shell.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NotifyIconData)]
        self.shell.Shell_NotifyIconW.restype = wintypes.BOOL
        self.user.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        self.user.LoadIconW.restype = wintypes.HICON
        self.user.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                        ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.user.LoadImageW.restype = wintypes.HICON
        self.user.DestroyIcon.argtypes = [wintypes.HICON]
        self.user.DestroyIcon.restype = wintypes.BOOL
        self.user.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
        self.user.RegisterWindowMessageW.restype = wintypes.UINT
        self.taskbar_created = self.user.RegisterWindowMessageW("TaskbarCreated")
        self.icon = self.user.LoadImageW(None, str(APP_ICON), 1, 0, 0, 0x10 | 0x40)
        self._owns_icon = bool(self.icon)
        if not self.icon:
            # Missing/corrupt artwork must not disable notifications. This
            # stock handle is shared and must never be passed to DestroyIcon.
            self.icon = self.user.LoadIconW(None, ctypes.c_void_p(32516))
        self.hwnd = int(self.winId())

    def _data(self):
        data = NotifyIconData()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd = self.hwnd
        data.uID = 1
        return data

    def _install(self):
        if self._installed:
            return True
        data = self._data()
        data.uFlags = 1 | 2 | 4  # NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = self.callback_message
        data.hIcon = self.icon
        data.szTip = "O.R.S.I"
        self._installed = bool(self.shell.Shell_NotifyIconW(0, ctypes.byref(data)))
        if self._installed:
            data.uVersion = 4
            self.shell.Shell_NotifyIconW(4, ctypes.byref(data))
        return self._installed

    def show_message(self, title, message):
        if self._closed or not self._install():
            return False
        data = self._data()
        data.uFlags = 0x10  # NIF_INFO
        data.szInfoTitle = title[:63]
        data.szInfo = message[:255]
        # Custom artwork | NIIF_NOSOUND | NIIF_RESPECT_QUIET_TIME. Qt's tray
        # showMessage API cannot suppress the extra Windows notification sound.
        data.dwInfoFlags = (0x04 if self._owns_icon else 0x01) | 0x10 | 0x80
        if self._owns_icon:
            data.hBalloonIcon = self.icon
        return bool(self.shell.Shell_NotifyIconW(1, ctypes.byref(data)))

    def nativeEvent(self, event_type, message):  # noqa: N802
        native = wintypes.MSG.from_address(int(message))
        if self.taskbar_created and native.message == self.taskbar_created and not self._closed:
            self._installed = False
            self._install()
            return True, 0
        elif native.message == self.callback_message:
            if native.lParam & 0xffff in {0x405, 0x400, 0x401, 0x202}:
                self.clicked.emit()  # Balloon click, keyboard select or tray click.
            return True, 0
        return super().nativeEvent(event_type, message)

    def shutdown(self):
        self._closed = True
        if self._installed:
            self.shell.Shell_NotifyIconW(2, ctypes.byref(self._data()))
            self._installed = False
        if self._owns_icon:
            self.user.DestroyIcon(self.icon)
            self._owns_icon = False
            self.icon = None
