from pathlib import Path

import pytest

from app.state.atomic import replace_state_file
from app.state.storage import JsonStore


def windows_denial(code):
    error = PermissionError("replacement denied")
    error.winerror = code
    return error


@pytest.mark.parametrize("code", [5, 32, 33])
def test_transient_windows_replacement_denial_preserves_exact_state_bytes(tmp_path, monkeypatch, code):
    import app.state.atomic as atomic
    store = JsonStore(tmp_path / "state.json")
    store.save({"value": "previous"})
    native_replace = atomic.os.replace
    attempts, delays = [], []
    def flaky_replace(source, target):
        attempts.append(Path(source).read_bytes())
        if len(attempts) <= 2:
            assert store.load() == {"value": "previous"}
            raise windows_denial(code)
        native_replace(source, target)
    monkeypatch.setattr(atomic.os, "replace", flaky_replace)
    monkeypatch.setattr(atomic, "sleep", delays.append)
    store.save({"value": "settled"})
    assert store.load() == {"value": "settled"}
    assert len(attempts) == 3 and all(value == attempts[0] for value in attempts)
    assert delays == [0.02, 0.04]


def test_permanent_denial_exhausts_bounded_retry_without_changing_destination(tmp_path, monkeypatch):
    import app.state.atomic as atomic
    source, destination = tmp_path / "new.tmp", tmp_path / "state.json"
    source.write_bytes(b"new settled state")
    destination.write_bytes(b"previous state")
    attempts, delays = [], []
    def deny(*args):
        attempts.append(args)
        raise windows_denial(5)
    monkeypatch.setattr(atomic.os, "replace", deny)
    monkeypatch.setattr(atomic, "sleep", delays.append)
    with pytest.raises(PermissionError):
        replace_state_file(source, destination)
    assert len(attempts) == 8 and sum(delays) <= 0.91
    assert destination.read_bytes() == b"previous state"


def test_unrelated_permission_error_is_not_retried(tmp_path, monkeypatch):
    import app.state.atomic as atomic
    def deny(*args):
        raise PermissionError("permanent policy denial")
    monkeypatch.setattr(atomic.os, "replace", deny)
    monkeypatch.setattr(atomic, "sleep", lambda _: pytest.fail("Unrelated errors must propagate"))
    with pytest.raises(PermissionError):
        replace_state_file(tmp_path / "a", tmp_path / "b")
