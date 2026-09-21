from app.settings.model import ModelConfig


def config(tmp_path, **overrides):
    model = tmp_path / "model.gguf"; model.touch()
    return ModelConfig(model_path=str(model), **overrides)


def test_auto_context_scales_with_gpu_memory_and_model_size(tmp_path):
    model_bytes = 2 * 1024 ** 3
    powerful = config(tmp_path).select_context(native_context=32768, gpu_offload_available=True,
        gpu_memory_mib=(16384, 15000), model_size_bytes=model_bytes)
    smaller = config(tmp_path).select_context(native_context=32768, gpu_offload_available=True,
        gpu_memory_mib=(8192, 7500), model_size_bytes=model_bytes)
    assert powerful.length == 32768
    assert smaller.length == 8192


def test_auto_context_uses_safe_cpu_default_and_native_clamp(tmp_path):
    cpu = config(tmp_path).select_context(native_context=32768, gpu_offload_available=False,
        model_size_bytes=2 * 1024 ** 3)
    short_native = config(tmp_path).select_context(native_context=4096, gpu_offload_available=False,
        model_size_bytes=2 * 1024 ** 3)
    assert cpu.length == 8192
    assert short_native.length == 4096


def test_fixed_context_remains_an_explicit_override(tmp_path):
    selected = config(tmp_path, context_length=16384).select_context(
        native_context=32768, gpu_offload_available=False, model_size_bytes=2 * 1024 ** 3)
    assert selected.length == 16384 and selected.reason == "fixed configuration"
