# O.R.S.I — gated file-metadata agent

O.R.S.I is a deliberately small desktop assistant. It starts in chat-only mode and can use either
the bundled local GGUF model or an OpenAI-compatible cloud model. Phase 8 adds one optional,
read-only capability for file metadata behind an explicit feature gate.

## What this build does

- Sends ordinary text conversation history to the selected model.
- Stores one text-only conversation under `state/conversation_v1/conversation.json`.
- Supports Local and Cloud model selection.
- Keeps a cloud API key in memory for the current application run only.
- Clearly identifies itself as **Chat only** or **Agent · File metadata**.
- When explicitly enabled, can return bounded metadata for one file or directory inside the
  portable O.R.S.I root through `filesystem.stat`.

## What this build cannot do

O.R.S.I cannot read file content, list or search directories, launch or close applications, run
commands, use the clipboard, automate windows, write or delete files, or make any operating-system
change. The optional metadata capability is the only model-visible computer capability.

When asked to do anything outside that boundary, the model is instructed to state the limitation
honestly. It can still discuss a task, review text pasted into the conversation, or explain steps
a person can perform manually.

## Enable the Phase 8 capability

The checked-in default in `config/agent.json` is disabled. Enable it for a deliberate run by
setting `filesystem_stat_enabled` to `true`, or for one process with:

```powershell
$env:ORSI_ENABLE_FILESYSTEM_STAT = "1"
python -m app.main
```

The permission boundary is always the portable O.R.S.I root; configuration cannot broaden it.
In Cloud mode, the conversation and any metadata results are sent to the selected provider. File
content is never read by this capability.

The bundled-model live smoke currently detects a compatibility gap: this GGUF emits tool-call
markup as assistant text instead of returning a native structured call. O.R.S.I intentionally
does not execute tool-like prose. The feature therefore remains disabled by default while model
function-calling compatibility is refined.

## Run

The portable copy starts with `ORSI.cmd`. For development with Python 3.12 and the dependencies
installed:

```powershell
python -m app.main
```

Place a llama.cpp-compatible GGUF file under `models/` and configure it in `config/model.json`.
Cloud settings live in `config/cloud.json`; credentials are not accepted in that file.

## Test

```powershell
python -m pytest
```

The regression suite verifies the disabled chat-only default, the sole advertised capability,
path denials, journaled execution, structured model round trips, cancellation, and conversation
privacy boundaries.

## Portable runtime

Build the application-local Python runtime once on Windows x64:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build-portable-runtime.ps1 -Backend cuda
```

Use `-Backend cpu` for a broadly compatible CPU-only copy. The portable application requires
Python 3.12 because the bundled llama.cpp wheels target that runtime.
