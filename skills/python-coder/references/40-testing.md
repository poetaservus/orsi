# 40 — Tests that establish behavior

Read for implementation verification, regression tests and test suite changes.

## Test the contract at the right boundary

Choose evidence that would fail for the defect or missing behavior. For a bug,
establish the existing failure before the fix when possible. A useful test states
input, operation and observable outcome. Prefer behavior over private method
names, call counts or snapshots of incidental wording.

Use pure unit tests for domain invariants, focused integration tests for real
boundaries, and a few end-to-end checks for the critical journey. Do not replace
everything with mocks and then claim storage, codecs, HTTP or UI behavior works.
Conversely, a pure transformation does not need a full application startup.

Coverage identifies gaps; it is not a mandatory percentage or proof of correctness.
Avoid new tests for reversible cosmetic changes unless a real behavioral concern
justifies them. Preserve existing acceptance prompts and expectations.

## Design meaningful cases

- Normal, empty and boundary inputs; valid versus invalid data shapes.
- Missing versus null, false and zero when the contract distinguishes them.
- Malformed input, permission failures and missing dependencies/resources.
- Failure after acquisition or partial progress; old data retained on failed saves.
- Repeated requests, ordering and idempotency if the behavior depends on them.
- Cancellation, timeout and shutdown with cleanup if work is asynchronous.

Assert specific exception classes and meaningful stable details. Reject a test
that would pass if the operation were a no-op. Use parameterization for related
cases, not a huge unrelated matrix. Property-based testing is useful for rich
input spaces and invariants; it is not required for every small helper.

## Control dependencies, not the implementation

Use `tmp_path` for isolated storage and `monkeypatch` for environment/lookup
boundaries. Patch the name where the code under test looks it up. Choose a small
fake or real local boundary when it is more truthful than a loose `Mock`.
Use constrained mocks (`spec`/autospec) when collaborator signatures matter.
Never mock the operation whose behavior the test claims to establish.

Inject clock/sleep/random sources for retry tests so they finish immediately.
Keep network and paid provider calls out of ordinary deterministic tests. Live
gates must be opt-in, bounded and reported separately.

## Fixture lifecycle

Keep fixtures narrow and make cleanup reliable even if assertions fail. Use
temporary directories, scoped patches, context managers and `yield` with
`try/finally`. Avoid persistent production state, global database resets and
surprise autouse fixtures. Respect the suite's existing isolation conventions.

Do not rely on arbitrary sleeps to establish concurrency. Use events, barriers or
observable signals with a bounded wait. Test an application's actual shutdown
boundary; a mocked `close()` cannot prove handles or threads were released.

## Failure-preservation example

The following test is intended to run alongside the `save_json` definition in
[30](30-errors-and-resources.md). It simulates the replace boundary failing and
checks both old data and temporary-file cleanup.

```python
def test_failed_replace_preserves_data(tmp_path, monkeypatch):
    target = tmp_path / "settings.json"
    target.write_text('{"theme":"original"}\n', encoding="utf-8")

    def fail_replace(source, destination):
        raise PermissionError("synthetic replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    import pytest
    with pytest.raises(PermissionError):
        save_json(target, {"theme": "changed"})
    assert target.read_text(encoding="utf-8") == '{"theme":"original"}\n'
    assert list(tmp_path.iterdir()) == [target]
```

## Verification rhythm

Run focused checks after the change, then the repository's required suite/lint/
typing/build gates. Diagnose failures: environment restrictions, unchanged flaky
tests and genuine regressions are different facts. Do not adjust timeouts or
weaken assertions to obtain green output without establishing the cause.

Record the commands or gates actually used and their outcomes. A skipped live
test, untested platform or unbuilt artifact cannot be reported as verified.
