import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep

import pytest

from app.inference.owned_process import start_owned_process, ProcessOwnershipError, _api


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows job-object integration")
ROOT = Path(__file__).resolve().parents[1]


def launch(code, **kwargs):
    return start_owned_process([sys.executable, "-c", code], cwd=ROOT,
                               env=os.environ.copy(), **kwargs)


def test_owned_process_exit_code_timeout_and_idempotent_close():
    process = launch("raise SystemExit(37)")
    try:
        assert process.wait(5) == 37
    finally:
        process.close()
        process.close()
    assert process.poll() == 37
    process = launch("import time; time.sleep(60)")
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(0.03)
        process.terminate()
        assert process.wait(5) == 1
    finally:
        process.close()


def test_atomic_ownership_is_required_before_create_process(monkeypatch):
    real_api = _api()

    class FailedOwnership:
        def __getattr__(self, name):
            return getattr(real_api, name)

        def UpdateProcThreadAttribute(self, *args):
            return False

        def CreateProcessW(self, *args):
            pytest.fail("must not create a child after ownership failed")

    monkeypatch.setattr("app.inference.owned_process._api", lambda: FailedOwnership())
    with pytest.raises(ProcessOwnershipError, match="atomic"):
        launch("raise SystemExit(99)")


def test_create_failure_releases_handles():
    kernel = _api()
    get_count = kernel.GetProcessHandleCount
    get_count.argtypes, get_count.restype = [W.HANDLE, C.POINTER(W.DWORD)], W.BOOL

    def handles():
        count = W.DWORD()
        assert get_count(W.HANDLE(-1), C.byref(count))
        return count.value

    # The first WinError formats a Windows message and loads system DLLs once.
    with pytest.raises(OSError):
        start_owned_process([str(ROOT / "missing-server.exe")], cwd=ROOT,
                            env=os.environ.copy())
    before = handles()
    for _ in range(10):
        with pytest.raises(OSError):
            start_owned_process([str(ROOT / "missing-server.exe")], cwd=ROOT,
                                env=os.environ.copy())
    assert handles() <= before + 1


@pytest.mark.parametrize("force_kill", [False, True])
def test_parent_exit_kills_owned_child_and_descendant_only(tmp_path, force_kill):
    report = tmp_path / "pids.txt"
    child_code = (
        "import subprocess,sys,time; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'], "
        "creationflags=0x08000000); "
        f"open({str(report)!r},'w').write(str(p.pid)); time.sleep(60)"
    )
    parent_code = (
        "import sys,time; from app.inference.owned_process import start_owned_process; import os; "
        f"p=start_owned_process([sys.executable,'-c',{child_code!r}], "
        f"cwd={str(ROOT)!r},env=os.environ.copy()); "
        "print(p.pid,flush=True); " + ("time.sleep(60)" if force_kill else "time.sleep(1); os._exit(0)")
    )
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
    parent = subprocess.Popen([sys.executable, "-c", parent_code], cwd=ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    opened = []
    kernel = _api()
    kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [W.DWORD, W.BOOL, W.DWORD], W.HANDLE
    try:
        child_pid = int(parent.stdout.readline())
        deadline = monotonic() + 5
        while not report.exists() and monotonic() < deadline:
            sleep(0.02)
        assert report.exists()
        descendant_pid = int(report.read_text())
        for pid in (child_pid, descendant_pid):
            handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
            assert handle
            opened.append(handle)
        if force_kill:
            parent.kill()
        parent.wait(5)
        for handle in opened:
            assert kernel.WaitForSingleObject(handle, 5000) == 0
        assert unrelated.poll() is None
    finally:
        parent.kill() if parent.poll() is None else None
        parent.wait(5)
        parent.stdout.close()
        parent.stderr.close()
        unrelated.kill()
        unrelated.wait(5)
        for handle in opened:
            kernel.CloseHandle(handle)
