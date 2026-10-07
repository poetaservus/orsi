"""Scoped authority, storage substitution, bounded continuation and native reads."""
from dataclasses import replace
import json
import os
import shutil

import pytest

from app.capabilities.contracts import CapabilityContext, CapabilityErrorCode, PermissionClass
from app.capabilities.registry import CapabilityRegistration, CapabilityRegistry
from app.capabilities.skill_read_reference import SkillReadReferenceCapability
from app.execution.executor import CapabilityExecutor
from app.runtime.cancellation import CancellationToken, CancellationSource, TaskCancelled
from app.runtime.skills import SkillInstaller, SkillRegistry
from app.runtime.skills.loader import load_skill, MAX_SKILL_SIZE
from app.runtime.skills.package_format import ReferenceFile, MAX_REFERENCE_BYTES
from app.runtime.skills.parser import parse_skill
from app.runtime.skills.reference_reader import (
    PackageSnapshot, SkillReferenceReader, ReferenceReadError, ReferenceErrorCode,
)
from app.runtime.skills.reference_storage import FilesystemReferenceStorage
from app.security.permissions import (PermissionGate, PermissionRule, PermissionDecision,
                                      ApprovalManager, prepare_capability_call)
from tests.test_skill_package_format_v1 import FIXTURE


class MemoryStorage:
    """An unlocked storage stand-in with no host filesystem authority."""
    def __init__(self, snapshot):
        self.value = snapshot
        self.calls = 0
        self.on_read = None

    def snapshot(self, skill, cancellation):
        cancellation.raise_if_cancelled()
        self.calls += 1
        if self.on_read:
            self.on_read()
        return self.value


@pytest.fixture
def memory(tmp_path):
    main = (FIXTURE / "SKILL.md").read_bytes()
    skill = parse_skill(main.decode("utf-8"), root_path=tmp_path, source_path=tmp_path / "SKILL.md")
    refs = tuple(ReferenceFile(p.relative_to(FIXTURE).as_posix(), p.read_bytes())
                 for p in sorted((FIXTURE / "references").glob("*.md")))
    storage = MemoryStorage(PackageSnapshot("vault-entry-1", main, refs))
    reader = SkillReferenceReader(storage)
    binding = reader.activate(skill, CancellationToken())
    return skill, storage, reader, binding


def read(reader, binding, path="references/behavior.md", **kwargs):
    return reader.read(binding, path, version=kwargs.pop("version", binding.version),
                       cancellation=kwargs.pop("cancellation", CancellationToken()), **kwargs)


def rejected(code, call):
    with pytest.raises(ReferenceReadError) as error:
        call()
    assert error.value.code == code
    assert len(str(error.value)) < 140
    return error.value


def test_inventory_is_content_free_and_one_selected_document_is_returned(memory):
    _, storage, reader, binding = memory
    inventory = binding.inventory()
    assert [r["path"] for r in inventory["resources"]] == ["references/behavior.md", "references/checks.md"]
    serialized = json.dumps(inventory)
    assert "lower exceeds upper" not in serialized and "vault-entry-1" not in serialized
    assert "vault-entry-1" not in repr(binding)
    result = read(reader, binding)
    assert result["text"] == storage.value.references[0].data.decode("utf-8-sig")
    assert "assert clamp" not in result["text"]
    assert result["complete_document"] and result["next_offset"] is None
    assert result["content_is_untrusted"]
    assert result["version"] == inventory["version"]
    assert "root_path" not in result and storage.calls == 2
    inventory["resources"].clear()
    assert len(binding.resources) == 2  # Detached public inventory cannot expand authority.


@pytest.mark.parametrize("path", ["../SKILL.md", "SKILL.md", "references/../SKILL.md",
    "references\\behavior.md", "C:/secret.md", "//host/secret.md", "references/%62ehavior.md",
    "references/behavior.md#section", "references/behavior.md:secret", "references/CON.md",
    "references//behavior.md", "references/ behavior.md", "references/behavior.md "])
def test_unsafe_identifiers_never_reach_storage(memory, path):
    _, storage, reader, binding = memory
    rejected(ReferenceErrorCode.UNSAFE, lambda: read(reader, binding, path))
    assert storage.calls == 1


@pytest.mark.parametrize("path", ["references/missing.md", "references/Behavior.md", "references/other-skill.md"])
def test_missing_inventory_members_never_trigger_fallback_search(memory, path):
    _, storage, reader, binding = memory
    rejected(ReferenceErrorCode.MISSING, lambda: read(reader, binding, path))
    assert storage.calls == 1


@pytest.mark.parametrize("kwargs", [{"max_bytes": 0}, {"max_bytes": 4097}, {"max_bytes": True},
    {"max_lines": 0}, {"max_lines": 81}, {"offset": -1}, {"offset": False}, {"offset": 100000}])
def test_invalid_excerpt_bounds_are_rejected(memory, kwargs):
    _, _, reader, binding = memory
    rejected(ReferenceErrorCode.INVALID_REQUEST, lambda: read(reader, binding, **kwargs))


def test_utf8_bom_crlf_long_line_continuation_is_exact_and_makes_progress(memory):
    skill, storage, reader, _ = memory
    text = "A😀é\r\n" * 17 + "X" * 120 + "\nFinal\n"
    storage.value = replace(storage.value, references=(ReferenceFile("references/unicode.md",
                              b"\xef\xbb\xbf" + text.encode("utf-8")),))
    binding = reader.activate(skill, CancellationToken())
    offset, chunks = 0, []
    while True:
        result = read(reader, binding, "references/unicode.md", offset=offset, max_bytes=7, max_lines=1)
        chunks.append(result["text"])
        assert result["bytes_returned"] <= 7 and len(result["text"].splitlines()) <= 1
        assert result["end_offset"] > offset
        assert result["total_text_bytes"] == len(text.encode("utf-8"))
        if not result["has_more"]:
            assert result["next_offset"] is None and not result["complete_document"]
            break
        offset = result["next_offset"]
    assert "".join(chunks) == text
    rejected(ReferenceErrorCode.INVALID_REQUEST,
             lambda: read(reader, binding, "references/unicode.md", offset=2))
    empty = read(reader, binding, "references/unicode.md", offset=len(text.encode("utf-8")))
    assert empty["text"] == "" and not empty["has_more"]


def test_default_and_maximum_excerpts_remain_small(memory):
    skill, storage, reader, _ = memory
    storage.value = replace(storage.value, references=(ReferenceFile("references/long.md", b"x" * 9000),))
    binding = reader.activate(skill, CancellationToken())
    result = read(reader, binding, "references/long.md")
    assert result["bytes_returned"] == 2048 and result["next_offset"] == 2048
    assert not result["complete_document"]
    result = read(reader, binding, "references/long.md", max_bytes=4096)
    assert result["bytes_returned"] == 4096


@pytest.mark.parametrize("change", ["reference", "unrequested-reference", "added", "removed", "main", "identity"])
def test_any_observed_package_change_revokes_authority_even_if_restored(memory, change):
    _, storage, reader, binding = memory
    original = storage.value
    if change in ("reference", "unrequested-reference"):
        index = 0 if change == "reference" else 1
        refs = list(original.references)
        refs[index] = replace(refs[index], data=b"changed")
        storage.value = replace(original, references=tuple(refs))
    elif change == "added":
        storage.value = replace(original, references=original.references + (ReferenceFile("references/new.md", b"new"),))
    elif change == "removed":
        storage.value = replace(original, references=original.references[1:])
    elif change == "main":
        storage.value = replace(original, main=original.main + b"\nChanged instructions")
    else:
        storage.value = replace(original, identity="vault-entry-replaced")
    rejected(ReferenceErrorCode.STALE, lambda: read(reader, binding))
    storage.value = original
    rejected(ReferenceErrorCode.DISABLED, lambda: read(reader, binding))


def test_switch_deactivation_reactivation_and_other_reader_never_reuse_bindings(memory):
    skill, storage, reader, old = memory
    current = reader.activate(skill, CancellationToken())
    assert old.version == current.version and old != current
    rejected(ReferenceErrorCode.STALE, lambda: read(reader, old))
    read(reader, current)
    other = SkillReferenceReader(storage)
    other.activate(skill, CancellationToken())
    rejected(ReferenceErrorCode.STALE, lambda: read(other, current))
    reader.deactivate()
    rejected(ReferenceErrorCode.DISABLED, lambda: read(reader, current))


@pytest.mark.parametrize("data,code", [(b"\xff", ReferenceErrorCode.INVALID_PACKAGE),
    (b"\x00secret", ReferenceErrorCode.INVALID_PACKAGE), (b" ", ReferenceErrorCode.INVALID_PACKAGE),
    (b"x" * (MAX_REFERENCE_BYTES + 1), ReferenceErrorCode.LIMIT_EXCEEDED)])
def test_invalid_references_fail_without_leaking_contents_or_retaining_authority(memory, data, code):
    skill, storage, reader, old = memory
    storage.value = replace(storage.value, references=(ReferenceFile("references/behavior.md", data),))
    rejected(code, lambda: reader.activate(skill, CancellationToken()))
    rejected(ReferenceErrorCode.DISABLED, lambda: read(reader, old))


def test_failed_snapshot_limit_and_cancellation_leave_no_old_authority(memory):
    skill, storage, reader, old = memory
    storage.value = replace(storage.value, main=b"x" * (MAX_SKILL_SIZE + 1))
    rejected(ReferenceErrorCode.LIMIT_EXCEEDED, lambda: reader.activate(skill, CancellationToken()))
    rejected(ReferenceErrorCode.DISABLED, lambda: read(reader, old))
    source = CancellationSource()
    source.cancel("private cancellation detail")
    with pytest.raises(TaskCancelled):
        reader.activate(skill, source.token)


def test_cancellation_and_revocation_during_snapshot_prevent_output(memory):
    _, storage, reader, binding = memory
    source = CancellationSource()
    storage.on_read = lambda: source.cancel()
    with pytest.raises(TaskCancelled):
        read(reader, binding, cancellation=source.token)
    storage.on_read = reader.deactivate
    rejected(ReferenceErrorCode.STALE, lambda: read(reader, binding))


def context(tmp_path, **kwargs):
    return CapabilityContext(call_id="read-1", session_id=kwargs.pop("session_id", "session-1"),
        turn_id=kwargs.pop("turn_id", "turn-1"), portable_root=tmp_path,
        allowed_read_roots=(tmp_path,), cancellation=kwargs.pop("cancellation", CancellationToken()))


def capability(reader, binding):
    return SkillReadReferenceCapability(reader, binding, session_id="session-1", turn_id="turn-1")


def test_scoped_capability_obeys_registry_permissions_and_existing_executor(memory, tmp_path):
    _, _, reader, binding = memory
    tool = capability(reader, binding)
    registry = CapabilityRegistry((CapabilityRegistration(tool, enabled=True, model_visible=True),))
    assert registry.model_visible_names == ("skill.read_reference",)
    args = {"path": "references/behavior.md", "version": binding.version}
    prepared = prepare_capability_call(tool, args, context(tmp_path))
    assert prepared.request.resource is None  # No arbitrary host resource or extra filesystem permission.
    denied = ApprovalManager().authorize(PermissionGate().evaluate(prepared))
    executor = CapabilityExecutor()
    assert executor.execute(prepared, denied).error.code == CapabilityErrorCode.PERMISSION_DENIED
    gate = PermissionGate((PermissionRule("scoped-skill-reader", PermissionDecision.ALLOW,
                          permission=PermissionClass.READ, capability_pattern=tool.name),))
    allowed = ApprovalManager().authorize(gate.evaluate(prepared))
    result = executor.execute(prepared, allowed)
    assert result.success and result.output["complete_document"]
    assert executor.execute(prepared, allowed).error.code == CapabilityErrorCode.CALL_REPLAYED
    executor.shutdown()


@pytest.mark.parametrize("case,code", [("session", CapabilityErrorCode.PERMISSION_DENIED),
    ("turn", CapabilityErrorCode.PERMISSION_DENIED), ("disabled", CapabilityErrorCode.DISABLED_CAPABILITY),
    ("stale", CapabilityErrorCode.PERMISSION_DENIED), ("missing", CapabilityErrorCode.NOT_FOUND),
    ("extra", CapabilityErrorCode.INVALID_ARGUMENTS), ("cancelled", CapabilityErrorCode.CANCELLED),
    ("invalid-offset", CapabilityErrorCode.INVALID_ARGUMENTS)])
def test_capability_returns_fixed_structured_errors(memory, tmp_path, case, code):
    _, _, reader, binding = memory
    tool = capability(reader, binding)
    args = {"path": "references/behavior.md", "version": binding.version}
    ctx = context(tmp_path)
    if case in ("session", "turn"):
        ctx = replace(ctx, **{case + "_id": "other"})
    elif case == "disabled": reader.deactivate()
    elif case == "stale": args["version"] = "0" * 64
    elif case == "missing": args["path"] = "references/missing.md"
    elif case == "extra": args["skill"] = "other-skill"
    elif case == "invalid-offset": args["offset"] = 9999
    else:
        source = CancellationSource()
        source.cancel("secret")
        ctx = replace(ctx, cancellation=source.token)
    result = tool.invoke(args, ctx)
    assert not result.success and result.output is None and result.error.code == code
    assert "secret" not in result.error.message


def test_storage_exception_has_no_traceback_or_private_text(memory, tmp_path, caplog):
    _, storage, reader, binding = memory
    def fail(): raise RuntimeError("private-vault-key-and-document")
    storage.on_read = fail
    result = capability(reader, binding).invoke(
        {"path": "references/behavior.md", "version": binding.version}, context(tmp_path))
    assert result.error.code == CapabilityErrorCode.INTERNAL_ERROR
    assert "private-vault" not in json.dumps(result.model_dump(mode="json"))
    assert "private-vault" not in caplog.text


@pytest.fixture
def native(tmp_path):
    if os.name != "nt": pytest.skip("Native non-following Windows storage")
    root = tmp_path / "pack"
    shutil.copytree(FIXTURE, root)
    skill = load_skill(root / "SKILL.md", root_path=root)
    reader = SkillReferenceReader(FilesystemReferenceStorage())
    return root, skill, reader, reader.activate(skill, CancellationToken())


def test_native_project_package_and_legacy_single_file_release_handles(native, tmp_path):
    root, skill, reader, binding = native
    assert read(reader, binding)["complete_document"]
    root.rename(tmp_path / "released")
    rejected(ReferenceErrorCode.STALE, lambda: read(reader, binding))
    single = tmp_path / "single"
    single.mkdir()
    shutil.copyfile(FIXTURE / "SKILL.md", single / "SKILL.md")
    binding = reader.activate(load_skill(single / "SKILL.md", root_path=single), CancellationToken())
    assert binding.resources == ()
    rejected(ReferenceErrorCode.MISSING, lambda: read(reader, binding))


@pytest.mark.parametrize("change", ["main", "reference", "other-reference", "add", "remove", "root-replaced", "oversize"])
def test_native_package_changes_cannot_supply_stale_continuations(native, tmp_path, change):
    root, _, reader, binding = native
    first = read(reader, binding, max_bytes=20)
    assert first["has_more"]
    if change == "root-replaced":
        root.rename(tmp_path / "old")
        shutil.copytree(tmp_path / "old", root)
    elif change == "remove": (root / "references/checks.md").unlink()
    elif change == "add": (root / "references/new.md").write_bytes(b"new")
    else:
        target = root / ({"main": "SKILL.md", "other-reference": "references/checks.md"}.get(
            change, "references/behavior.md"))
        target.write_bytes(b"x" * (MAX_REFERENCE_BYTES + 1) if change == "oversize"
                           else target.read_bytes() + b"\nChanged")
    rejected(ReferenceErrorCode.LIMIT_EXCEEDED if change == "oversize" else ReferenceErrorCode.STALE,
             lambda: read(reader, binding, offset=first["next_offset"]))
    root.rename(tmp_path / "handles-released")


@pytest.mark.parametrize("location", ["package", "references", "nested", "leaf"])
def test_native_junctions_fail_closed_and_leave_external_data_untouched(native, tmp_path, location):
    import _winapi
    root, _, reader, binding = native
    outside = tmp_path / "external"
    outside.mkdir()
    (outside / "private.md").write_bytes(b"external private document")
    target = root if location == "package" else root / "references" if location == "references" else root / (
        "references/behavior.md" if location == "leaf" else "references/nested")
    if target.exists(): target.rename(tmp_path / "original-tree")
    _winapi.CreateJunction(str(outside), str(target))
    try:
        rejected(ReferenceErrorCode.UNSAFE, lambda: read(reader, binding))
        assert (outside / "private.md").read_bytes() == b"external private document"
    finally:
        target.rmdir()  # Remove only the junction, never its destination.


def test_native_cancellation_releases_package_handles(native, tmp_path, monkeypatch):
    import app.runtime.skills.windows_reference_snapshot as windows
    root, _, reader, binding = native
    real = windows._read
    source = CancellationSource()
    inspected = []
    def cancel_while_pinned(handle, max_bytes, token):
        inspected.append(max_bytes)
        source.cancel()
        return real(handle, max_bytes, token)
    monkeypatch.setattr(windows, "_read", cancel_while_pinned)
    with pytest.raises(TaskCancelled):
        read(reader, binding, cancellation=source.token)
    assert inspected == [MAX_SKILL_SIZE]
    root.rename(tmp_path / "cancelled-handles-released")


def test_native_reference_growth_during_read_fails_closed(native, tmp_path, monkeypatch):
    import app.runtime.skills.windows_reference_snapshot as windows
    root, _, reader, binding = native
    real = windows._child
    from contextlib import contextmanager
    @contextmanager
    def grow(parent, name, **kwargs):
        if name == "behavior.md":
            (root / "references/behavior.md").write_bytes(b"PRIVATE-CONTENT" * 1500)
        with real(parent, name, **kwargs) as opened:
            yield opened
    monkeypatch.setattr(windows, "_child", grow)
    rejected(ReferenceErrorCode.LIMIT_EXCEEDED, lambda: read(reader, binding))
    root.rename(tmp_path / "growth-handles-released")


def test_native_rename_and_junction_swap_never_read_foreign_contents(native, tmp_path, monkeypatch):
    import _winapi
    import app.runtime.skills.windows_reference_snapshot as windows
    from contextlib import contextmanager
    from types import SimpleNamespace
    root, _, reader, binding = native
    outside = tmp_path / "outside-pack"
    shutil.copytree(FIXTURE, outside)
    (outside / "references/behavior.md").write_bytes(b"PRIVATE FOREIGN DOCUMENT")
    real, moved, observed = windows._read, tmp_path / "moved-pack", []
    native_factory, child, swapped = windows._native, windows._child, []
    def share_directory_renames():
        native = native_factory()
        def create(*args):
            args = list(args)
            if args[8] & 1: args[6] = 7  # Exercise the identity guard even where renaming is permitted.
            return native.NtCreateFile(*args)
        return SimpleNamespace(NtCreateFile=create, NtQueryDirectoryFile=native.NtQueryDirectoryFile,
                               RtlNtStatusToDosError=native.RtlNtStatusToDosError)
    @contextmanager
    def replace_path(parent, name, **kwargs):
        if name == "SKILL.md" and not swapped:
            root.rename(moved)
            _winapi.CreateJunction(str(outside), str(root))
            swapped.append(True)
        with child(parent, name, **kwargs) as opened:
            yield opened
    def swap(handle, max_bytes, token):
        data = real(handle, max_bytes, token)
        observed.append(data)
        return data
    monkeypatch.setattr(windows, "_native", share_directory_renames)
    monkeypatch.setattr(windows, "_child", replace_path)
    monkeypatch.setattr(windows, "_read", swap)
    try:
        rejected(ReferenceErrorCode.UNSAFE, lambda: read(reader, binding))
        assert observed and all(b"PRIVATE FOREIGN DOCUMENT" not in data for data in observed)
        assert (outside / "references/behavior.md").read_bytes() == b"PRIVATE FOREIGN DOCUMENT"
    finally:
        if swapped: root.rmdir()  # Remove the junction only.
    moved.rename(tmp_path / "swap-handles-released")


def test_reader_is_not_exposed_in_production_catalog_before_conversation_wiring(tmp_path):
    from app.capabilities.catalog import build_builtin_registry
    from app.settings.agent import AgentFeatureConfig
    registry = build_builtin_registry(AgentFeatureConfig(), application_root=tmp_path,
                                      state_directory=tmp_path / "state")
    assert "skill.read_reference" not in registry.names


@pytest.mark.parametrize("change,code", [("count", ReferenceErrorCode.LIMIT_EXCEEDED),
    ("total", ReferenceErrorCode.LIMIT_EXCEEDED), ("depth", ReferenceErrorCode.LIMIT_EXCEEDED),
    ("invalid-encoding", ReferenceErrorCode.INVALID_PACKAGE), ("reserved", ReferenceErrorCode.INVALID_PACKAGE)])
def test_native_inventory_rejects_contract_violations_before_activation(native, change, code):
    root, skill, reader, old = native
    if change == "count":
        for index in range(31): (root / f"references/extra{index}.md").write_bytes(b"extra")
    elif change == "total":
        for index in range(5): (root / f"references/large{index}.md").write_bytes(b"x" * MAX_REFERENCE_BYTES)
    elif change == "depth":
        target = root / "references/a/b/c/d/e"
        target.mkdir(parents=True)
        (target / "deep.md").write_bytes(b"deep")
    elif change == "invalid-encoding": (root / "references/behavior.md").write_bytes(b"PRIVATE\xff")
    else:
        # Native Windows cannot create reserved device names through ordinary
        # paths; an invalid but creatable component exercises the same validator.
        (root / "references/space name.md").write_bytes(b"invalid component")
    rejected(code, lambda: reader.activate(skill, CancellationToken()))
    rejected(ReferenceErrorCode.DISABLED, lambda: read(reader, old))
    root.rename(root.with_name("validation-handles-released"))


def test_native_nested_bom_documents_and_document_links_remain_plain_text(native):
    root, skill, reader, _ = native
    nested = root / "references/examples"
    nested.mkdir()
    data = b"\xef\xbb\xbf# Example\r\n[Behavior](../behavior.md)\r\n"
    (nested / "sample.md").write_bytes(data)
    binding = reader.activate(skill, CancellationToken())
    result = read(reader, binding, "references/examples/sample.md")
    assert result["text"] == data.decode("utf-8-sig") and result["complete_document"]
    assert result["total_text_bytes"] == len(data) - 3
    assert len(binding.resources) == 3  # Link text does not expand/activate anything.


def test_installed_package_read_and_removal_invalidate_reader(native, tmp_path):
    root, _, _, _ = native
    installer = SkillInstaller(SkillRegistry(global_root=tmp_path / "storage"))
    installer.install(root)
    reader = SkillReferenceReader(FilesystemReferenceStorage())
    binding = reader.activate(installer.info("python-clamp"), CancellationToken())
    assert len(binding.resources) == 2 and read(reader, binding)["complete_document"]
    installer.remove("python-clamp")
    rejected(ReferenceErrorCode.STALE, lambda: read(reader, binding))
    installer.storage_root.rename(tmp_path / "storage-released")
