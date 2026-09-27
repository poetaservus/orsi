from __future__ import annotations

import os
import re

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.capability_routing import select_turn_capabilities
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.security.host_access import HostAccessPolicy
from app.settings.agent import load_agent_feature_config
from app.settings.model import load_model_config


CATALOG = ("filesystem.stat", "filesystem.list", "filesystem.read_text",
           "filesystem.write_text", "filesystem.edit_text")


@pytest.mark.parametrize("prompt", [
    "implement this into my style.css",
    "great, please add the javascript to the script.js file",
    "apply these changes to the file",
    "append the code to script.js",
    "add a gradient in the header in style.css",
])
def test_apply_code_to_file_exposes_approved_compact_edit(prompt):
    names = select_turn_capabilities(prompt, CATALOG)
    assert "filesystem.edit_text" in names
    assert "filesystem.read_text" in names
    assert "filesystem.write_text" not in names


def test_apply_code_preserves_legacy_write_fallback():
    available = tuple(name for name in CATALOG if name != "filesystem.edit_text")
    names = select_turn_capabilities("implement this into my style.css", available)
    assert "filesystem.write_text" in names
    assert "filesystem.read_text" in names


def test_ordinary_implementation_discussion_does_not_advertise_edits():
    assert select_turn_capabilities("how do teams implement an idea?", CATALOG) == ("filesystem.stat",)


@pytest.mark.skipif(os.name != "nt" or os.environ.get("ORSI_RUN_PHASE1_RESTORE") != "1",
                    reason="Opt-in real local-model restore acceptance.")
def test_local_model_implements_suggested_css_with_shipped_config(tmp_path):
    portable = tmp_path / "portable"
    portable.mkdir()
    website = tmp_path / "Documents" / "website"
    website.mkdir(parents=True)
    target = website / "style.css"
    target.write_bytes(b"body { color: white; background: #222; }\n"
                       b".faq-item { max-height: 0; overflow: hidden; opacity: 0; }\n"
                       b".faq-item.open { max-height: 200px; opacity: 1; }\n")
    model = LlamaServerInferenceEngine(load_model_config())
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path,
                                         acknowledged=True)
    config = load_agent_feature_config()
    assert config.filesystem_edit_text_enabled
    runtime = build_agent_runtime(model, config=config, portable_root=portable,
                                   state_directory=portable / "state", host_access_policy=policy)
    store = ConversationStore(portable / "conversation.json")
    store.append("user", "there is a folder in my documents called website list the files there please")
    store.append("assistant", f"The website folder at {website} contains index.html, script.js, and style.css.")
    store.append("user", "edit style.css to make the FAQ menu open and close smoothly")
    store.append("assistant", "Use this transition on .faq-item to animate the existing open/closed states:\n"
                 "```css\n.faq-item { max-height: 0; overflow: hidden; opacity: 0; "
                 "transition: max-height 0.3s ease, opacity 0.3s ease; }\n```")
    service = ConversationService(model, store, agent_runtime=runtime, portable_root=portable,
                                   host_access_policy=policy)
    approvals = []

    def approve(record):
        assert record.capability == "filesystem.edit_text"
        assert record.resource == str(target)
        approvals.append(record.approval_id)
        service.resolve_approval(record.approval_id, True)

    service.set_approval_requester(approve)
    try:
        service.run("implement this into my style.css")
        content = target.read_text(encoding="utf-8")
        assert "transition:" in content and "max-height 0.3s ease" in content
        assert "body { color: white; background: #222; }" in content
        assert approvals
        records = runtime.executor.journal.records
        assert any(r.capability == "filesystem.read_text" and r.result_success for r in records)
        assert any(r.capability == "filesystem.edit_text" and r.result_success for r in records)
        assert not any(r.capability == "filesystem.write_text" for r in records)
    finally:
        service.shutdown()
        model.close()


@pytest.mark.skipif(os.name != "nt" or os.environ.get("ORSI_RUN_PHASE1_RESTORE") != "1",
                    reason="Opt-in real local-model restore acceptance.")
@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_local_model_targets_header_among_repeated_css_declarations(tmp_path, newline):
    portable = tmp_path / "portable"
    portable.mkdir()
    website = tmp_path / "Documents" / "website"
    website.mkdir(parents=True)
    target = website / "style.css"
    header = "header {\n  text-align: center;\n  padding: 40px 20px;\n  background-color: #2f2f2f;\n}\n"
    prefix = "body {\n  background-color: #2f2f2f;\n  color: #ffffff;\n}\n\n"
    # Repeated declarations and content beyond the default 200-line read expose
    # the failure missed by the earlier tiny, seeded-conversation fixture.
    suffix = "\n" + "".join(f".section-{i} {{\n  background-color: #2f2f2f;\n}}\n" for i in range(10))
    suffix += "".join(f".item-{i} {{ margin: {i}px; }}\n" for i in range(275))
    raw = (prefix + header + suffix).replace("\n", newline).encode()
    target.write_bytes(raw)
    (website / "index.html").write_text("<!doctype html><header><h1>Example</h1></header>", encoding="utf-8")
    (website / "script.js").write_text("// Example", encoding="utf-8")
    model = LlamaServerInferenceEngine(load_model_config())
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(model, config=load_agent_feature_config(), portable_root=portable,
                                   state_directory=portable / "state", host_access_policy=policy)
    service = ConversationService(model, ConversationStore(portable / "conversation.json"),
                                   agent_runtime=runtime, portable_root=portable, host_access_policy=policy)
    approvals = []

    def approve(record):
        assert record.capability == "filesystem.edit_text" and record.resource == str(target)
        assert target.read_bytes() == raw
        approvals.append(record)
        service.resolve_approval(record.approval_id, True)

    service.set_approval_requester(approve)
    try:
        service.run("there is a folder in my documents called website list the items there\\")
        service.run("add a gradient in the header in style.css")
        edited = target.read_bytes().decode()
        changed_header = re.search(r"(?m)^header \{[^}]+\}" + re.escape(newline), edited)
        assert changed_header and "gradient(" in changed_header.group()
        assert edited.replace(changed_header.group(), header.replace("\n", newline), 1).encode() == raw
        assert len(approvals) == 1
        records = runtime.executor.journal.records
        assert any(r.capability == "filesystem.list" and r.result_success for r in records)
        assert any(r.capability == "filesystem.read_text" and r.result_success for r in records)
        assert sum(r.capability == "filesystem.edit_text" and r.result_success for r in records) == 1
        assert not any(r.capability == "filesystem.write_text" for r in records)
    finally:
        service.shutdown()
        model.close()
