# Context recovery: implemented, rollout not qualified

The unchanged accepted source baseline is `651567b19fab4e8dbe7808aa3644bb54297dbe00`.
The candidate adds `AgentFeatureConfig.context_recovery_enabled`, default **false**. No accepted
model profile, sampling setting, prompt source, production permission or checked-in agent flag
was changed. Normal startup continues to use the accepted context selector and capability routing.
This is a gated implementation, not a claim that long sessions now work reliably in production.

## Request preservation

`app/conversation/recovery.py` builds disposable request projections from history. It first
projects large capability outputs, retaining head/tail excerpts and bounded literal matches from
user requirements. Partial projections carry an omission notice, original byte count and SHA-256.
They explicitly say that omitted content is not evidence of absence and must not be reconstructed
or used to replay mutations. Original stored results and settled execution traces stay intact.

All system messages, all user requirements, complete call arguments, success/error envelopes and
message-scoped call/result identities remain exact. A projected directory listing cannot establish
filename uniqueness. Filename resolution matches the generating message as well as its call ID,
and does not automatically continue disambiguation from an earlier stopped turn.

Compaction runs only when projection still exceeds admission capacity. It shortens older ordinary
assistant text and makes older result excerpts smaller, preserving every tool exchange. It does
not invoke a summarizing model, add summary requests, discard user requirements, or split call/result
pairs. If protected content still cannot fit, the turn stops with a context-limit outcome. Projection
failure after a successful operation stops safely while retaining its settlement.

This is recovery before request admission. It does not implement a retry for provider-side context
overflow. Preserving every requirement and pair also means sufficiently long sessions eventually
reach a hard limit; this policy does not promise indefinite sessions.

## Capability reachability and cost

With the gate enabled, the entire enabled, model-visible registry is available independently of
phrases or language. Disabled capabilities stay unavailable, and each call still passes validation,
permissions and approval separately. The default phrase router remains active because this
candidate failed the cost gate. Blanket catalog advertisement solves one reachability problem
but carries substantial schema cost; a measured, cheaper discovery policy remains future work.

The runtime persists inference invocation counts, estimated input tokens and projection/compaction
counts in turn outcomes. These count admitted agent-runtime calls, including failed attempts and
fallback requests. They do not count hidden provider HTTP retries or every non-agent chat request.
The acceptance wrapper additionally measures all inference invocations in its sessions and records
actual provider usage when available. Missing usage is null, never zero.

## Matched baseline comparison

Both arms used the same fixed runner, prompts, model/profile hashes, target limits, agent limits,
permission flags and synthetic full-local workspace authority. Only source and the recovery flag
differed. Baseline application source came from an untouched Git archive of `651567b`.
There were two repetitions of each workload with no reset between its turns.

These are **deterministic architecture fixtures**, not real-model success or measured billing.
The conservative character estimator and scripted responses isolate retention, admission,
reachability, settlement and cost accounting. They cannot certify how Qwen follows requirements.

| Workload | Arm | Passed turns | Successful continuous sessions | Generation requests | Estimated input tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| Routine, 3 turns/session | Baseline | 6/6 | 2/2 | 10 | 18,140 |
| Routine, 3 turns/session | Candidate | 6/6 | 2/2 | 10 | 85,990 |
| Pressure, 8 turns/session | Baseline | 8/16 | 0/2 | 24 | 130,174 |
| Pressure, 8 turns/session | Candidate | 16/16 | 2/2 | 30 | 307,808 |
| Total | Baseline | 14/22 | 2/4 | 34 | 148,314 |
| Total | Candidate | 22/22 | 4/4 | 40 | 393,798 |

Routine input cost increased **4.7404 times**, despite unchanged routine request count. Pressure
work made additional requests to complete work the baseline could not finish; stopping earlier
is not counted as a cost saving. Actual total input/output usage is unavailable in fixture mode.

The new conservative acceptance criterion allows at most 1.25 times baseline routine requests,
estimated input and observed total tokens. This ceiling is an implementation decision, fixed
before judging these results; it was not relaxed to force acceptance. Qualification also requires
matched accepted 16,384-context/4,096-output limits, at least two repetitions, all candidate turns
and sessions completed, complete actual usage, and released owned servers. Deterministic runs
cannot qualify rollout. The candidate passed the fixture success gate and **failed the cost gate**.

Large executor results still have the accepted 64-KiB JSON ceiling and an opaque 8-KiB preview.
Information already removed there cannot be restored by context projection. The pressure fixture
uses a bounded search to obtain a central marker when the read preview omits it; this is visible in
its increased request count. It therefore verifies the combined gated policy, not projection alone
and not compliance with the prompt's requested single read call. Independent tests exercise
projection with intact large result data and exact current requirements.

## Live acceptance and memory

The running user-owned ORSI server was preserved. The final memory check saw 16,384 MiB total and
3,860 MiB free. The existing guard resolved a new 14B load to CPU, context 4,096 and output 1,024.
The live runner refused this unmatched baseline **before allocating a model**; it did not force
an unsafe context. An earlier partial CPU probe is retained separately and cannot qualify the
accepted GPU baseline. No live 16K comparison or cloud acceptance was completed.

Content-free evidence is under ignored `state/diagnostics/`:

- `context_recovery_deterministic_baseline_v1.json`
- `context_recovery_deterministic_candidate_v1.json`
- `context_recovery_comparison_v1.json`
- `context_recovery_live_memory_gate_v1.json`
- `context_recovery_cpu_probe_v1.json` (partial, unqualified)

Reports record hashes, effective limits/flags, numeric counters and outcomes; they do not contain
prompts, replies, arguments, results or credentials. Synthetic persisted session fixtures are
content-bearing test history, separate from those diagnostic reports.

## Verification and reproduction

Focused preservation/runtime/outcome checks passed: **130 tests**. A full run after the final
runtime changes had 821 passed, 54 skipped and one existing Windows atomic journal-write failure
(`os.replace`, WinError 5); the failing case passed on an immediate focused recheck. After the final
acceptance-gate hardening, the full suite had **823 passed, 54 skipped, 5 subtests passed and one
WinError 5 journal-write failure** in a different filename-resolution case. Its complete resolver
module plus all acceptance-gate tests passed the recheck: **46 passed**. Both failed full-run logs
are retained. The journal failure remains an unresolved storage reliability issue; this change
does not repair it and these results must not be described as an entirely green full suite.

An additional 21-turn continuous fixture makes 41 generation requests, preserves 20 settled reads,
keeps the standing requirement in every request and restores all 21 outcomes after restart.
Tests also verify current oversized requirements and 12 tool pairs are preserved even when they
cannot fit, scoped ID reuse, safe projection failure, and rejection of mismatched, unmeasured,
incomplete or over-budget acceptance reports.

To reproduce, export the pinned source with `git archive` and extract it into an ignored workspace
directory. Use a fresh workspace and report path for each arm; the runner refuses workspace reuse.
Run these from the installation root, substituting fresh paths if they already exist:

```powershell
.\runtime\python\python.exe tools/context_recovery_acceptance.py --source-root state/context-baseline-651567b --installation-root . --workspace state/context-ab-baseline-new --report state/diagnostics/context-ab-baseline-new.json --variant baseline --repetitions 2 --deterministic
.\runtime\python\python.exe tools/context_recovery_acceptance.py --source-root . --installation-root . --workspace state/context-ab-candidate-new --report state/diagnostics/context-ab-candidate-new.json --variant recovery --repetitions 2 --deterministic
.\runtime\python\python.exe tools/compare_context_acceptance.py state/diagnostics/context-ab-baseline-new.json state/diagnostics/context-ab-candidate-new.json --report state/diagnostics/context-ab-comparison-new.json
```

Omit `--deterministic` only when accepted GPU limits are available for both live arms. The runner
uses synthetic files and approves only its exact synthetic copy operation. It closes only its
owned server. Keep prompts and settings fixed between arms; rerun both if the runner changes.
For the architectural comparison that motivated this work, see
[the pinned OpenCode audit](robustness-audit-2026-10-01.md#opencode-comparison).
