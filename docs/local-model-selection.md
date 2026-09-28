# Local model selection

Open **Settings → Local model** while **Run with → Local** is selected. The list
comes from the portable `models` directory at startup. Restart ORSI after adding
another model. Only GGUF files with a recognized Qwen2, Qwen3, or Qwen3-VL
architecture and an embedded tool-calling template are offered. This is a format
compatibility check, not a guarantee of a model's tool-use quality.

## Default and experimental model

The approved Qwen3 14B configuration remains the default: 16,384 context tokens,
4,096 response tokens, temperature 0.1. Its existing context and GPU settings
are preserved in the shipped configuration.

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

A selection creates a fresh profile; settings from the previous model are not
carried over. The profile includes the model path, context limits, exact FP16 KV
cache estimate from GGUF metadata, response limit, GPU/CPU selection, temperature,
top-p, top-k, min-p, repetition/presence penalties, and cache type. The native
server uses the selected model's embedded chat template.

| Profile | Temperature | Top-p | Top-k | Min-p | Repetition / presence | Cache |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen2 / Qwen3 | 0.1 | 0.95 | 40 | 0.05 | 1.0 / 0.0 | FP16 |
| Qwen3-VL (experimental) | 0.2 | 0.9 | 40 | 0.0 | 1.0 / 0.0 | FP16 |

The chooser unloads the old model before measuring available GPU memory. Context
is selected conservatively between 4,096 and 16,384 tokens, capped by the model's
native limit. CPU fallback uses 4,096. Responses reserve a quarter of the selected
context, up to 4,096 tokens. Selecting a model again after switching away can
therefore choose a smaller context than a manually configured starting profile.
On this machine, the switch check selected 8,192/2,048 for 14B and 16,384/4,096 for
both smaller models. The existing approved 14B default remains 16,384/4,096.

Loading happens off the UI thread and selection is disabled during responses.
Only a successful server startup is saved atomically to `config/model.json`.
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

Real checks loaded all three downloaded models in sequence, queried them,
checked profile persistence, and closed the final native server. Experimental
4B editing failures are recorded above rather than hidden behind load checks.
