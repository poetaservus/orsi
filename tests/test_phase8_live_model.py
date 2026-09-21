from __future__ import annotations

import os
from pathlib import Path
from threading import Thread

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.settings.agent import AgentFeatureConfig
from app.execution.audit import CallLifecycleState
from app.security.host_access import HostAccessPolicy
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.settings.model import load_model_config


class RecordingLlamaServerInferenceEngine(LlamaServerInferenceEngine):
    """Capture normalized native calls for exact real-model routing assertions."""

    def __init__(self, config):
        super().__init__(config)
        self.observed_calls = []

    def respond_with_capabilities(self, messages, capabilities):
        response = super().respond_with_capabilities(messages, capabilities)
        self.observed_calls.extend(response.capability_calls)
        return response


@pytest.mark.skipif(
    os.environ.get("ORSI_RUN_LIVE_MODEL_TESTS") != "1",
    reason="Set ORSI_RUN_LIVE_MODEL_TESTS=1 for the bundled-model smoke test.",
)
def test_bundled_model_completes_a_filesystem_stat_round_trip(tmp_path: Path):
    """Opt-in smoke test: no scripted provider responses participate in this path."""
    portable_root = tmp_path / "portable"
    portable_root.mkdir()
    probe = portable_root / "phase8-live-probe.txt"
    probe.write_text("metadata-only live smoke", encoding="utf-8")
    state = tmp_path / "state"
    model = LlamaServerInferenceEngine(load_model_config())
    runtime = build_agent_runtime(
        model,
        config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=portable_root,
        state_directory=state,
    )
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=(portable_root,),
    )
    try:
        answer = service.run(
            "Use filesystem.stat to inspect phase8-live-probe.txt, then tell me its size."
        )

        assert answer.strip()
        records = runtime.executor.journal.records
        assert len(records) == 1, f"Bundled model answer without a stat record: {answer}"
        assert records[0].state == CallLifecycleState.COMPLETED
    finally:
        service.shutdown()
        model.close()


@pytest.mark.skipif(
    os.environ.get("ORSI_RUN_LIVE_MODEL_PATH_FIDELITY") != "1",
    reason="Set ORSI_RUN_LIVE_MODEL_PATH_FIDELITY=1 for the absolute-path gate.",
)
def test_bundled_model_preserves_absolute_in_root_paths(tmp_path: Path):
    """Real-model regression for natural absolute paths containing the root name."""
    portable_root = tmp_path / "orsi_test"
    portable_root.mkdir()
    state = tmp_path / "state"
    model = LlamaServerInferenceEngine(load_model_config())
    runtime = build_agent_runtime(
        model,
        config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=portable_root,
        state_directory=state,
    )
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=(portable_root,),
    )
    try:
        prompts = (
            "What's the metadata of {path}",
            "Please tell me the metadata for {path}.",
            'Can you inspect the metadata for this exact file: "{path}"?',
            "Get the file metadata of {path}",
            "What metadata does {path} have?",
        )
        for index in range(25):
            probe = portable_root / f"absolute-path-{index}.txt"
            expected_size = 170 + index
            probe.write_bytes(bytes([65 + index % 26]) * expected_size)
            answer = service.run(
                prompts[index % len(prompts)].format(path=probe)
            )

            records = runtime.executor.journal.records
            assert len(records) == 1, (index, answer, records)
            assert records[0].state == CallLifecycleState.COMPLETED
            assert str(expected_size) in answer
            service.new_session()
    finally:
        service.shutdown()
        model.close()


@pytest.mark.skipif(
    os.environ.get("ORSI_RUN_LIVE_MODEL_CONVERSATION") != "1",
    reason="Set ORSI_RUN_LIVE_MODEL_CONVERSATION=1 for the same-session chat gate.",
)
def test_bundled_model_keeps_general_conversation_after_metadata(tmp_path: Path):
    """Real-model regression: a tool turn must not make later chat metadata-only."""
    portable_root = tmp_path / "orsi_test"
    portable_root.mkdir()
    state = tmp_path / "state"
    model = LlamaServerInferenceEngine(load_model_config())
    runtime = build_agent_runtime(
        model,
        config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=portable_root,
        state_directory=state,
    )
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=(portable_root,),
    )
    try:
        recipe_prompts = (
            "Can you give me a recipe for pancakes?",
            "How do I make simple pancakes?",
            "Please give me an easy pancake recipe.",
        )
        for index in range(10):
            probe = portable_root / f"conversation-transition-{index}.txt"
            expected_size = 230 + index
            probe.write_bytes(bytes([65 + index % 26]) * expected_size)

            metadata_answer = service.run(
                f"What's the metadata of {probe}"
            )
            records = runtime.executor.journal.records
            assert len(records) == 1, (index, metadata_answer, records)
            assert records[0].state == CallLifecycleState.COMPLETED
            assert str(expected_size) in metadata_answer

            recipe_answer = service.run(
                recipe_prompts[index % len(recipe_prompts)]
            )
            assert runtime.executor.journal.records == records, (
                index,
                recipe_answer,
                runtime.executor.journal.records,
            )
            lowered = recipe_answer.casefold()
            assert "flour" in lowered
            assert sum(word in lowered for word in ("egg", "milk", "batter", "pan")) >= 2
            assert "provide me with a path" not in lowered
            assert "only provide information based on the metadata" not in lowered
            service.new_session()
    finally:
        service.shutdown()
        model.close()


@pytest.mark.skipif(
    os.environ.get("ORSI_RUN_LIVE_MODEL_ACCEPTANCE") != "1",
    reason="Set ORSI_RUN_LIVE_MODEL_ACCEPTANCE=1 for the 25/25 model gate.",
)
def test_bundled_model_native_tool_call_acceptance_matrix(tmp_path: Path):
    """Real-model gate: native calls, no-call chat, failures, and cancellation."""
    portable_root = tmp_path / "portable"
    portable_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside private body", encoding="utf-8")
    state = tmp_path / "state"
    model = LlamaServerInferenceEngine(load_model_config())
    runtime = build_agent_runtime(
        model,
        config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=portable_root,
        state_directory=state,
    )
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=(portable_root,),
    )
    try:
        for index in range(25):
            probe = portable_root / f"phase8-acceptance-{index}.txt"
            expected_size = 80 + index
            probe.write_bytes(bytes([65 + index % 26]) * expected_size)
            answer = service.run(
                "Use filesystem.stat exactly once to inspect "
                f"{probe.name}, then report its size in bytes."
            )
            records = runtime.executor.journal.records
            assert len(records) == 1, (index, answer, records)
            assert records[0].state == CallLifecycleState.COMPLETED
            assert str(expected_size) in answer
            service.new_session()

        for index in range(25):
            answer = service.run(
                f"This is ordinary conversation number {index}. "
                f"Reply exactly with chat-{index}; do not use a tool."
            )
            assert answer.strip()
            assert runtime.executor.journal.records == ()
            service.new_session()

        for index in range(5):
            answer = service.run(
                "Pass this exact path string to filesystem.stat once and let the "
                "capability decide whether it is allowed: "
                r"..\outside.txt"
            )
            records = runtime.executor.journal.records
            assert len(records) == 1, (index, answer, records)
            assert records[0].state == CallLifecycleState.DENIED
            service.new_session()

        for index in range(5):
            missing = f"missing-live-{index}.txt"
            answer = service.run(
                f"Use filesystem.stat exactly once to inspect {missing}."
            )
            records = runtime.executor.journal.records
            assert len(records) == 1, (index, answer, records)
            assert records[0].state == CallLifecycleState.FAILED
            service.new_session()

        for index in range(5):
            result: list[str] = []
            worker = Thread(
                target=lambda: result.append(
                    service.run(
                        "Write a detailed 1200-word essay about local inference "
                        f"for cancellation trial {index}. Do not use a tool."
                    )
                )
            )
            worker.start()
            assert model.wait_for_active_request(5.0)
            assert service.cancel_current_task()
            worker.join(5.0)
            assert not worker.is_alive()
            assert result == ["The response was stopped."]
            service.new_session()
    finally:
        service.shutdown()
        model.close()


@pytest.mark.skipif(
    os.environ.get("ORSI_RUN_PHASE9_LIVE_MODEL") != "1",
    reason="Set ORSI_RUN_PHASE9_LIVE_MODEL=1 for the Full local read model gate.",
)
def test_bundled_model_full_local_metadata_acceptance(tmp_path: Path):
    """Real-model gate for absolute host paths outside the portable application root."""
    portable_root = tmp_path / "portable"
    user_home = tmp_path / "host-user"
    host_project = tmp_path / "host-project"
    portable_root.mkdir()
    user_home.mkdir()
    host_project.mkdir()
    state = tmp_path / "state"
    policy = HostAccessPolicy.full_local(
        application_root=portable_root,
        user_home=user_home,
        acknowledged=True,
    )
    model = LlamaServerInferenceEngine(load_model_config())
    runtime = build_agent_runtime(
        model,
        config=AgentFeatureConfig(
            filesystem_stat_enabled=True,
            full_local_read_enabled=True,
        ),
        portable_root=portable_root,
        state_directory=state,
        host_access_policy=policy,
    )
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=policy.permission_roots(),
        host_access_policy=policy,
    )
    try:
        prompts = (
            "What's the metadata of {path}",
            "Please inspect this exact host file and report its size: {path}",
            'Use filesystem.stat once for "{path}" and report the byte size.',
            "Get the file metadata of {path}",
            "What metadata does {path} have?",
        )
        for index in range(25):
            probe = host_project / f"phase9-host-{index}.txt"
            expected_size = 310 + index
            probe.write_bytes(bytes([65 + index % 26]) * expected_size)
            answer = service.run(prompts[index % len(prompts)].format(path=probe))

            records = runtime.executor.journal.records
            assert len(records) == 1, (index, answer, records)
            assert records[0].state == CallLifecycleState.COMPLETED
            assert str(expected_size) in answer
            service.new_session()

        for index in range(25):
            answer = service.run(
                f"Ordinary Full local read conversation {index}. "
                f"Reply exactly with phase9-chat-{index}; do not use a tool."
            )
            assert answer.strip()
            assert runtime.executor.journal.records == ()
            service.new_session()
    finally:
        service.shutdown()
        model.close()


@pytest.mark.skipif(
    os.environ.get("ORSI_RUN_PHASE9_LIST_LIVE_MODEL") != "1",
    reason="Set ORSI_RUN_PHASE9_LIST_LIVE_MODEL=1 for the filesystem.list model gate.",
)
def test_bundled_model_full_local_directory_listing_acceptance(tmp_path: Path):
    """Real-model gate for bounded host directory listing and ordinary no-call chat."""
    portable_root = tmp_path / "portable"
    user_home = tmp_path / "host-user"
    host_directories = tmp_path / "host-directories"
    portable_root.mkdir()
    user_home.mkdir()
    host_directories.mkdir()
    state = tmp_path / "state"
    policy = HostAccessPolicy.full_local(
        application_root=portable_root,
        user_home=user_home,
        acknowledged=True,
    )
    model = LlamaServerInferenceEngine(load_model_config())
    runtime = build_agent_runtime(
        model,
        config=AgentFeatureConfig(
            filesystem_stat_enabled=True,
            filesystem_list_enabled=True,
            full_local_read_enabled=True,
        ),
        portable_root=portable_root,
        state_directory=state,
        host_access_policy=policy,
    )
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=policy.permission_roots(),
        host_access_policy=policy,
    )
    try:
        prompts = (
            "What files and folders are in this exact directory: {path}",
            "Use filesystem.list exactly once for {path} and report every returned name.",
            'List the names inside this host directory: "{path}"',
            "Show me what is in {path}",
            "Which files are present in {path}?",
        )
        for index in range(25):
            directory = host_directories / f"directory-{index}"
            directory.mkdir()
            expected_name = f"phase9-visible-{index}.txt"
            (directory / expected_name).write_text(
                "CONTENT-MUST-NOT-BE-READ",
                encoding="utf-8",
            )
            (directory / "Subfolder").mkdir()
            answer = service.run(
                prompts[index % len(prompts)].format(path=directory.resolve())
            )

            records = runtime.executor.journal.records
            assert len(records) == 1, (index, answer, records)
            assert records[0].capability == "filesystem.list"
            assert records[0].state == CallLifecycleState.COMPLETED
            assert expected_name.casefold() in answer.casefold()
            assert "CONTENT-MUST-NOT-BE-READ" not in answer
            service.new_session()

        for index in range(25):
            answer = service.run(
                f"Ordinary listing-enabled conversation {index}. "
                f"Reply exactly with list-chat-{index}; do not use a tool."
            )
            assert answer.strip()
            assert runtime.executor.journal.records == ()
            service.new_session()
    finally:
        service.shutdown()
        model.close()


@pytest.mark.skipif(
    os.environ.get("ORSI_RUN_PHASE9_READ_TEXT_LIVE_MODEL") != "1",
    reason="Set ORSI_RUN_PHASE9_READ_TEXT_LIVE_MODEL=1 for the filesystem.read_text model gate.",
)
def test_bundled_model_full_local_text_read_acceptance(tmp_path: Path):
    """Real-model gate for bounded text reading and ordinary no-call chat."""
    portable_root = tmp_path / "portable"
    user_home = tmp_path / "host-user"
    host_files = tmp_path / "host-files"
    portable_root.mkdir()
    user_home.mkdir()
    host_files.mkdir()
    state = tmp_path / "state"
    policy = HostAccessPolicy.full_local(
        application_root=portable_root,
        user_home=user_home,
        acknowledged=True,
    )
    model = LlamaServerInferenceEngine(load_model_config())
    runtime = build_agent_runtime(
        model,
        config=AgentFeatureConfig(
            filesystem_stat_enabled=True,
            filesystem_list_enabled=True,
            filesystem_read_text_enabled=True,
            full_local_read_enabled=True,
        ),
        portable_root=portable_root,
        state_directory=state,
        host_access_policy=policy,
    )
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=policy.permission_roots(),
        host_access_policy=policy,
    )
    try:
        prompts = (
            "Read this exact text file and show its contents: {path}",
            "Open {path} and tell me what it says.",
            'Show the contents of "{path}".',
            "Use filesystem.read_text exactly once for {path}.",
            "Summarize the text inside {path}.",
        )
        for index in range(25):
            target = host_files / f"read-target-{index}.txt"
            marker = f"PHASE9-READ-TEXT-MARKER-{index}"
            target.write_text(f"{marker}\nactual file content\n", encoding="utf-8")
            answer = service.run(prompts[index % len(prompts)].format(path=target.resolve()))

            records = runtime.executor.journal.records
            assert len(records) == 1, (index, answer, records)
            assert records[0].capability == "filesystem.read_text"
            assert records[0].state == CallLifecycleState.COMPLETED
            assert marker in answer
            assert "sample" not in answer.casefold()
            service.new_session()

        for index in range(25):
            answer = service.run(
                f"Ordinary text-read-enabled conversation {index}. "
                f"Reply exactly with read-chat-{index}; do not use a tool."
            )
            assert answer.strip()
            assert runtime.executor.journal.records == ()
            service.new_session()
    finally:
        service.shutdown()
        model.close()


@pytest.mark.skipif(
    os.environ.get("ORSI_RUN_PHASE9_SEARCH_LIVE_MODEL") != "1",
    reason="Set ORSI_RUN_PHASE9_SEARCH_LIVE_MODEL=1 for the filesystem.search model gate.",
)
def test_bundled_model_full_local_search_acceptance(tmp_path: Path):
    """Real-model gate for bounded text search and ordinary no-call chat."""
    portable_root = tmp_path / "portable"
    user_home = tmp_path / "host-user"
    host_directories = tmp_path / "host-directories"
    portable_root.mkdir()
    user_home.mkdir()
    host_directories.mkdir()
    state = tmp_path / "state"
    policy = HostAccessPolicy.full_local(
        application_root=portable_root,
        user_home=user_home,
        acknowledged=True,
    )
    model = LlamaServerInferenceEngine(load_model_config())
    runtime = build_agent_runtime(
        model,
        config=AgentFeatureConfig(
            filesystem_stat_enabled=True,
            filesystem_list_enabled=True,
            filesystem_read_text_enabled=True,
            filesystem_search_enabled=True,
            full_local_read_enabled=True,
        ),
        portable_root=portable_root,
        state_directory=state,
        host_access_policy=policy,
    )
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=policy.permission_roots(),
        host_access_policy=policy,
    )
    try:
        prompts = (
            "Search for {marker} in {path}",
            "Find {marker} inside {path}",
            "Search {path} for {marker}",
            'Find "{marker}" inside "{path}"',
            "Use filesystem.search for {marker} in {path}",
        )
        for index in range(25):
            directory = host_directories / f"directory-{index}"
            directory.mkdir()
            marker = f"PHASE9-SEARCH-MARKER-{index}"
            expected_file = directory / "target.txt"
            expected_file.write_text(f"alpha {marker} omega\n", encoding="utf-8")
            (directory / "other.txt").write_text("no marker here\n", encoding="utf-8")
            answer = service.run(
                prompts[index % len(prompts)].format(
                    marker=marker,
                    path=directory.resolve(),
                )
            )

            records = runtime.executor.journal.records
            assert len(records) == 1, (index, answer, records)
            assert records[0].capability == "filesystem.search"
            assert records[0].state == CallLifecycleState.COMPLETED
            assert marker in answer
            assert "target.txt" in answer
            service.new_session()

        for index in range(25):
            answer = service.run(
                f"Ordinary search-enabled conversation {index}. "
                f"Reply exactly with search-chat-{index}; do not use a tool."
            )
            assert answer.strip()
            assert runtime.executor.journal.records == ()
            service.new_session()
    finally:
        service.shutdown()
        model.close()


@pytest.mark.skipif(
    os.environ.get("ORSI_RUN_PHASE9_LIST_LIVE_MODEL") != "1",
    reason="Set ORSI_RUN_PHASE9_LIST_LIVE_MODEL=1 for the filesystem.list model gate.",
)
def test_bundled_model_uses_stat_after_a_directory_listing(tmp_path: Path):
    """Real-model regression for list-to-metadata follow-up tool selection."""
    portable_root = tmp_path / "portable"
    user_home = tmp_path / "host-user"
    host_directory = tmp_path / "lab"
    portable_root.mkdir()
    user_home.mkdir()
    host_directory.mkdir()
    expected_sizes: dict[str, int] = {}
    for index, name in enumerate(
        ("3.jpg", "4.jpg", "6.jpg", "fixed_v1.txt", "wokr.py", "work_css.txt"),
        start=1,
    ):
        content = "x" * index
        (host_directory / name).write_text(content, encoding="utf-8")
        expected_sizes[name] = len(content)

    state = tmp_path / "state"
    policy = HostAccessPolicy.full_local(
        application_root=portable_root,
        user_home=user_home,
        acknowledged=True,
    )
    model = LlamaServerInferenceEngine(load_model_config())
    runtime = build_agent_runtime(
        model,
        config=AgentFeatureConfig(
            filesystem_stat_enabled=True,
            filesystem_list_enabled=True,
            full_local_read_enabled=True,
        ),
        portable_root=portable_root,
        state_directory=state,
        host_access_policy=policy,
    )
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=policy.permission_roots(),
        host_access_policy=policy,
    )
    try:
        listing_answer = service.run(
            f"What files do I have in this exact directory: {host_directory.resolve()}"
        )
        assert all(name.casefold() in listing_answer.casefold() for name in expected_sizes)
        assert [record.capability for record in runtime.executor.journal.records] == [
            "filesystem.list"
        ]

        metadata_answer = service.run("Can you tell me the metadata of each file?")

        records = runtime.executor.journal.records
        capabilities = [record.capability for record in records]
        assert capabilities.count("filesystem.list") == 1, metadata_answer
        assert capabilities.count("filesystem.stat") == len(expected_sizes), metadata_answer
        assert len(capabilities) == len(expected_sizes) + 1, metadata_answer
        assert all(record.state == CallLifecycleState.COMPLETED for record in records)
        lowered = metadata_answer.casefold()
        assert all(name.casefold() in lowered for name in expected_sizes)
        assert all(f"{size} bytes" in lowered for size in expected_sizes.values())
    finally:
        service.shutdown()
        model.close()


@pytest.mark.skipif(
    os.environ.get("ORSI_RUN_PHASE9_LIST_LIVE_MODEL") != "1",
    reason="Set ORSI_RUN_PHASE9_LIST_LIVE_MODEL=1 for the filesystem.list model gate.",
)
@pytest.mark.parametrize("_live_repeat", range(3))
def test_bundled_model_switches_naturally_between_chat_and_filesystem_tasks(
    tmp_path: Path,
    _live_repeat: int,
):
    """Real-model regression for the manually reported chat/task/chat workflow."""
    portable_root = tmp_path / "portable"
    user_home = tmp_path / "host-user"
    host_directory = tmp_path / "lab"
    portable_root.mkdir()
    user_home.mkdir()
    host_directory.mkdir()
    expected_sizes = {
        "3.jpg": 101,
        "4.jpg": 202,
        "6.jpg": 303,
        "fixed_v1.txt": 404,
        "wokr.py": 505,
        "work_css.txt": 606,
    }
    for name, size in expected_sizes.items():
        (host_directory / name).write_bytes(b"x" * size)

    state = tmp_path / "state"
    policy = HostAccessPolicy.full_local(
        application_root=portable_root,
        user_home=user_home,
        acknowledged=True,
    )
    model = RecordingLlamaServerInferenceEngine(load_model_config())
    runtime = build_agent_runtime(
        model,
        config=AgentFeatureConfig(
            filesystem_stat_enabled=True,
            filesystem_list_enabled=True,
            full_local_read_enabled=True,
        ),
        portable_root=portable_root,
        state_directory=state,
        host_access_policy=policy,
    )
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=policy.permission_roots(),
        host_access_policy=policy,
    )
    try:
        chat = (
            "hello",
            "how are you today?",
            "can you tell me a fun fact about Hungary",
            "yes",
            "really? I didn't know this",
        )
        for prompt in chat:
            before = len(model.observed_calls)
            answer = service.run(prompt)
            assert len(model.observed_calls) == before, (prompt, answer)
            lowered = answer.casefold()
            assert "couldn't find a file" not in lowered
            assert "couldn't find a directory" not in lowered
            assert "fun_facts.txt" not in lowered
            if prompt == "how are you today?":
                assert "just a program" not in lowered
                assert "don't have feelings" not in lowered
        assert runtime.executor.journal.records == ()

        before_records = len(runtime.executor.journal.records)
        listing_answer = service.run(
            f"can you tell me what files I have in {host_directory.resolve()}"
        )
        listing_records = runtime.executor.journal.records
        assert len(listing_records) - before_records == 1, listing_answer
        assert sum(record.capability == "filesystem.list" for record in listing_records) == 1
        assert all(name.casefold() in listing_answer.casefold() for name in expected_sizes)

        first_selected = {"work_css.txt"}
        before_records = len(runtime.executor.journal.records)
        selected_answer = service.run(
            "can you tell me the metadata of work_css.txt"
        )
        selected_records = runtime.executor.journal.records
        assert len(selected_records) - before_records == 1, selected_answer
        assert sum(record.capability == "filesystem.stat" for record in selected_records) == 1
        lowered = selected_answer.casefold()
        assert all(name in lowered for name in first_selected)
        assert all(f"{expected_sizes[name]:,} bytes" in lowered for name in first_selected)

        continuation = {"fixed_v1.txt"}
        before_records = len(runtime.executor.journal.records)
        continuation_answer = service.run("and for fixed_v1.txt as well please")
        continuation_records = runtime.executor.journal.records
        assert len(continuation_records) - before_records == 1, continuation_answer
        assert sum(
            record.capability == "filesystem.stat" for record in continuation_records
        ) == 2
        lowered = continuation_answer.casefold()
        assert all(name in lowered for name in continuation)
        assert all(f"{expected_sizes[name]:,} bytes" in lowered for name in continuation)

        selected = first_selected | continuation

        remaining = set(expected_sizes) - selected
        before_records = len(runtime.executor.journal.records)
        remaining_answer = service.run(
            "now can you tell me the metadata of the rest of the files there?"
        )
        remaining_records = runtime.executor.journal.records
        assert len(remaining_records) - before_records == len(remaining), remaining_answer
        assert sum(record.capability == "filesystem.stat" for record in remaining_records) == 6
        lowered = remaining_answer.casefold()
        assert all(name in lowered for name in remaining)
        assert all(f"{expected_sizes[name]:,} bytes" in lowered for name in remaining)

        records = runtime.executor.journal.records
        assert sum(record.capability == "filesystem.list" for record in records) == 1
        assert sum(record.capability == "filesystem.stat" for record in records) == 6
        assert all(record.state == CallLifecycleState.COMPLETED for record in records)

        for prompt in (
            "thanks. now tell me another fun fact about Hungary",
            "really? that's interesting",
            "how are you now?",
        ):
            before = len(model.observed_calls)
            answer = service.run(prompt)
            assert len(model.observed_calls) == before, (prompt, answer)
            lowered = answer.casefold()
            assert "couldn't find" not in lowered
            assert "just a program" not in lowered
    finally:
        service.shutdown()
        model.close()
