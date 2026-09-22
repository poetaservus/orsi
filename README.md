# O.R.S.I

O.R.S.I is a local-first Windows desktop assistant with a Qt GUI, local GGUF inference, optional
OpenAI-compatible cloud inference, and a schema-driven capability system. Tool requests are
validated, authorized, journaled, and executed by application code; the model and GUI cannot bypass
those boundaries.

The architectural guide is [ARCHITECTURE.md](ARCHITECTURE.md). Current milestone information is in
[docs/status-report.md](docs/status-report.md) and [docs/roadmap.md](docs/roadmap.md).

## Run the current development build

Use the current repository at:

```text
C:\Users\yaboy\Desktop\orsi_test
```

Launch [ORSI_TEST.cmd](ORSI_TEST.cmd) to exercise the feature-enabled development build. The
portable runtime must already exist under `runtime/python`, and a compatible GGUF model must match
`config/model.json`. [ORSI.cmd](ORSI.cmd) is the base portable launcher.

For development:

```powershell
runtime\python\python.exe -m app.main
```

## Current capabilities

- Ordinary local or cloud conversation with bounded context.
- `filesystem.stat`, `filesystem.find`, `filesystem.list`,
  `filesystem.read_text`, and bounded literal `filesystem.search`.
- Approval-controlled `filesystem.mkdir`, `filesystem.write_text`,
  `filesystem.copy`, `filesystem.move`, and Recycle-Bin `filesystem.trash`.
- Approval-controlled `application.launch` for explicitly allowlisted applications. The current
  implementation recognizes Blender and resolves only verified local executables.
- Portable-root read scope by default, or full-local read on supported Windows drives only after an
  explicit warning is accepted for that launch.
- Crash-journaled tool lifecycle, cancellation, bounded retries/steps, strict schemas, and
  single-use expiring approvals.

O.R.S.I has no shell tool, arbitrary process execution, permanent-delete tool, clipboard/window
automation, background indexing, plugin loader, or skills runtime. Network shares and device paths
are denied. Writes to application/state, AppData, operating-system, recovery, installed-application,
redirected, reparse, or ambiguous paths are denied.

## How tool requests work

The active model receives the complete enabled capability catalog and can return ordinary text or
one native tool call. O.R.S.I validates the tool name and arguments, applies deterministic
permissions, asks for approval when required, journals the lifecycle, executes the tool once, and
returns its structured result to the model.

There is no production regex command router. A narrow same-folder filename recovery can resolve one
obvious extension/stem variant after an extensionless file read misses. See
[ARCHITECTURE.md](ARCHITECTURE.md#10-natural-language-resolution).

## Configuration

- `config/agent.json`: feature gates, full-local read selection, and bounded agent-loop limits.
  Normal runs have no short whole-session deadline; model requests and tools retain their own
  timeouts, while step, capability-call, repetition, protocol-failure, and transcript limits remain
  finite. Set `runtime_limits.overall_timeout_seconds` to a positive number only when a deployment
  needs an additional absolute safety deadline.
- `config/model.json`: local GGUF path, context policy, and generation limits.
- `config/cloud.json`: OpenAI-compatible endpoint, ordered provider model pool, safe headers, and
  API-key environment-variable name. `model` is the primary model and `fallback_models` are tried
  in order when a cloud request is unavailable or returns a malformed tool-call response. The
  first successful model remains pinned for later steps. Transient network, timeout, rate-limit,
  conflict, and server failures use bounded exponential-backoff retries controlled by
  `max_retries`; malformed calls switch models without retrying the same malformed response.
  `timeout_seconds` bounds each candidate and `model_step_timeout_seconds` bounds the complete
  pool/retry operation.

Feature flags can be overridden with explicit `ORSI_ENABLE_...` environment variables. Full-local
read authority is still not created until the launch warning is accepted.

Cloud credentials are accepted only from the configured environment variable or the in-memory GUI
prompt. Do not place API keys in JSON or headers. Cloud mode may send conversation text and requested
tool results—including file names or file content—to the configured provider after the GUI
disclosure.

## Test

```powershell
runtime\python\python.exe -m pytest --basetemp .pytest-tmp
```

The repository-local test base is important on Windows: the real write policy intentionally rejects
the normal AppData temp directory. The suite covers provider adapters, schemas, registration,
permissions, denials, approval flows, executor routing, crash recovery, conversation/context
behavior, natural-language tool use, and off-screen Qt integration.

Opt-in live-model tests remain skipped unless their documented environment gates and model runtime
are available.

To re-certify every configured OpenRouter pool member independently, set
`ORSI_RUN_LIVE_CLOUD_MODEL_ACCEPTANCE=1` and `OPENROUTER_API_KEY`, then run
`runtime\python\python.exe -m pytest tests\test_cloud_live_model.py --basetemp .pytest-tmp`.
The gate disables pool failover for each candidate and requires both a complete filesystem tool
round-trip and a no-tool conversational response.

## Portable runtime

Build an application-local Python 3.12 runtime on Windows x64:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build-portable-runtime.ps1 -Backend cuda
```

Use `-Backend cpu` for the CPU-only build. The packaging scripts pin and verify the matching
llama-server archive and install the declared runtime dependencies without changing application
configuration or credentials.
