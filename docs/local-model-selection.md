# Local model selection

Open **Settings → Local model** while **Run with → Local** is selected. The list
comes from the portable `models` directory at startup. Restart ORSI after adding
another model. Only GGUF files with a recognized Qwen2, Qwen3, or Qwen3-VL
architecture and an embedded tool-calling template are offered. This is a format
compatibility check, not a guarantee of a model's tool-use quality.

## Default and experimental model

The accepted Qwen3 14B profile remains the default: a target of 16,384 context
tokens, 4,096 response tokens, temperature 0.1. Targets do not bypass the memory
guard. The model's file size and SHA-256 are pinned alongside its profile.
Qwen2.5 3B is load-tested; Qwen3-VL 4B remains experimental. Loading and a short
reply do not qualify a model for complex tool tasks.

The downloaded Qwen3-VL 4B Instruct Q4_K_M is available as **experimental**.
It loads successfully, answers chat prompts, and can produce native tool calls,
but failed the real follow-up file-editing acceptance tests. Failures included
prose mixed with tool calls, incorrect edit arguments, and answering with
instructions instead of performing edits. Low-temperature sampling, a stronger
formatting instruction, and the publisher's suggested text sampling did not
make those scenarios reliable. The prompt experiments are not product changes;
ORSI's strict response validation and write approvals remain unchanged.

The VL model runs in text mode. Image attachments are not enabled and no vision
projector is installed. Model guidance: [official Qwen3-VL GGUF model card](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF).

## What selecting a model changes

A selection resolves that model's versioned profile; settings from the previous
model are not carried over. The profile includes the model path, context targets, exact FP16 KV
cache estimate from GGUF metadata, response limit, GPU/CPU selection, temperature,
top-p, top-k, min-p, repetition/presence penalties, and cache type. The native
server uses the selected model's embedded chat template.

| Profile | Temperature | Top-p | Top-k | Min-p | Repetition / presence | Cache |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen2 / Qwen3 | 0.1 | 0.95 | 40 | 0.05 | 1.0 / 0.0 | FP16 |
| Qwen3-VL (experimental) | 0.2 | 0.9 | 40 | 0.0 | 1.0 / 0.0 | FP16 |

The chooser unloads the old model before measuring available GPU memory. The
same resolver runs at startup, actual lazy loading and reloads. Context is capped
by the profile target and native limit. The guard uses at most 80% of total and
90% of free GPU memory, reserves 1 GiB, and accounts for weights and exact FP16
KV dimensions. The 14B weight multiplier is 1.10, verified against this machine;
other profiles retain 1.20. If the minimum GPU context cannot fit, offload is
disabled and the CPU profile uses 4,096 context / 1,024 reply tokens.

Reply budgets are separate targets: a memory reduction to 8K context can retain
a 4K reply limit, rather than automatically halving it. The reply limit is capped
at half the effective context. Targets stay unchanged so later loads can recover
their full limits when memory is available. Real 14B → 3B → 14B verification on
this 16 GiB GPU restored 16,384 / 4,096, with about 4 GiB GPU memory free after
both 14B loads. See [baseline verification](model-baseline-2026-10-01.md).

Loading happens off the UI thread and selection is disabled during responses.
Only a successful server startup saves the chosen ID atomically to
`state/local_model_selection_v1.json`. `config/model.json` is never rewritten.
Failure preserves the previous selection and configuration and releases the
candidate server; the previous model reloads on the next request. Chat history
is retained and the context meter uses the active model's limits. The existing
Windows owned-process shutdown protection also applies during switching.

## Verification

Deterministic coverage includes metadata bounds, profile replacement, CPU
fallback, saved settings, switching order, conversation preservation, load/save/
missing-file failures, shutdown during switching, busy-session exclusion, and
the Qt settings worker. Backend tests verify all sampling parameters reach both
chat and tool requests, and mixed responses are still rejected.

The current opt-in acceptance is `tests/test_model_baseline_live.py` with
`ORSI_RUN_MODEL_BASELINE=1`. It loads 14B → 3B → 14B, checks the running server's
context, short replies, profile immutability, restored limits, memory headroom
and release of every owned process. It writes content-free evidence to
`state/test-artifacts/model-baseline-live.json`. Earlier experimental 4B editing
failures remain recorded above.
