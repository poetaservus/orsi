"""Pinned, unmodified upstream data through native import and context boundaries."""
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.engine import InferenceEngine
from app.runtime.skills import SkillInstaller, SkillRegistry, SkillActivationError, with_active_skill, parse_skill
from tests.fixtures.tasteskill_cases import FRONTEND_TASKS


FIXTURE = Path(__file__).parent / "fixtures" / "tasteskill"
MANIFEST = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("item", MANIFEST["records"], ids=lambda item: item["name"])
def test_upstream_file_is_byte_exact_and_metadata_is_supported(item):
    source = FIXTURE / item["path"]
    data = source.read_bytes()
    assert len(data) == item["file_bytes"]
    assert sha256(data).hexdigest() == item["sha256"]
    # Verify the Git object ID as well, including Git's blob header.
    from hashlib import sha1
    assert sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == item["object_id"]
    skill = parse_skill(data.decode("utf-8"), root_path=source.parent, source_path=source)
    assert skill.name == item["name"] and skill.description.strip()
    assert sorted(skill.metadata) == item["metadata_keys"] == []
    assert len(skill.instructions.encode("utf-8")) == item["body_bytes"]
    rendered = with_active_skill("CORE POLICY", skill)
    encoded = rendered.split("\nACTIVE SKILL\n", 1)[1].split("\nEND ACTIVE SKILL\n", 1)[0]
    assert json.loads(encoded) == {"name": skill.name, "instructions": skill.instructions}
    assert rendered.startswith("CORE POLICY")


@pytest.mark.skipif(os.name != "nt", reason="Native Windows skill installer")
def test_pinned_bundle_installs_reinstalls_and_removes_without_resources(tmp_path):
    installer = SkillInstaller(SkillRegistry(global_root=tmp_path / "skills"))
    result = installer.install(FIXTURE / "skills")
    names = tuple(sorted(item["name"] for item in MANIFEST["records"]))
    assert len(names) == 13 and result.installed == names
    assert not installer.registry.report.issues
    assert installer.install(FIXTURE / "skills").already_installed == names
    for item in MANIFEST["records"]:
        stored = installer.info(item["name"])
        assert stored.source_path.read_bytes() == (FIXTURE / item["path"]).read_bytes()
        assert [path.name for path in stored.root_path.iterdir()] == ["SKILL.md"]
    for name in names:
        installer.remove(name)
    assert installer.list() == ()
    installer.storage_root.rename(tmp_path / "handles-released")


class BoundedBackend(InferenceEngine):
    context_length = 16384
    max_response_tokens = 4096

    def __init__(self):
        self.requests = []

    def respond(self, messages):
        self.requests.append(messages)
        if messages[0]["content"].startswith("Choose zero or one instruction skill"):
            return '{"skill":"design-taste-frontend"}'
        return "Deterministic admission fixture."


@pytest.mark.skipif(os.name != "nt", reason="Native Windows skill loader")
def test_large_upstream_skill_is_dropped_automatically_and_rejected_explicitly(tmp_path):
    registry = SkillRegistry(global_root=tmp_path / "skills")
    installer = SkillInstaller(registry)
    installer.install(FIXTURE / "skills" / "taste-skill")
    backend = BoundedBackend()
    service = ConversationService(backend, ConversationStore(tmp_path / "conversation.json"),
                                  skill_registry=registry)
    try:
        assert service.run(FRONTEND_TASKS[0][1]) == "Deterministic admission fixture."
        assert service.skill_selection.reason == "skill_context_limit"
        assert service.active_skill is None
        assert len(backend.requests) == 2
        assert "\nACTIVE SKILL\n" not in backend.requests[-1][0]["content"]
        assert backend.requests[-1][-1]["content"] == FRONTEND_TASKS[0][1]
        service.new_session()
        service.activate_skill("design-taste-frontend")
        before = len(backend.requests)
        with pytest.raises(SkillActivationError) as error:
            service.run(FRONTEND_TASKS[0][1])
        assert error.value.code.value == "context_limit"
        assert len(backend.requests) == before
    finally:
        service.shutdown()


@pytest.mark.parametrize("mode_fields", [
    {"routing_passed": False, "automatic_frontend_passed": False},
    {"tool_catalog_unchanged": True, "smaller_skill_tool_probe_passed": True},
])
def test_live_audit_report_supports_both_modes_without_raw_content(mode_fields, capsys):
    from tests.tasteskill_live_validation import print_summary
    report = {"qualification_passed": False, "owned_server_exited": True,
              "raw_reply": "PRIVATE", "raw_skill_body": "PRIVATE", **mode_fields}
    print_summary(report)
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result == {key: value for key, value in report.items() if not key.startswith("raw_")}
    assert "PRIVATE" not in output
