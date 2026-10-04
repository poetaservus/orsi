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
- Portable-root read scope by default, or configured full-local read on supported Windows drives.
  Startup and cloud selection do not show warning dialogs. Tool approvals appear in the input
  area: **Enter** approves the displayed operation; **Esc** aborts it.
- Crash-journaled tool lifecycle, cancellation, bounded retries/steps, strict schemas, and
  single-use expiring approvals.
- Instruction-only skills: validated local/public HTTPS Git installation, explicit or automatic
  selection, one lower-priority prompt section, and content-free diagnostics.

O.R.S.I has no shell tool, arbitrary process execution, permanent-delete tool, clipboard/window
automation, background indexing, or plugin loader. Network shares and device paths
are denied. Writes to application/state, AppData, operating-system, recovery, installed-application,
redirected, reparse, or ambiguous paths are denied.

## Skills

In the desktop app, open **Settings → Manage skills…**. Paste a public GitHub link to
`SKILL.md`, or choose/drop a local Markdown file, then **Preview → Install**. Skills installed
through Settings become available immediately. Select an installed skill and use **Remove…**
to remove it after confirmation. Installation and management controls live only in Settings.
See [the Settings workflow and verification](docs/skill-settings.md).

Skills add instructions/context; tools remain separately registered and authorized callable
capabilities. MCP is an external tool/resource protocol, while a plugin may bundle skills, tools,
MCP definitions, hooks and configuration. MCP/plugin loading and Claude compatibility are future
work. See the [frozen extension boundaries](docs/skill-runtime-phase6-2.md).

```text
ORSI.cmd skill list
ORSI.cmd skill install "C:\path\to\small-skill"
ORSI.cmd skill info "exact-skill-name"
```

Installation copies `SKILL.md` only, preserving upstream bytes. Scripts, assets, references and
dependencies are not installed or executed. The default global storage is `~/.orsi/skills/`.
Project discovery requires an explicitly supplied project root; startup does not infer one.
Restart O.R.S.I after CLI installation/removal to refresh the application's startup catalog.

In the desktop composer, type `/skill`, choose a name, and send your prompt with its blue chip.
That attachment applies to that message. The underlying local command interface still supports
session activation using `/skill exact-skill-name` and clearing it with `/skill`.
A new chat clears selection. Automatic selection can choose one skill or no match for
the current turn. Skills cannot add tools, change model configuration, or grant permissions.
Skill decision/injection events appear in `state/orsi.log` without prompt contents or hidden
reasoning; see [observability](docs/skill-runtime-phase6-1.md).

## How tool requests work

The active model receives the full enabled, model-visible capability catalog on each agent turn
and can return ordinary text alongside native tool calls. Registry visibility never
constructs arguments, grants permission, or executes an operation. O.R.S.I validates the model's
tool name and arguments, applies deterministic permissions, asks for approval when required,
journals the lifecycle, executes the tool once, and returns its structured result to the model.

There is no production regex command executor. Skill selection leaves tool visibility unchanged,
while a narrow same-folder filename recovery can resolve one obvious
extension/stem variant after an extensionless file read misses. See
[ARCHITECTURE.md](ARCHITECTURE.md#10-natural-language-resolution).

## Configuration

- `config/agent.json`: feature gates, full-local read selection, and bounded agent-loop limits.
  Normal runs have no short whole-session deadline; model requests and tools retain their own
  timeouts, while step, capability-call, repetition, protocol-failure, and transcript limits remain
  finite. Set `runtime_limits.overall_timeout_seconds` to a positive number only when a deployment
  needs an additional absolute safety deadline.
- `config/model.json`: versioned per-model targets, pinned model identities, sampling and memory
  guards. The accepted Qwen3 14B target is 16,384 context tokens and 4,096 response tokens. Actual
  limits are checked against free memory at load time. **Settings → Local model** saves only the
  chosen ID under ignored `state/local_model_selection_v1.json`; it never rewrites accepted profiles.
  See [local model selection](docs/local-model-selection.md)
  for supported models and the experimental Qwen3-VL 4B limitations.
- `config/cloud.json`: OpenAI Responses configuration and explicit Luna/Sol profiles. The default
  is GPT-6 Luna, with 32,768 effective context tokens and a 4,096-token output reserve. Runtime
  selection stores only the model ID in ignored `state/cloud_model_selection_v1.json`.
  Keys come from `OPENAI_API_KEY` or the in-memory session prompt. Requests use `store: false`;
  the SDK is the sole retry owner and `max_retries` is initially zero. Local remains the default
  launch mode. Phase 1 supports text chat and skill selection. Neither profile is
  live-qualified yet. Existing
  OpenRouter adapter tests remain as compatibility coverage during the migration.
  Phase 2 adds native tools and durable stateless response-item/encrypted-reasoning
  replay. See [OpenAI cloud migration](docs/cloud-openai.md)
  and [native tool verification](docs/cloud-openai-tools.md) for scope and results.

Feature flags can be overridden with explicit `ORSI_ENABLE_...` environment variables. Full-local
read authority follows the configured flag. Writes and application launches still require
approval for each exact operation.

The content-free `state/diagnostics/effective_baseline_v1.json` snapshot records the source revision,
effective flags, model hash, targets, actual limits and GPU memory. See
[baseline verification](docs/model-baseline-2026-10-01.md) and [Git workflow](docs/git-workflow.md).

Replies that hit their output limit are shown as **incomplete**, with the received text retained.
The desktop window has no separate title bar. Small controls in its top-right corner minimize,
maximize/restore and close it. New-session and settings controls stay at the top left, with
version/mode/context status centered above the conversation. These overlays have no header strip
or retracting behavior; drag the empty top spaces or resize from the edges. Windows keeps
native caption/resize handling and Snap styles. Closing uses the existing model/worker cleanup.
Assistant prose supports Markdown emphasis, lists, headings and inline code. Replies use light
formatting where helpful and respect explicit code-only or plain-text requests. User messages stay
literal; copying a full response retains its original Markdown and code.
Unfinished code fences still appear in code boxes. Incomplete tool generation is rejected before
argument repair or execution. The UI releases its controls even when the context meter cannot
refresh. See [completion-state verification](docs/completion-state-2026-10-02.md).

Each launch opens an empty conversation. The previous session, including settled tool results and
stopped turn outcomes, is preserved under `state/conversation_v1/archives/`; archives are local files
and are not loaded into the new chat. Within a session, a successful edit stays known when a later
model step fails. Unknown mutations still require review across launches and are never replayed
automatically. Conversation history and archives retain tool arguments/results, which can include
file contents; **New session** clears only the active conversation. The execution journal and
diagnostic snapshots remain content-free. See [durable turn verification](docs/turn-outcomes-2026-10-02.md).

Normal provider responses may contain text alongside multiple calls. Calls settle sequentially
with independent validation and approval; separate limits bound consecutive format failures,
semantic corrections and total model requests. See
[provider response verification](docs/provider-response-recovery-2026-10-02.md).

An opt-in context recovery candidate preserves requirements and tool pairings while projecting
large results. It remains **disabled**: deterministic sessions improved, but routine estimated
input cost increased 4.74 times and live GPU acceptance is incomplete. See
[context recovery measurements](docs/context-recovery-2026-10-02.md).

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

The existing OpenRouter gate applies only when using a legacy `CloudConfig`; it does not qualify
the new OpenAI Responses profiles. With that legacy configuration, set
`ORSI_RUN_LIVE_CLOUD_MODEL_ACCEPTANCE=1` and `OPENROUTER_API_KEY`, then run
`runtime\python\python.exe -m pytest tests\test_cloud_live_model.py --basetemp .pytest-tmp`.
The gate disables pool failover for each candidate and independently exercises listing, reading,
an 80-rule multiline write, searching, copying, moving, folder creation, trashing, metadata inspection, and
a no-tool conversational response. Every mutating case uses a temporary workspace and automatic
test-only approval; the trash case moves its fixture into temporary holding instead of adding an
entry to the real Windows Recycle Bin.

## Portable runtime

Build an application-local Python 3.12 runtime on Windows x64:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build-portable-runtime.ps1 -Backend cuda
```

Use `-Backend cpu` for the CPU-only build. The packaging scripts pin and verify the matching
llama-server archive and install the declared runtime dependencies without changing application
configuration or credentials.
