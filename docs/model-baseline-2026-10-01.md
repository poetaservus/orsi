# Effective model baseline, 1 October 2026

This repair implements the first item in the robustness audit: make the baseline
reproducible before changing response handling, continuation, routing or tools.
The integration baseline is identified by Git tag `baseline/model-profiles-2026-10-01`.
The runtime snapshot records its full commit, tracked changes and untracked files.
The source audit remains [robustness-audit-2026-10-01.md](robustness-audit-2026-10-01.md).

## Source and runtime ownership

`config/model.json` now contains a schema-versioned default and independent,
immutable per-model profiles. Qualified profiles require exact file size and
SHA-256 identity. Metadata, architecture and full file identity are checked before
loading; hashes are cached only while size and modification time match. A replaced
model cannot silently inherit an accepted profile.

| Model ID | Qualification | GPU target context / reply | CPU context / reply |
| --- | --- | --- | --- |
| `Qwen314BQ4KM.gguf` | Existing accepted profile | 16,384 / 4,096 | 4,096 / 1,024 |
| `model.gguf` | Load-tested Qwen2.5 3B | 16,384 / 4,096 | 4,096 / 1,024 |
| `Qwen3VL4BInstructQ4KM.gguf` | Experimental; prior edit failures | 16,384 / 4,096 | 4,096 / 1,024 |

`state/local_model_selection_v1.json` stores only schema version and model ID.
Only a successful switch writes it. Startup restores that ID and resolves its
profile using the same memory policy as switching. Invalid state falls back to
the versioned default. Runtime reductions never overwrite profile targets.
Unlisted compatible files receive an explicitly unqualified discovery profile.
The old flat configuration remains readable for compatibility, without chooser
writes. The exact original user configuration was preserved in the Git hygiene
backup before migrating its model selection.

## Why 14B no longer silently becomes 8K / 2K

The old chooser generated an adaptive profile while startup used a fixed profile.
It multiplied the 8,584.74 MiB GGUF by 1.20, reserved 1,024 MiB, then used the
remaining conservative GPU budget for KV. That selected 8K. A separate rule
reserved only a quarter of context for output, causing 2K replies as well.

The 14B KV estimate is 163,840 bytes/token from its actual GGUF dimensions:
16K context needs 2,560 MiB. The revised weight multiplier is 1.10; with the
1,024 MiB reserve, the estimated allocation is 13,027.21 MiB. This fits the
13,107.2 MiB ceiling on the 16,384 MiB GPU while retaining the existing 20% total
and 10% free-memory margins. The estimate remains larger than the observed
allocation in the real load test. No fixed target bypasses this check.

When other workloads reduce free memory, the effective context can decrease.
Output keeps its independent 4K target when it fits half the effective context.
If the minimum GPU context cannot fit, the resolver sets GPU layers to zero and
uses the CPU profile. Memory is checked again when a lazy backend actually loads,
including reloads after cloud mode or a failed switch.

## Diagnostic evidence

`state/diagnostics/effective_baseline_v1.json` records only allowlisted facts:
source commit and tracked/untracked change state, mode, effective feature flags after the
read acknowledgement and any agent fallback, agent limits, model ID/architecture/
size/SHA-256, normalized profile-manifest hash, target/effective limits, sampling,
memory policy, memory before load and at capture, and backend load state.
No conversation text, generated code, file contents, host paths, API keys or
server credentials are stored. Snapshot write failure does not break inference.

The opt-in live check writes separate evidence to
`state/test-artifacts/model-baseline-live.json`. It queries the running server's
context rather than trusting Python settings, verifies short replies, compares
profiles before and after 14B → 3B → 14B, checks headroom against the allocation
estimate, and verifies all replaced/final owned servers exit. Evidence is tied to
the source commit at the time the check runs; it is ignored runtime data.

Reproduce with the bundled runtime in an unrestricted Windows terminal:

```powershell
$env:ORSI_RUN_MODEL_BASELINE = '1'
runtime\python\python.exe -m pytest tests/test_model_baseline_live.py --basetemp .pytest-tmp-baseline-live -s
```

Deterministic tests cover immutable profiles, state-only persistence, restart
selection, round trips, memory reductions, recovery to targets, safe CPU fallback,
replaced model identity, invalid state, effective diagnostics and existing switch
failure/shutdown/UI behavior. The ordinary suite keeps live gates skipped unless
explicitly enabled. This baseline does not claim to repair the audit's truncation,
continuation, protocol, context-compaction or tool-selection defects.

## Verification result

The complete pre-commit regression run passed 733 tests and 5 subtests, with 53
live or host-dependent skips; the final revision-identification check added one
deterministic test and all 24 model/profile-focused tests passed. The dedicated
live 14B → 3B → 14B check passed again against clean source commit `28c2787`.
Both 14B loads left about 4,020–4,025 MiB GPU memory free across the two runs,
and all owned servers exited. Its snapshots identify the full clean commit.

An earlier full run hit three intermittent Windows `WinError 5` failures while
atomically replacing conversation/journal JSON in unchanged persistence code.
Those affected areas passed a focused recheck (72 tests), and the subsequent
complete run passed. This repair does not hide or fix that separate persistence
reliability concern; the original failure output is retained under
`state/test-artifacts/model-baseline-suite.txt`.

A further full run against clean commit `28c2787` passed 733 tests and 5 subtests
but failed one existing filesystem-list case on the same journal JSON replacement
error (53 skipped). The failure occurred in a scripted-model test that does not
use the new profile resolver or baseline recorder. The persistence implementation
is unchanged by this repair. Keep this as an open reliability defect; do not
describe the overall application as fully stable merely because another run
passes. Exact output: `state/test-artifacts/model-baseline-clean-suite.txt`.
The failing filesystem-list cases passed their immediate focused recheck (2 tests).
The final live verification also constructs the real configured capability runtime
under isolated test state before recording its effective flags.
