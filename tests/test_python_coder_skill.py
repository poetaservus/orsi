"""Validate the authored package through installation, retrieval and live examples."""
import asyncio
import json
import os
from pathlib import Path
import re

import pytest

from app.runtime.cancellation import CancellationToken
from app.runtime.skills import SkillInstaller, SkillRegistry
from app.runtime.skills.reference_reader import SkillReferenceReader
from app.runtime.skills.reference_storage import FilesystemReferenceStorage


PACKAGE = Path(__file__).resolve().parents[1] / "skills" / "python-coder"


def example_namespace(filename):
    text = (PACKAGE / "references" / filename).read_text(encoding="utf-8")
    blocks = re.findall(r"^```python\n(.*?)^```$", text, re.MULTILINE | re.DOTALL)
    assert blocks, f"No executable example in {filename}"
    namespace = {"__name__": "python_coder_reference_example"}
    for block in blocks:
        exec(compile(block, filename, "exec"), namespace)
    return namespace


def test_package_local_links_and_python_examples_are_valid():
    files = [PACKAGE / "SKILL.md", *sorted((PACKAGE / "references").glob("*.md"))]
    for path in files:
        text = path.read_text(encoding="utf-8")
        for link in re.findall(r"\]\(([^)]+)\)", text):
            if link.startswith(("https://", "http://")):
                continue
            destination = (path.parent / link.split("#", 1)[0]).resolve()
            assert destination.is_relative_to(PACKAGE.resolve())
            assert destination.is_file(), (path, link)
        for block in re.findall(r"^```python\n(.*?)^```$", text, re.MULTILINE | re.DOTALL):
            compile(block, str(path), "exec")


@pytest.mark.skipif(os.name != "nt", reason="Native O.R.S.I. package snapshots require Windows")
def test_package_installs_and_all_references_round_trip_with_bounded_continuation(tmp_path):
    installer = SkillInstaller(SkillRegistry(global_root=tmp_path / "skills"))
    result = installer.install(PACKAGE)
    assert result.installed == ("python-coder",)
    skill = installer.info("python-coder")
    reader = SkillReferenceReader(FilesystemReferenceStorage())
    token = CancellationToken()
    binding = reader.activate(skill, token)
    assert {resource.path for resource in binding.resources} == {
        path.relative_to(PACKAGE).as_posix() for path in (PACKAGE / "references").glob("*.md")
    }
    for resource in binding.resources:
        expected = (PACKAGE / resource.path).read_bytes()
        offset, chunks = 0, []
        while True:
            page = reader.read(binding, resource.path, version=binding.version,
                               cancellation=token, offset=offset, max_bytes=4096, max_lines=80)
            assert page["path"] == resource.path and page["bytes_returned"] <= 4096
            chunks.append(page["text"].encode("utf-8"))
            if not page["has_more"]:
                break
            assert page["next_offset"] > offset
            offset = page["next_offset"]
        assert b"".join(chunks) == expected
    assert installer.install(PACKAGE).already_installed == ("python-coder",)


@pytest.mark.parametrize("value, expected", [(1, 1), (65535, 65535), ("80", 80), ("00080", 80)])
def test_port_example_accepts_its_documented_forms(value, expected):
    parse = example_namespace("20-types-and-contracts.md")["parse_port"]
    assert parse(value) == expected


@pytest.mark.parametrize("value", [True, False, 80.0, None, " 80", "\u0668\u0660", "", [], {}])
def test_port_example_rejects_coercion_and_wrong_types(value):
    parse = example_namespace("20-types-and-contracts.md")["parse_port"]
    with pytest.raises(TypeError):
        parse(value)


@pytest.mark.parametrize("value", [0, -1, 65536, "0", "99999", "9" * 10000])
def test_port_example_rejects_out_of_range_or_oversized_input(value):
    parse = example_namespace("20-types-and-contracts.md")["parse_port"]
    with pytest.raises(ValueError):
        parse(value)


def test_save_example_successfully_round_trips_unicode_without_leaving_temporary_files(tmp_path):
    save = example_namespace("30-errors-and-resources.md")["save_json"]
    target = tmp_path / "settings.json"
    value = {"title": "caf\u00e9", "enabled": False, "items": [1, 2]}
    save(target, value)
    assert json.loads(target.read_text(encoding="utf-8")) == value
    assert list(tmp_path.iterdir()) == [target]


def test_save_example_invalid_data_does_not_replace_previous_state(tmp_path):
    save = example_namespace("30-errors-and-resources.md")["save_json"]
    target = tmp_path / "settings.json"
    target.write_text("original", encoding="utf-8")
    with pytest.raises(ValueError):
        save(target, {"rate": float("nan")})
    assert target.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.iterdir()) == [target]


def test_documented_failure_preservation_test_exercises_the_real_save_example(tmp_path, monkeypatch):
    namespace = example_namespace("30-errors-and-resources.md")
    text = (PACKAGE / "references" / "40-testing.md").read_text(encoding="utf-8")
    block = re.findall(r"^```python\n(.*?)^```$", text, re.MULTILINE | re.DOTALL)[0]
    exec(compile(block, "40-testing.md", "exec"), namespace)
    namespace["test_failed_replace_preserves_data"](tmp_path, monkeypatch)


def test_save_example_retains_primary_failure_when_cleanup_also_fails(tmp_path, monkeypatch):
    save = example_namespace("30-errors-and-resources.md")["save_json"]
    target = tmp_path / "settings.json"
    target.write_text("original", encoding="utf-8")

    def fail_replace(source, destination):
        raise PermissionError("replace failed")

    def fail_unlink(self, **kwargs):
        raise OSError("cleanup failed")

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", fail_replace)
        scoped.setattr(Path, "unlink", fail_unlink)
        with pytest.raises(PermissionError, match="replace failed") as failure:
            save(target, {"value": "new"})
        assert failure.value.__notes__ == ["temporary file cleanup also failed"]
    assert target.read_text(encoding="utf-8") == "original"
    for temporary in tmp_path.glob(".save-*.tmp"):
        temporary.unlink()


def test_structured_concurrency_example_returns_both_completed_results():
    run_pair = example_namespace("50-concurrency.md")["run_pair"]
    assert asyncio.run(run_pair()) == (2, 3)
