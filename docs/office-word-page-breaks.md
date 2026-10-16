# Word report page breaks and failed-worker cleanup, 16 October 2026

## Scope

The reported `office.word_compose` failure occurs during argument validation,
before a Word write or approval. Its screenshot identifies the page-break rule;
the original call payload is unavailable. Leading, trailing and adjacent break
blocks each reproduce that exact refusal against main `e240296`.

Composition now treats explicit page breaks as content-page separators. The
typed block validator removes boundary breaks and collapses adjacent breaks
before approval identity, the native document compiler and structural readback
consume the plan. Interior separators, paragraphs (including explicitly empty
paragraphs), tables, typography, running matter and page fields are preserved.
Break-only reports, invalid block fields and over-limit input lists still fail.
The tool description states this behavior; the schema and accepted manifest are
unchanged. The full catalog remains below its existing budget (19,964 bytes;
7,087 estimated reserve tokens).

The change is bounded to Word composition validation, failed Office worker
cleanup and their regressions. It
does not change acceptance prompts, routing, model settings, correction/replay
limits or write/approval/recovery policy. Conversation history retains the actual
submitted arguments; only the effective approved write plan is normalized.

## Qualification

The active checkout includes the 100 pending full-suite repair files. Their
pre-change hashes are recorded under ignored
`state/backups/word-page-breaks-20261016/`; they are not part of this Word change.
The focused Office contract, provider projection/replay, validation, agent
correction, authority and completion selection passes **132 tests in 24.11 s**.
Three preliminary attempts had failures in the new transcript fixture (an
unpaired call, then incomplete result envelopes); those failed runs are retained
separately and are not counted as passes. The final fixture uses a complete typed
capability result and preserves the actual eight submitted break markers in
provider history while approving the two effective separators.

A later full run exposed a separate failed-receipt cleanup race. The SDK worker
invalidated the connection and settled its error before its `finally` block
completed transport shutdown. The caller could therefore return an unconfirmed
write while the worker thread was still alive. Failed receipts now wait for the
existing bounded disconnect when the connection is invalidated and its worker
is still alive. Successful receipts are untouched. If cleanup itself fails,
the original error classification is retained and the content-free diagnostic
`confirmation_cleanup_failed` is set; an uncertain write never becomes replayable.
Four deterministic regressions reproduce the pre-fix gap for read/write errors
and failed cleanup, retaining the exact original error and one dispatch.

The opt-in native Word gate submits the redundant-marker report through the
production connection settings. It checks denied approval, stale-snapshot
refusal, canonical approval arguments, genuine body text and table, native page
count, all rendered pages, recovery, save/reopen and owned-process cleanup.
It passes **1 test in 75.29 s**, with eight submitted markers producing three
native pages. The production composition roundtrip, including authority
preparation, took 14.625 s; this is not a measurement of the tool call alone.
All three PNGs were visually reviewed: no table overflow, clipped text or
orphaned headings; headers, footers and page totals are consistent. The bridge,
owned Word process and private temporary data were released without forced
cleanup.

The first complete active-checkout run recorded **4,330 passed, 6 failed,
70 skipped**, **15 passing subtests** and two existing Qt deprecation warnings
in **1,437.67 s**. All six failures are in native shell-session fixtures that
read readiness metadata or exit status after a one-second observation window.
A separate recheck reproduced seven affected assertions, including an output
arrival race. A content-free owned-server probe measured a returned running
PowerShell session at 1.031 s and actual server readiness at 1.219 s. The shell
correctly reported no verified readiness. Fixture repair and final suite
qualification belong to the separate [full-suite repair](full-suite-repair.md);
production shell behavior and deadlines are unchanged. The failed run remains
retained and is not counted as passing.

The second full run cleared all shell failures but recorded **4,335 passed,
1 failed, 70 skipped**, **15 passing subtests** and two existing Qt warnings
in **1,538.43 s**. Its failure is the native unconfirmed-write regression's
immediate worker-release assertion. The four deterministic cleanup cases each
failed before the product repair. The final focused selection passes **148
tests in 37.59 s**. The native report gate passes again in **77.03 s**, with a
13.984 s composition roundtrip including authority preparation. All three PNGs
are byte-for-byte identical to the visually reviewed pages; owned process,
bridge and temporary cleanup passes.
Earlier progress messages that reported
no failures from the log tail were incorrect; complete-log/JUnit inspection is
authoritative.

The third complete active-checkout run recorded **4,339 passed, 1 failed,
70 skipped**, **15 passing subtests** and two existing Qt warnings in
**1,397.83 s**. All Office and shell tests passed. The remaining failure is
`test_native_inventory_rejects_contract_violations_before_activation[depth-limit_exceeded]`:
Windows denied renaming its synthetic package directory after validation
(`WinError 5`). The unchanged complete reference-reader module subsequently
passed **73 tests in 1.24 s**. The cause of that intermittent denial remains
unresolved; the full run is not claimed clean and no reader behavior or assertion
was changed to conceal it.

An additional unchanged full run was interrupted at the user's request around
11% and is not qualification evidence. The owned test process was confirmed
stopped. No further tests or handle-audit probe were run after that request.

The 70 full-suite skips comprise 51 optional model/provider gates, nine opt-in
Office desktop cases, eight unavailable symbolic-link cases and two native
display cases. The Word report desktop gate passed separately as described
above. No real provider requests were made.

Full-suite temporary files use a short repository-local path; logs, JUnit XML
and native diagnostics are retained under ignored `state/word-page-breaks/` and
`state/full-suite-word-page-breaks/`. Optional external/provider gates are
reported separately; no real model request is made by these checks.

## Git recovery

`codex/word-page-breaks` starts from local main `e240296` in the active checkout,
carrying the pending repair files without modifying them. The original branch,
refs, worktree map, file hashes and full-history bundle are retained under
ignored `state/backups/word-page-breaks-20261016/`.

After qualification, commit only the bounded Word change, then return the active
checkout to its existing full-suite repair branch without changing the tested
tree. Commit its separately qualified repair files. Fast-forward local main to
both commits and remove only the two merged feature branches. Preserve private
settings, other worktrees, historical/unmerged tips and remote refs.
