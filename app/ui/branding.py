"""Shared application artwork and Windows taskbar identity."""
import ctypes
import logging
from pathlib import Path
import sys

from PySide6.QtGui import QIcon


APP_ID = "ORSI.Desktop"
APP_ICON = Path(__file__).with_name("assets") / "orsi.ico"


def app_icon():
    icon = QIcon(str(APP_ICON))
    return icon if not icon.isNull() else QIcon(str(APP_ICON.with_name("bsw_o.png")))


def configure_application(application):
    application.setApplicationName("O.R.S.I")
    application.setWindowIcon(app_icon())
    if sys.platform == "win32":
        try:
            shell = ctypes.WinDLL("shell32", use_last_error=True)
            shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
            shell.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
            if shell.SetCurrentProcessExplicitAppUserModelID(APP_ID) < 0:
                raise OSError()
        except OSError:
            logging.getLogger(__name__).warning("The Windows taskbar identity could not be set.")
