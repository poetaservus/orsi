"""Real icon decoding, native resource ownership and Windows shortcut metadata."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.branding import APP_ICON, APP_ID, app_icon, configure_application
from app.ui.main_window import MainWindow
from app.ui.profile_loading import ProfileLoadingWindow
from tools.build_app_icon import SIZES


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_all_icon_sizes_decode_with_transparency_and_original_proportions(app):
    icon = app_icon()
    source = QImage(str(APP_ICON.with_name("bsw_o.png")))
    assert not source.isNull() and source.hasAlphaChannel()
    assert not icon.isNull() and {s.width() for s in icon.availableSizes()} == set(SIZES)
    for side in SIZES:
        image = icon.pixmap(side, side).toImage()
        assert image.hasAlphaChannel() and image.size().width() == side and image.size().height() == side
        assert image.pixelColor(0, 0).alpha() == 0 and image.pixelColor(side // 2, side // 2).alpha() == 0
        visible = [(x,y) for y in range(side) for x in range(side) if image.pixelColor(x,y).alpha() > 100]
        assert visible
        width = max(x for x,y in visible) - min(x for x,y in visible) + 1
        height = max(y for x,y in visible) - min(y for x,y in visible) + 1
        assert abs(width / height - source.width() / source.height()) < .2


def test_application_and_top_level_windows_share_logo(app):
    configure_application(app)
    window = MainWindow(None, "synthetic")
    loading = ProfileLoadingWindow(geometry=QRect(0, 0, 760, 600))
    expected = app_icon().pixmap(32, 32).toImage()
    try:
        assert app.applicationName() == "O.R.S.I"
        assert app.windowIcon().pixmap(32, 32).toImage() == expected
        assert window.windowIcon().pixmap(32, 32).toImage() == expected
        assert loading.windowIcon().pixmap(32, 32).toImage() == expected
        if os.name == "nt":
            shell, ole = ctypes.WinDLL("shell32"), ctypes.WinDLL("ole32")
            shell.GetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
            shell.GetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
            ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
            result = ctypes.c_void_p()
            assert shell.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(result)) == 0
            try:
                assert ctypes.wstring_at(result) == APP_ID
            finally:
                ole.CoTaskMemFree(result)
    finally:
        loading.close()
        window.close()


def test_quiet_launcher_preserves_arguments_and_local_runtime_path(monkeypatch):
    import sys
    import app.launcher as launcher
    import app.main as desktop
    call = Mock(return_value=0)
    monkeypatch.setattr(desktop, "main", call)
    monkeypatch.setenv("PATH", "original-search-path")
    monkeypatch.setattr(sys, "argv", ["shortcut", "synthetic option"])
    assert launcher.main() == 0 and sys.argv == ["shortcut", "synthetic option"]
    libraries = str(Path(launcher.__file__).resolve().parents[1] / "runtime/python/Lib/site-packages/nvidia/cu13/bin/x86_64")
    assert os.environ["PATH"] == libraries + os.pathsep + "original-search-path"
    call.assert_called_once_with()


@pytest.mark.skipif(os.name != "nt", reason="Windows icon ownership")
@pytest.mark.parametrize("missing", [False, True])
def test_native_tray_loads_logo_and_releases_only_owned_icons(app, monkeypatch, tmp_path, missing):
    import app.ui.windows_notifications as native
    if missing:
        monkeypatch.setattr(native, "APP_ICON", tmp_path / "missing.ico")
    parent = QWidget()
    backend = native.WindowsNotifications(parent)
    destroy = Mock(wraps=backend.user.DestroyIcon)
    backend.user.DestroyIcon = destroy
    try:
        assert backend.icon and backend._owns_icon is (not missing)
        backend.shutdown()
        backend.shutdown()
        assert destroy.call_count == (0 if missing else 1)
    finally:
        backend.shutdown()
        parent.close()


def powershell(script, *, path):
    environment = dict(os.environ, ORSI_ICON_TEST_SHORTCUT=str(path))
    return subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-Command", "-"],
        input=script, text=True, capture_output=True, env=environment, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)


def read_shortcut(path):
    value = powershell("""
$p=$env:ORSI_ICON_TEST_SHORTCUT
$link=(New-Object -ComObject WScript.Shell).CreateShortcut($p)
$folder=(New-Object -ComObject Shell.Application).Namespace((Split-Path -Parent $p))
$item=$folder.ParseName((Split-Path -Leaf $p))
@{target=$link.TargetPath;arguments=$link.Arguments;working=$link.WorkingDirectory;icon=$link.IconLocation;description=$link.Description;appid=$item.ExtendedProperty('System.AppUserModel.ID')} | ConvertTo-Json -Compress
""", path=path)
    assert value.returncode == 0, value.stderr
    return json.loads(value.stdout.strip())


@pytest.fixture
def shortcut_inputs(tmp_path):
    root = tmp_path / "node's application with spaces"
    (root / "app/ui/assets").mkdir(parents=True)
    (root / "ORSI.cmd").write_text("@exit /b 0\n")
    (root / "runtime/python").mkdir(parents=True)
    (root / "runtime/python/pythonw.exe").write_bytes(b"synthetic executable, never run")
    (root / "app/ui/assets/orsi.ico").write_bytes(APP_ICON.read_bytes())
    return root, tmp_path / "O.R.S.I test.lnk"


def create_shortcut(root, path):
    script = Path(__file__).resolve().parents[1] / "tools/create_shortcut.ps1"
    return subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(script), "-ApplicationRoot", str(root), "-ShortcutPath", str(path)],
        text=True, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)


@pytest.mark.skipif(os.name != "nt", reason="Windows shell links")
def test_shortcut_icon_identity_and_custom_options_survive_refresh(shortcut_inputs):
    root, path = shortcut_inputs
    result = create_shortcut(root, path)
    assert result.returncode == 0, result.stderr
    link = read_shortcut(path)
    assert Path(link["target"]) == root / "runtime/python/pythonw.exe" and Path(link["working"]) == root
    assert link["arguments"] == "-m app.launcher"
    assert link["icon"] == str(root / "app/ui/assets/orsi.ico") + ",0" and link["appid"] == APP_ID
    change = powershell("""
$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:ORSI_ICON_TEST_SHORTCUT)
$s.Arguments='-m app.launcher synthetic custom option';$s.Description='Keep this custom description';$s.Save()
""", path=path)
    assert change.returncode == 0, change.stderr
    result = create_shortcut(root, path)
    assert result.returncode == 0, result.stderr
    refreshed = read_shortcut(path)
    assert refreshed == link | {"arguments":"-m app.launcher synthetic custom option","description":"Keep this custom description"}
    assert not list(path.parent.glob(".orsi-shortcut-*.lnk"))


@pytest.mark.skipif(os.name != "nt", reason="Windows shell links")
def test_shortcut_for_another_application_is_preserved(shortcut_inputs):
    root, path = shortcut_inputs
    value = powershell("""
$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:ORSI_ICON_TEST_SHORTCUT)
$s.TargetPath=Join-Path $env:WINDIR 'notepad.exe';$s.Save()
""", path=path)
    assert value.returncode == 0, value.stderr
    before = path.read_bytes()
    result = create_shortcut(root, path)
    assert result.returncode != 0 and path.read_bytes() == before
    assert not list(path.parent.glob(".orsi-shortcut-*.lnk"))
