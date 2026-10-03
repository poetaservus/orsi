from hashlib import sha1, sha256
import json
import os

import pytest

from app.runtime.skills import SkillInstaller, SkillRegistry, parse_skill, with_active_skill
from tests.simple_skill_live_validation import FIXTURE, assess_brand_reply, finalize_summary


def test_upstream_bytes_license_metadata_and_injection_are_preserved():
    manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    record = manifest["records"][0]
    data = (FIXTURE / "SKILL.md").read_bytes()
    assert len(data) == record["file_bytes"] == 2235
    assert sha256(data).hexdigest() == record["sha256"]
    assert sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == record["object_id"]
    assert sha256((FIXTURE / "LICENSE.txt").read_bytes()).hexdigest() == manifest["license_sha256"]
    skill = parse_skill(data.decode("utf-8"), root_path=FIXTURE, source_path=FIXTURE / "SKILL.md")
    assert skill.metadata == {"license": "Complete terms in LICENSE.txt"}
    assert len(skill.instructions.encode()) == record["body_bytes"]
    encoded = with_active_skill("CORE", skill).split("\nACTIVE SKILL\n", 1)[1].split("\nEND ACTIVE SKILL\n", 1)[0]
    assert json.loads(encoded) == {"name": skill.name, "instructions": skill.instructions}


@pytest.mark.skipif(os.name != "nt", reason="Native Windows skill installer")
def test_single_skill_installs_idempotently_and_releases_handles(tmp_path):
    installer = SkillInstaller(SkillRegistry(global_root=tmp_path / "skills"))
    assert installer.install(FIXTURE).installed == ("brand-guidelines",)
    assert installer.install(FIXTURE).already_installed == ("brand-guidelines",)
    assert installer.info("brand-guidelines").source_path.read_bytes() == (FIXTURE / "SKILL.md").read_bytes()
    assert [p.name for p in installer.info("brand-guidelines").root_path.iterdir()] == ["SKILL.md"]
    assert not installer.registry.report.issues
    installer.remove("brand-guidelines")
    assert installer.list() == ()
    installer.storage_root.rename(tmp_path / "released")


def test_css_assessment_requires_actual_color_properties_and_font_rules():
    colors = "#141413 #faf9f5 #b0aea5 #e8e6dc #d97757 #6a9bcc #788c5d"
    assert not assess_brand_reply("css", colors + " Poppins Arial Lora Georgia")["passed"]
    properties = "\n".join(f"--color-{i}: {color};" for i, color in enumerate(colors.split()))
    css = ":root {" + properties + "}\nh1 {font-family: Poppins, Arial;}\nbody {font-family: Lora, Georgia;}"
    assert assess_brand_reply("css", css)["passed"]
    assert not assess_brand_reply("css", css.replace("#788c5d", "#000000"))["passed"]
    assert not assess_brand_reply("css", css.replace("h1 {", ".caption {"))["passed"]


def test_blocked_requests_do_not_count_as_verified_injection_or_tool_catalog():
    summary = {"physical_requests": [], "routing": [{"passed": True}], "runs": [
        {"case_id": "css", "mode": "explicit", "active_skill": "brand-guidelines"},
        {"case_id": "tool", "mode": "explicit", "successful_stat_calls": 0}]}
    finalize_summary(summary)
    assert summary["skill_injection_exact"] is None
    assert summary["tool_catalog_unchanged"] is None
    assert summary["branding_passed"] is False
    assert summary["tool_probes_passed"] is False
