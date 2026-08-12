from __future__ import annotations

import logging
import os
import sys
import ctypes
from pathlib import Path

from app.inference.engine import InferenceEngine, InferenceUnavailable
from app.inference.model_config import ModelConfig


log = logging.getLogger(__name__)
_DLL_DIRECTORY_HANDLES = []
_DLL_LIBRARY_HANDLES = []


def _configure_portable_cuda_dlls() -> None:
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return
    if _DLL_DIRECTORY_HANDLES:
        return
    package_root = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for relative in (("cu13", "bin", "x86_64"), ("cuda_runtime", "bin"), ("cublas", "bin")):
        directory = package_root.joinpath(*relative)
        if directory.is_dir():
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(directory)))
            log.info("Added portable CUDA DLL directory: %s", directory)
            for name in ("cudart64_13.dll", "cublasLt64_13.dll", "cublas64_13.dll"):
                library = directory / name
                if library.is_file():
                    _DLL_LIBRARY_HANDLES.append(ctypes.CDLL(str(library)))
                    log.info("Preloaded portable CUDA DLL: %s", library)


def _probe_native_context(llama_cpp, model_path: Path) -> int | None:
    probe = None
    try:
        from llama_cpp._internals import LlamaModel
        params = llama_cpp.llama_model_default_params()
        params.vocab_only = True
        params.n_gpu_layers = 0
        probe = LlamaModel(path_model=str(model_path), params=params, verbose=False)
        metadata = probe.metadata()
        architecture = metadata.get("general.architecture")
        value = metadata.get(f"{architecture}.context_length") if architecture else None
        if value is None:
            value = next((item for key, item in metadata.items() if key.endswith(".context_length")), None)
        return int(value) if value is not None else None
    except Exception as exc:
        log.warning("Could not determine the GGUF native context length: %s", exc)
        return None
    finally:
        if probe is not None:
            probe.close()


class LlamaCppInferenceEngine(InferenceEngine):
    def __init__(self, config: ModelConfig):
        path = config.resolved_model_path
        if not path.is_file(): raise InferenceUnavailable(f"No local GGUF model found at {path}. Update config/model.json.")
        if sys.version_info[:2] != (3, 12):
            raise InferenceUnavailable(
                f"O.R.S.I local inference requires Python 3.12 x64, but Python "
                f"{sys.version_info.major}.{sys.version_info.minor} is running. "
                "Launch O.R.S.I with its bundled Python 3.12 runtime."
            )
        _configure_portable_cuda_dlls()
        try:
            from llama_cpp import Llama, llama_cpp
        except (ImportError, OSError, RuntimeError) as exc:
            raise InferenceUnavailable(
                "llama-cpp-python could not load its native libraries. Reinstall the CUDA wheel inside "
                "O.R.S.I's Python 3.12 virtual environment."
            ) from exc
        self.config = config
        supports_gpu = getattr(llama_cpp, "llama_supports_gpu_offload", None)
        gpu_offload_available = bool(supports_gpu()) if callable(supports_gpu) else None
        native_context = _probe_native_context(llama_cpp, path)
        selection = config.select_context(native_context=native_context,
                                          gpu_offload_available=gpu_offload_available is True)
        self.context_length = selection.length
        self.native_context_length = selection.native_context
        self.context_selection = selection
        log.info("llama.cpp GPU offload available: %s; requested layers: %s",
                 gpu_offload_available, config.gpu_layers)
        log.info("Selected context length: %s tokens (%s; native=%s; GPU total/free MiB=%s/%s)",
                 selection.length, selection.reason, selection.native_context,
                 selection.gpu_total_mib, selection.gpu_free_mib)
        if config.gpu_layers != 0 and gpu_offload_available is False:
            log.warning("GPU layers were requested, but this llama-cpp-python build has no GPU offload backend.")
        try:
            self.model = Llama(model_path=str(path), n_ctx=self.context_length,
                               n_gpu_layers=config.gpu_layers, verbose=False)
        except Exception as exc:
            raise InferenceUnavailable(
                "The local model could not be initialized on this computer. "
                "Try the CPU portable build or select Cloud mode."
            ) from exc

    def respond(self, messages: list[dict[str, str]]) -> str:
        response = self.model.create_chat_completion(**{
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        })
        message = response["choices"][0]["message"]
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise InferenceUnavailable("The local model returned an empty response.")
        return content.strip()

    def close(self) -> None:
        self.model.close()
