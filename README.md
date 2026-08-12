# O.R.S.I — conversational baseline

O.R.S.I is currently a deliberately small, chat-only desktop application. It can hold a
conversation through either the bundled local GGUF model or an OpenAI-compatible cloud model.
It has no computer-control capabilities.

## What this build does

- Sends ordinary text conversation history to the selected model.
- Stores one text-only conversation under `state/conversation_v1/conversation.json`.
- Supports Local and Cloud model selection.
- Keeps a cloud API key in memory for the current application run only.
- Clearly identifies itself in the interface as **Chat only**.

## What this build cannot do

O.R.S.I cannot access files, launch or close applications, run commands, inspect the computer,
use the clipboard, automate windows, or make any other operating-system change. No action
registry, action schema, execution loop, confirmation path, audit log, or undo system is part of
the application.

When asked to operate the computer, the model is instructed to state this limitation honestly.
It can still discuss a task, review text pasted into the conversation, or explain steps a person
can perform manually.

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

The regression suite verifies that local and cloud model requests contain only normal chat
fields and that removed computer-action packages are absent.

## Portable runtime

Build the application-local Python runtime once on Windows x64:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build-portable-runtime.ps1 -Backend cuda
```

Use `-Backend cpu` for a broadly compatible CPU-only copy. The portable application requires
Python 3.12 because the bundled llama.cpp wheels target that runtime.
