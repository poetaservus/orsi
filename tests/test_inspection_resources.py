import json
from pathlib import Path
import sys

import pytest

from app.capabilities.project_verification import ProjectInspectCapability, run_worker
from app.runtime.cancellation import CancellationToken
from app.runtime.owned_process import ProcessOwnershipError, start_owned_process
from tests.test_project_verification import approved
from tests.test_filesystem_read_text import context


@pytest.mark.parametrize("allowance", [True, 0, 1024**3 - 1, 4 * 1024**3 + 1, None])
def test_untrusted_resource_allowances_cannot_launch_a_process(tmp_path, allowance):
    with pytest.raises(ProcessOwnershipError, match="bounded allowance"):
        start_owned_process(["never.exe"], cwd=tmp_path, env={}, job_memory_bytes=allowance)


@pytest.mark.parametrize("allowance", [None, 4 * 1024**3])
def test_native_job_applies_the_selected_bounded_memory_and_releases_it(tmp_path, allowance):
    code = ("import ctypes,json; from app.runtime.owned_process import _api,_ExtendedLimits; "
        "limits=_ExtendedLimits(); api=_api(); "
        "assert api.QueryInformationJobObject(None,9,ctypes.byref(limits),ctypes.sizeof(limits),None); "
        "print(json.dumps({'memory':limits.job_memory,'processes':limits.basic.active_limit,'flags':limits.basic.flags}))")
    kwargs = {} if allowance is None else {"job_memory_bytes": allowance}
    result = run_worker([str(Path(sys.executable).resolve()), "-c", code],
        cwd=Path(__file__).resolve().parents[1], timeout=10, cancellation=CancellationToken(), **kwargs)
    assert result["exit_code"] == 0 and result["owned_processes_released"]
    limits = json.loads(result["output"])
    assert limits["memory"] == (1024**3 if allowance is None else allowance)
    assert limits["processes"] == 16 and limits["flags"] & 0x2000  # Kill on job close remains enabled.


def test_inspection_uses_its_own_allowance_without_model_control(tmp_path, monkeypatch):
    tool = ProjectInspectCapability(tmp_path / "state")
    observed = []
    def worker(*args, **kwargs):
        observed.append(kwargs["job_memory_bytes"])
        return {"exit_code": 0, "stop_reason": None, "output": '{"passed":true}', "owned_processes_released": True}
    monkeypatch.setattr("app.capabilities.project_verification.run_worker", worker)
    args = {"project_path": str(tmp_path), "kind": "browser", "url": "http://localhost:5173/"}
    assert tool.invoke(args, approved(tool, args, context(tmp_path))).success
    assert observed == [4 * 1024**3]
    assert "job_memory_bytes" not in tool.arguments_model.model_fields
