from pathlib import Path
import sys

import pytest

from app.capabilities.project_verification import ProjectInspectCapability, ProjectInspectionArguments
from app.agent.bootstrap import build_agent_runtime
from app.agent.contracts import AgentRunStatus
from app.inference.protocol import ModelResponse
from app.settings.agent import AgentFeatureConfig
from tests.test_agent_runtime import run
from tests.test_bounded_edit_recovery import RoomyScriptedModel, call
from tests.test_project_verification import approved, free_port
from tests.test_filesystem_read_text import context


def fixture(tmp_path, *, wait, loaded=True, overlay=False):
    pytest.importorskip("playwright")
    state = Path(__file__).resolve().parents[1] / "state"
    if not (state / "playwright").is_dir():
        pytest.skip("Local Playwright browser is not installed")
    (tmp_path / "index.html").write_text("""<style>
        body {margin:0} #intro {height:1500px;background:#f00}
        #model {display:block;height:500px;width:500px;background:#0f0}
        </style><div id=intro>Intro</div><model-viewer id=model src=model.glb></model-viewer>
        <script>
        let locked=true;
        addEventListener('scroll',()=> {if(locked) scrollTo(0,0)});
        setTimeout(()=> {locked=false;document.querySelector('#intro').style.visibility='hidden'},1500);
        customElements.define('model-viewer',class extends HTMLElement {
            connectedCallback() {setTimeout(()=>{this.loaded=%s;this.modelIsVisible=%s},1000)}
        });
        %s
        </script>""" % (str(loaded).lower(), str(loaded).lower(),
            "customElements.define('vite-error-overlay',class extends HTMLElement {connectedCallback(){this.attachShadow({mode:'open'}).textContent='Failed to resolve import @google/model-viewer'}});document.body.appendChild(document.createElement('vite-error-overlay'));" if overlay else ""),
        encoding="utf-8")
    steps = ([{"action": "wait", "target": "#intro", "state": "hidden", "timeout_ms": 4000}] if wait else [])
    steps += [{"action": "in_view", "target": "#model"},
        {"action": "model_loaded", "target": "#model", "timeout_ms": 800}]
    return state, {"project_path": str(tmp_path), "kind": "browser", "url": f"http://127.0.0.1:{free_port()}/",
        "server_executable": str(Path(sys.executable).resolve()), "server_arguments": [], "steps": steps}


@pytest.mark.parametrize("wait,loaded,overlay,passed", [(True, True, False, True),
    (False, True, False, False), (True, False, False, False), (True, True, True, False)])
def test_intro_viewport_model_readiness_and_current_preview_error(tmp_path, wait, loaded, overlay, passed):
    state, args = fixture(tmp_path, wait=wait, loaded=loaded, overlay=overlay)
    port = args["url"].split(":")[-1].rstrip("/")
    args["server_arguments"] = ["-m", "http.server", port, "--bind", "127.0.0.1"]
    tool = ProjectInspectCapability(state)
    result = tool.invoke(args, approved(tool, args, context(tmp_path)))
    assert result.success, result.error
    output = result.output
    assert output.get("inspection_complete"), output
    assert output["passed"] is passed, output
    assert output["visual_verification_status"] == "requires_review"
    assert output["screenshot_sha256"] and output["screenshot_dimensions"] == [1280, 800]
    model = output["layout"]["models"][0]
    if wait:
        assert model["inViewport"] and output["capture_targets"][0]["in_viewport"]
        assert model["loaded"] is loaded
        if not loaded:
            assert not output["checks"][-1]["passed"]
    else:
        assert not output["checks"][0]["passed"]
        assert not output["capture_targets"][0]["in_viewport"]
    assert any(p["kind"] == "preview_error" for p in output["problems"]) is overlay


def test_real_inspector_delivers_pixels_to_runtime_continuation(tmp_path):
    from app.inference.local_images import image_accounting_messages
    from app.inference.protocol import native_chat_messages
    state, args = fixture(tmp_path, wait=True)
    args["server_arguments"] = ["-m", "http.server", args["url"].split(":")[-1].rstrip("/"), "--bind", "127.0.0.1"]
    class VisionModel(RoomyScriptedModel):
        supports_local_image_inputs = True
        def count_image_message_tokens(self, messages):
            image_accounting_messages(messages)
            return 2048
    model = VisionModel([call(1, "project.inspect", **args), ModelResponse.text("Observed the model section.")])
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True,
        project_inspect_enabled=True, context_recovery_enabled=True, conversation_context_enabled=True),
        portable_root=tmp_path, state_directory=tmp_path / "state")
    runtime.registry.resolve("project.inspect").state_directory = state
    runtime.set_tool_approval_required(False)
    result = run(runtime, tmp_path)
    assert result.status == AgentRunStatus.COMPLETED
    continuation = model.requests[1]
    native_chat_messages(continuation, model.definitions[1])
    assert continuation[-1]["role"] == "user"
    assert continuation[-1]["content"][-1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_in_view_preserves_a_scrolled_target_that_is_already_in_the_viewport(tmp_path):
    state, args = fixture(tmp_path, wait=False)
    (tmp_path / "index.html").write_text("""<style>
        body {margin:0} #hero {height:800px;background:#f00} #next {height:1000px;background:#0f0}
        </style><main id=hero>Scroll-driven animation</main><section id=next>Next section</section>""", encoding="utf-8")
    args["server_arguments"] = ["-m", "http.server", args["url"].split(":")[-1].rstrip("/"), "--bind", "127.0.0.1"]
    args["steps"] = [{"action": "scroll", "amount": 400}, {"action": "in_view", "target": "#hero"}]
    tool = ProjectInspectCapability(state)
    result = tool.invoke(args, approved(tool, args, context(tmp_path)))
    assert result.success and result.output["passed"], result
    output = result.output
    assert output["checks"][0]["scroll"]["after"] == 400
    assert output["layout"]["scrollTop"] == 400
    assert output["capture_targets"][0]["bounds"]["y"] == -400
    assert output["capture_targets"][0]["in_viewport"]


@pytest.mark.parametrize("extra", [{"steps": [{"action": "wait", "timeout_ms": 15001}]},
    {"steps": [{"action": "in_view"}]}, {"steps": [{"action": "model_loaded"}]},
    {"kind": "desktop", "url": None, "pid": 1, "steps": [{"action": "wait"}]}])
def test_readiness_steps_preserve_bounded_browser_scope(tmp_path, extra):
    with pytest.raises(ValueError):
        ProjectInspectionArguments.model_validate({"project_path": str(tmp_path), "kind": "browser", "url": "http://localhost/", **extra})
