# O.R.S.I — gated read-only filesystem agent

O.R.S.I is a deliberately small desktop assistant. It starts in chat-only mode and can use either
the bundled local GGUF model or an OpenAI-compatible cloud model. The current Phase 9 checkpoint
adds optional metadata and bounded directory-listing capabilities behind explicit feature gates.

## What this build does

- Sends ordinary text conversation history to the selected model.
- Stores one text-only conversation under `state/conversation_v1/conversation.json`.
- Supports Local and Cloud model selection.
- Keeps a cloud API key in memory for the current application run only.
- Continuously identifies the active model, agent state, host-read scope, and read capabilities.
- When explicitly enabled, can return bounded metadata through `filesystem.stat` and deterministic,
  paginated names and types from one requested directory through `filesystem.list`.
- Can use acknowledged Full local read access across enabled local drives under the current Windows
  account without elevation.

## What this build cannot do

O.R.S.I cannot read file content, search directories, launch or close applications, run commands,
use the clipboard, automate windows, write or delete files, or make any operating-system change.
Directory listing is limited to one explicitly requested directory, 50 returned entries per call,
and a 4,096-entry bounded snapshot.

When asked to do anything outside that boundary, the model is instructed to state the limitation
honestly. It can still discuss a task, review text pasted into the conversation, or explain steps
a person can perform manually.

## Enable the read-only capabilities

The checked-in defaults in `config/agent.json` are disabled. Enable the current Phase 9 checkpoint
for one deliberate process with:

```powershell
$env:ORSI_ENABLE_FILESYSTEM_STAT = "1"
$env:ORSI_ENABLE_FILESYSTEM_LIST = "1"
$env:ORSI_ENABLE_FULL_LOCAL_READ = "1"
python -m app.main
```

Full local read is not constructed until the user accepts its warning for that application launch.
Declining keeps the enabled capabilities confined to the portable O.R.S.I root. Network and device
paths remain denied. In Cloud mode, the conversation, metadata, and returned directory names/types
are sent to the selected provider after an additional disclosure. File content is never read by
these capabilities.

When this gate is enabled, local capability requests use the bundled loopback-only
`llama-server.exe`. The server is pinned to llama.cpp build `b9976` (`e3546c794`), matching the
llama.cpp revision in `llama-cpp-python 0.3.34`, and reuses the same portable CUDA 13 runtime. It
runs hidden with bounded startup and shutdown. The server only decodes Qwen's native tool envelope;
every returned call still passes O.R.S.I's strict allowlisted normalizer, permission gate, executor,
and crash journal before anything can run. The feature remains disabled by default; enabling it is
still an explicit local release choice rather than an automatic consequence of passing Phase 8.

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

The regression suite verifies the disabled chat-only default, exact advertised catalog, path
denials, bounded cursor pagination, journaled execution, structured model round trips,
cancellation, and conversation privacy boundaries.

## Portable runtime

Build the application-local Python runtime once on Windows x64:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build-portable-runtime.ps1 -Backend cuda
```

Use `-Backend cpu` for a broadly compatible CPU-only copy. The portable application requires
Python 3.12 because the bundled llama.cpp wheels target that runtime. The builder also downloads
the matching pinned llama-server archive, verifies its SHA-256 digest, packages only the server and
required llama.cpp libraries, and checks the executable's build identity before completing.
