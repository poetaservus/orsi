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

Write fixtures sit beside the synthetic portable application folder, following
the existing local acceptance layout. The application's protected-folder rules
remain unchanged. The harness clicks only its own known cloud-consent dialog
for these synthetic fixtures and restricts write approvals to their workspace,
excluding the application folder. A failed switch to Sol still returns to Luna
and verifies a successful response without relabeling the switch as passing.

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

The final live candidate was committed and clean at
`539ee07b8e8c59ee7c2a722f19ea8d02432aec05`. Its read-only evidence audit matched
the candidate identity exactly before this documentation-only results record.
All 60 cells were accounted for across both repetitions:

| Configured profile | Passed | Failed | Blocked |
| --- | ---: | ---: | ---: |
| GPT-6 Luna | 28 | 2 | 0 |
| GPT-6.1 Sol | 0 | 0 | 30 |

Luna passed every independent workflow in both repetitions: ordinary chat,
complete long code, read/edit/clarification/follow-up with exact byte preservation,
cancellation followed by a stat task, durable restart, cloud/local/cloud switching,
and all eight filesystem cases including the real Recycle Bin adapter. Both
model-round-trip failures came from the required switch to Sol, which returned
the adapter's API permission error. Both attempts returned to Luna and completed
the final response while preserving the session. Sol's preflight also returned
permission failure; its unavailable cells were recorded explicitly, not skipped
or substituted. Neither profile is promoted to qualified.

Real mode switches loaded the accepted default local model at **16,384 context
and 4,096 output tokens**, returned to the cloud profile's **32,768 context and
4,096 output**, and released each owned local server. Every owned SDK client,
transport thread and local process was released. No encrypted reasoning items
were returned by Luna; live reasoning-profile replay remains blocked by Sol
access rather than being certified by deterministic tests.

The final post-matrix full regression passed **1,694 tests and 15 subtests**, with
**49 skipped**, in **219.78 seconds**. The JUnit-based report's 1,709 passing cases
includes those 15 subtests. The existing skips remain separate: 18 legacy pool
live gates, 24 opt-in local-model/live UI gates and seven host symlink checks.
The final fixture/permission/edit/write recheck passed **157 tests**; the earlier
cloud/startup/qualification regressions passed **298 tests**.

A fresh cloud-only portable build used checksum-verified official CPython
**3.12.10**, the declared dependencies, **OpenAI SDK 2.54.0** and **Qt 6.11.2**.
Dependency consistency, offline real-SDK parsing/transport, native cloud-tool
startup and UI teardown passed. A separate live request from that package passed
native stat and reopened no-tool chat without a local backend, then released its
client/thread. Its tool request and continuation used **3,152** and **3,384** total
tokens. The checked package source/configuration matched the candidate. This
verifies the portable Python distribution; Nuitka executable compilation was not
run and is not claimed as passing.

Earlier evidence remains separate. The first full suite recorded **1,685 passed,
one failed, 49 skipped and 15 subtests passed** in 221.57 seconds: the initial
startup change broke the existing local-only chat fallback. That was repaired
without changing its test; the startup recheck passed **108 tests**, followed by
a full **1,686 passed, 49 skipped and 15 subtests passed** run in 189.81 seconds.
The first live attempt stalled at the consent dialog before submitting any
workflow. The next matrix correctly denied writes because the harness had put
fixtures in its protected application folder: **16 passed, 14 failed and 30
blocked**, with its full regression passing **1,688 tests and 15 subtests** in
224.54 seconds. The fixture layout and known-dialog interaction were corrected,
not the product's permissions, prompts, sampling or context policy. Those
attempts do not qualify either model or replace the final corrected matrix.

Content-free reports and synthetic fixture history remain ignored under
`state/test-artifacts/cloud-phase41/`. Preservation checks confirm unchanged
main, the original clean checkout/configuration and all **43** historical refs.
The original runtime was not installed into or replaced. Account/project/key
access to Sol and its missing live evidence remain required for full qualification.
