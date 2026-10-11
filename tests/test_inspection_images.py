import base64
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.inspection_images import inspection_image_message
from app.capabilities.contracts import CapabilityResult
from app.capabilities.project_verification import ProjectInspectCapability
from app.inference.hybrid import HybridInferenceEngine
from app.inference.openai_tools import responses_input
from app.inference.protocol import native_chat_messages
from tests.test_attachment_processing import image_data
from tests.test_cloud_attachment_input import native_sdk
from tests.test_cloud_inference import capability_definition


def screenshot(tmp_path):
    tool = ProjectInspectCapability(tmp_path)
    path = tmp_path / "verification" / "capture" / "screenshot.png"
    path.parent.mkdir(parents=True)
    data = image_data()
    path.write_bytes(data)
    result = CapabilityResult(call_id="receipt-1", capability="project.inspect", success=True, duration_ms=0,
        output={"screenshot_path": str(path), "screenshot_sha256": sha256(data).hexdigest()})
    return tool, result, data


@pytest.mark.parametrize("mode", ["local", "cloud"])
def test_verified_pixels_reach_native_model_input(tmp_path, mode, native_sdk):
    tool, result, data = screenshot(tmp_path)
    model = SimpleNamespace(supports_local_image_inputs=mode == "local", supports_native_attachment_tools=mode == "cloud")
    message = inspection_image_message(tool, result, model)
    assert "not a new user request" in message["content"][0]["text"]
    definition = capability_definition()
    if mode == "local":
        native = native_chat_messages([message], [definition])
        url = native[0]["content"][1]["image_url"]["url"]
    else:
        backend, counts, generations, _ = native_sdk()
        hybrid = HybridInferenceEngine(local=None, cloud=backend, default_mode="cloud", fallback_to_local=False)
        assert 16384 < hybrid.count_image_message_tokens([message]) < 18000
        hybrid.respond_with_capabilities([message], [definition])
        assert len(counts) == len(generations) == 1
        assert counts[0]["input"] == generations[0]["input"]
        url = generations[0]["input"][0]["content"][1]["image_url"]
        assert generations[0]["input"][0]["content"][1]["type"] == "input_image"
    assert base64.b64decode(url.split(",", 1)[1]) == data


@pytest.mark.parametrize("condition", ["unsupported", "changed", "outside", "symlink"])
def test_unavailable_or_untrusted_screenshot_never_becomes_image_input(tmp_path, condition):
    tool, result, _ = screenshot(tmp_path)
    if condition == "changed":
        Path(result.output["screenshot_path"]).write_bytes(b"changed")
    elif condition == "outside":
        result.output["screenshot_path"] = str(tmp_path / "private.png")
    elif condition == "symlink":
        path = Path(result.output["screenshot_path"])
        target = tmp_path / "other.png"
        path.replace(target)
        try:
            path.symlink_to(target)
        except OSError:
            pytest.skip("Host does not permit symlinks")
    message = inspection_image_message(tool, result, SimpleNamespace(supports_local_image_inputs=condition != "unsupported"))
    assert message["role"] == "system" and "unverified" in message["content"]
    assert not isinstance(message["content"], list)


def test_screenshot_supplement_preserves_tool_pairing(tmp_path):
    from app.inference.protocol import ModelCapabilityCall, model_capability_calls_message, model_capability_result_message
    tool, result, _ = screenshot(tmp_path)
    definition = capability_definition()
    call = ModelCapabilityCall(provider_call_id="call-1", capability=definition.name, arguments={"path": "probe.txt"})
    receipt = result.model_copy(update={"capability": definition.name})
    transcript = [model_capability_calls_message((call,)), model_capability_result_message(call, receipt.model_dump(mode="json")),
        inspection_image_message(tool, result, SimpleNamespace(supports_local_image_inputs=True))]
    wire = responses_input(transcript, [definition])
    assert [item.get("type", item.get("role")) for item in wire] == ["function_call", "function_call_output", "user"]
