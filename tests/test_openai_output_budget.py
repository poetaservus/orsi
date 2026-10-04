"""A large file's content must fit in a complete native write call."""
from app.capabilities.filesystem_write_text import FilesystemWriteTextArguments
from app.inference.protocol import ModelCapabilityDefinition, ModelResponseKind, ModelProtocolFailureCode
from app.settings.cloud import load_cloud_config
from tests.test_openai_phase1 import response
from tests.test_openai_tools import function, scripted_sdk


def definition():
    return ModelCapabilityDefinition(name="filesystem.write_text", description="Write text after approval.",
                                    input_schema=FilesystemWriteTextArguments.model_json_schema())


def test_large_complete_write_call_uses_expanded_checked_in_luna_budget(monkeypatch):
    settings = load_cloud_config()
    text = "<article>synthetic fixture</article>\n" * 900
    arguments = {"path": "C:/synthetic-fixture/index.html", "text": text}
    payload = response(output=[function(definition(), arguments)],
                       usage={"input_tokens": 200, "output_tokens": 9000, "total_tokens": 9200})
    engine, client, bodies, factory = scripted_sdk(monkeypatch, [payload], engine_config=settings)
    try:
        result = engine.respond_with_capabilities([{"role": "user", "content": "Write the synthetic fixture."}],
                                                  (definition(),))
        assert result.kind == ModelResponseKind.CAPABILITY_CALLS
        assert result.capability_calls[0].arguments == arguments
        assert result.completion.usage.output_tokens > 4096
        assert bodies[0]["max_output_tokens"] == 16384
        assert bodies[0]["reasoning"] == {"effort": "none"} and bodies[0]["temperature"] == 0.1
        assert engine.context_length == 45056
        assert settings.profile("gpt-6-luna").max_input_tokens == 28672
        assert factory.call_args.kwargs["timeout"] == 180
    finally:
        engine.close()
    assert client.is_closed()


def test_larger_budget_still_rejects_an_incomplete_tool_call(monkeypatch):
    payload = response(status="incomplete", incomplete_details={"reason": "max_output_tokens"},
                       output=[function(definition(), arguments={"path": "C:/synthetic-fixture/index.html", "text": "partial"},
                                        status="in_progress")],
                       usage={"input_tokens": 200, "output_tokens": 16384, "total_tokens": 16584})
    engine, client, bodies, _ = scripted_sdk(monkeypatch, [payload], engine_config=load_cloud_config())
    try:
        result = engine.respond_with_capabilities([{"role": "user", "content": "Write the synthetic fixture."}],
                                                  (definition(),))
        assert result.protocol_failure.code == ModelProtocolFailureCode.OUTPUT_TRUNCATED
        assert not result.capability_calls and result.openai_response is None
        assert result.completion.incomplete
    finally:
        engine.close()
    assert client.is_closed()
