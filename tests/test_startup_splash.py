"""Native launch regression: use the same pythonw runtime as orsi.cmd."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Native Windows desktop launcher")
@pytest.mark.parametrize("selection,action,compositions", [
    ("legacy", "none", 1),
    ("plain", "none", 1),
    ("locked", "none", 0),
    ("locked", "unlock", 1),
    ("locked", "legacy", 1),
])
def test_real_desktop_launch_and_login_show_native_splash(tmp_path, selection, action, compositions):
    root = tmp_path / "application"
    environment = dict(os.environ, QT_QPA_PLATFORM="windows")
    process = subprocess.Popen([str(Path(sys.executable).with_name("pythonw.exe")),
        "-m", "tests.startup_splash_probe", str(root), selection, action],
        cwd=Path(__file__).resolve().parents[1], env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        assert process.wait(timeout=30) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    assert "error" not in report, report
    assert report["exit_code"] == 0 and report["compositions"] == compositions
    assert [cover["phase"] for cover in report["covers"]] == (["launch"] if action == "none" else ["launch", action])
    assert all(cover["native_visible"] and cover["topmost"] and cover["finished"] for cover in report["covers"])
