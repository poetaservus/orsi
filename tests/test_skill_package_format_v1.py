"""The tiny authored pack is compatible; Phase 1 adds no resource loading."""
import json
import os
from pathlib import Path

import pytest

from app.runtime.skills import SkillInstaller, SkillRegistry, parse_skill, with_active_skill


FIXTURE = Path(__file__).parent / "fixtures" / "skill_package_v1" / "python-clamp"


def test_entry_point_remains_plain_skill_guidance_without_reference_injection():
    text = (FIXTURE / "SKILL.md").read_text(encoding="utf-8")
    skill = parse_skill(text, root_path=FIXTURE, source_path=FIXTURE / "SKILL.md")
    assert skill.name == "python-clamp"
    assert skill.metadata == {}
    assert skill.instructions == text.split("---\n", 2)[2]
    prompt = with_active_skill("CORE", skill)
    payload = json.loads(prompt.split("\nACTIVE SKILL\n", 1)[1].split("\nEND ACTIVE SKILL\n", 1)[0])
    assert payload == {"name": "python-clamp", "instructions": skill.instructions}
    assert "references/behavior.md" in prompt
    assert "lower exceeds upper" not in prompt
    assert "assert clamp(-2, 0, 3) == 0" not in prompt


def test_tiny_pack_has_resolvable_entry_and_document_relative_links():
    main = (FIXTURE / "SKILL.md").read_text(encoding="utf-8")
    behavior = FIXTURE / "references" / "behavior.md"
    checks = FIXTURE / "references" / "checks.md"
    assert "[Behavior](references/behavior.md)" in main
    assert "[Checks](references/checks.md)" in main
    assert "[Behavior](behavior.md)" in checks.read_text(encoding="utf-8")
    assert (checks.parent / "behavior.md").resolve() == behavior.resolve()
    files = tuple(FIXTURE.rglob("*.md"))
    assert len(files) == 3
    assert sum(path.stat().st_size for path in files) < 2048
    for path in files:
        text = path.read_text(encoding="ascii")
        assert len(text.split()) <= (150 if path.name == "SKILL.md" else 100)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows skill installer")
def test_current_installer_preserves_entry_point_without_claiming_package_support(tmp_path):
    installer = SkillInstaller(SkillRegistry(global_root=tmp_path / "skills"))
    assert installer.install(FIXTURE).installed == ("python-clamp",)
    installed = installer.info("python-clamp")
    assert installed.source_path.read_bytes() == (FIXTURE / "SKILL.md").read_bytes()
    assert [path.name for path in installed.root_path.iterdir()] == ["SKILL.md"]
    assert installer.install(FIXTURE).already_installed == ("python-clamp",)
    installer.remove("python-clamp")
    assert installer.list() == ()
