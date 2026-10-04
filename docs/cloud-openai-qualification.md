# OpenAI cloud Phase 4.1: qualification and packaging

The migration stays on `codex/cloud-openai`; main and the original application
remain preserved. Phase 4.2 owns default/UI selection and legacy removal.

## Acceptance gate

`tools/openai_live_qualification.py` uses the real Responses adapter, hybrid
mode selection, Qt worker/UI, permission executor and durable conversation store.
It reuses the existing ordinary, long-code, read/edit/clarification/follow-up,
cancellation and model-switch prompts from `app.infrastructure.qualification`.
The existing filesystem matrix supplies its unchanged prompts and synthetic
fixtures. Restart and cloud/local/cloud switching extend those workflows.
There are 15 workflows, two repetitions and two configured cloud profiles:
**60 required cells**. Access failures remain explicit blocked cells; no fallback
or substituted model hides them. Trash uses the real Windows Recycle Bin adapter,
limited to the synthetic fixture, rather than the legacy test's holding adapter.
Generated code is parsed/compiled and never executed.

The report binds the committed revision, source/test/tool/packaging hashes,
unchanged prompt suite, cloud and local manifests, feature flags, runtime and SDK
version. Admission requires every cell, durable terminal sequences, actual fixture
effects and approvals, application limits, complete non-cancelled usage,
restart/session preservation, and released owned clients/workers/local processes.
The local mode round trip checks the accepted default local profile without
downgrading its limits. It does not requalify every existing local model.

The runner then executes the full regression suite using a short repository-local
temporary directory. Packaging evidence and a passing full regression are also
required. Missing, failed, skipped, stale or deterministic evidence blocks
qualification. `tools/verify_openai_qualification.py` audits reports read-only.
Neither tool rewrites configuration, model qualification flags, main or remotes.
Content-free summaries retain counts, fixed outcomes, numeric metrics and
verification results. Synthetic conversations stay separately under ignored
fixture state. The authorized key is read in memory only.

This follows [OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices).
The accepted [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) and
[Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) profiles retain
their documented reasoning settings and existing application budgets.

## Packaging

`build-portable-runtime.ps1 -Backend cloud` builds a fresh official, checksum-
verified CPython runtime with the declared SDK/Qt dependencies, without local
inference binaries. Existing-runtime protection remains in place. Both local
build variants now verify the OpenAI SDK as well. The Nuitka route explicitly
includes the lazy OpenAI package and package data and checks its dependency pin
before compilation.

Startup now checks the native local tool server only when configuring local
inference. Missing local binaries no longer disable cloud tools. A cloud-only
portable package can start the native tool agent and UI while the existing
permission boundary remains in force. Versioned defaults, sampling, context
policy, prompts, routing and tool limits are unchanged.

`tools.verify_openai_runtime` checks the installed pin, real SDK parsing and
transport using an offline fixture and released lazy clients. Its cloud-only
mode additionally verifies startup, native capabilities and UI teardown without
local models/server or a live inference request. Packaging builds and all mutable
state are confined to the isolated validation directory, never the original
runtime. Nuitka executable compilation is separate from portable runtime checks.

## Verification

Results are recorded below after the unchanged live matrix and full regression.
Both configured model profiles remain unqualified until all required gates pass.
