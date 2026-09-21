# O.R.S.I status report

Date: 2026-09-21

## Overall status

The active development repository is `C:\Users\yaboy\Desktop\orsi_test`. The codebase has
completed a structural cleanup while preserving the current Qt design, local/cloud inference,
schema-driven tool calling, deterministic authorization, approval flows, and filesystem behavior.
The version remains `v0.4.0-dev`; this cleanup is not a release promotion.

The correct feature-enabled launcher is `ORSI_TEST.cmd`. The base portable launcher remains
`ORSI.cmd`.

## Architecture status

- `app/main.py` is now a minimal GUI entry point.
- `app/startup.py` owns application composition and inference/backend selection.
- Agent code is grouped under `app/agent/`; the old unreachable regex resolver and forced-call
  branch were removed.
- Tool contracts and implementations remain under `app/capabilities/`, with one registration path
  in `capabilities/catalog.py`.
- Permission, host-access, read-path, and write-path policy live under `app/security/`.
- Execution, native Windows filesystem operations, and the crash journal live under
  `app/execution/`.
- Validated feature/model/cloud/path configuration lives under `app/settings/`.
- Model/tool protocols and provider adapters live under `app/inference/`.
- Conversation context, orchestration, persistence, and result grounding are separate modules under
  `app/conversation/`.
- GUI approvals and the background conversation worker were extracted from the main window without
  changing the visual design.
- Application logging is configured once through `app/infrastructure/logging.py`; the capability
  crash journal remains a separate audit trail.
- A static import-graph audit found 68 application modules and no circular dependencies.

See [../ARCHITECTURE.md](../ARCHITECTURE.md) for the dependency map and extension points.

## Runtime behavior

- Ordinary conversation works through the bundled local model or the configured OpenAI-compatible
  cloud provider.
- The model receives the complete enabled capability catalog each agent turn and selects native
  schema-driven tool calls. There is no production regex command router.
- Read tools: `filesystem.stat`, `filesystem.find`, `filesystem.list`,
  `filesystem.read_text`, and bounded literal `filesystem.search`.
- Approval-controlled tools: `filesystem.mkdir`, `filesystem.write_text`,
  `filesystem.copy`, `filesystem.move`, `filesystem.trash`, and
  `application.launch`.
- `application.launch` is allowlisted and currently recognizes Blender; it does not provide a
  shell or arbitrary process execution.
- Full-local read still requires an explicit warning acknowledgement for every launch. Write and
  execute permissions remain separate and require exact, single-use approval.
- Interrupted or unverified mutations still block retry pending journal review.
- Cloud credentials remain environment-sourced or in-memory only.

## Verification

- Complete deterministic suite:
  `runtime\python\python.exe -m pytest --basetemp .codex-refactor-final-test4`
  — **575 passed, 17 skipped** in 53.89 seconds.
- Python compilation:
  `runtime\python\python.exe -m compileall -q app tests` — passed.
- Opt-in bundled local-model smoke:
  `test_bundled_model_completes_a_filesystem_stat_round_trip` — passed. This verifies actual
  llama-server startup, local model initialization, native tool calling, read-only execution, and
  result continuation.
- Opt-in real-model off-screen GUI workflow:
  `test_real_local_agent_ui_workflow` — passed. This verifies GUI/backend communication, normal
  chat, successful metadata execution, missing-path failure, denied traversal, and cancellation.
- Approval, denial, expiry, changed-target, crash-journal, and GUI-dialog paths are covered by the
  deterministic suite, including native Windows write integration in repository-local test
  sandboxes.
- The 17 normally skipped tests are additional opt-in live-model matrices and manual acceptance
  gates; they are not deterministic unit/integration failures.

## Security and dependency audit

- No production API key, token, password, or personal absolute path was found. Test-only fake
  credentials remain obvious fixtures.
- Cloud secrets are referenced only by environment-variable name in checked-in configuration.
- No security control was removed or weakened.
- No shell/console, clipboard/window automation, plugin loader, or skills subsystem is present.
- `pytest-mock` was declared but unused and has been removed from the test extra. Pydantic,
  PySide6, llama-cpp-python, and pytest remain actively used.
- Runtime/model/state directories and historical threat reviews were retained because they are live
  assets or useful security history, not duplicate implementations.

## Remaining technical debt

- `ui/main_window.py`, `agent/runtime.py`, `execution/audit.py`,
  `security/permissions.py`, and `inference/protocol.py` remain substantial modules. They now
  have clearer surrounding boundaries, but further internal extraction should be driven by concrete
  changes rather than file-size targets.
- In-progress cancellation remains backend-cooperative; not every third-party inference call can be
  interrupted immediately.
- Malformed persisted conversation JSON still needs preserve-and-recover handling.
- Fresh portable-runtime packaging and a visible packaged GUI smoke check remain release gates.
- The allowlisted application locator found no standard Blender installation during the previous
  host check; the launch path should be manually accepted on a machine where Blender is installed.
