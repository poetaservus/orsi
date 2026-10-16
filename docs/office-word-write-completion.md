# Word report confirmation deadlines

The reported warning was reproduced with the production Office connection
settings on an isolated synthetic three-page report. Word received the report,
but the client stopped waiting after ten seconds, before native verification
and the complete recovery snapshot returned a receipt. The original native
report test had explicitly used a thirty-second call timeout, masking the
production mismatch. The production-settings reproduction failed with the
same `OUTCOME_UNKNOWN` message in 27.93 seconds overall; its owned process,
bridge and export scratch directory were released.

## Bounded confirmation

Default `office.word_compose` calls now allow sixty seconds for the write,
repagination, native content/format/geometry verification and recovery capture.
The SDK read timeout and client wait use the same per-request value. The outer
capability deadline is ninety seconds, covering the two existing authority
controls plus the write and bounded shutdown. Ordinary Office calls retain
their ten-second budget and forty-second outer deadline. Explicit host/test
call-timeout overrides remain authoritative, including short hung-worker gates.

A receipt that settles between a timed poll and the worker-stop/deadline check
is preserved. A settled failure remains a failure. Timeout, cancellation and
worker loss without a verified receipt still return unknown, invalidate the
connection and require review. No write is replayed, inferred successful from
appearance, automatically saved or rolled back. Content-free private diagnostics
identify the confirmation stop reason and timeout value.

Native write/readback rules, approvals, identity/snapshot binding, model profiles,
sampling, routing, prompts, tool schemas and schema budgets are unchanged. The
native regression now uses production call settings and checks both deadlines,
so a larger test-only timeout cannot hide this mismatch again.

## Qualification

The final focused selection passed **135 tests** in **34.54 seconds**. New cases
exercise a real MCP/SDK receipt delayed eleven seconds after its synthetic side
effect, proving the old ten-second cutoff is crossed without replay. They cover
ordinary-tool budgets, explicit short overrides, true timeouts, sent-write
cancellation, released owned workers/scratch, and both successful and failed
receipts at the timed-poll boundary. Initial boundary-fixture failures omitted
the required ready-connection generation; that fixture was corrected without
changing production exposure validation.

The native three-page report gate passed in **59.81 seconds**, using production
call deadlines. The first composition round trip, including authority checks,
took **12.203 seconds**; the pre-fix production-settings gate independently
reproduced the ten-second confirmation failure. The gate verified actual body paragraphs,
heading styles, editable table, page count and fields, rendered every page,
exercised denial/stale-source/foreign-edit protections and owned restoration,
saved to a new local path, and reopened the file. All owned Word/bridge processes
and export scratch were released without forced fixture termination. The user's
document was not modified by these tests.

The unrestricted full suite recorded **4,209 passed, 84 failed, 99 skipped**,
**15 passing subtests** and two warnings in **1,360.24 seconds**. All fifty
original baseline failing IDs and all fifty-three failing IDs from the preceding
Word validation qualification recur. Thirty-one further failures are in unchanged
shell, Git skill installer/package and skill registry modules. They include
Git clone rejection, missing shell readiness files and native rename denials;
one PowerShell formatting assertion has its long temporary path wrapped in
the console output. There are no failing Word confirmation checks.

An unrestricted recheck of all six affected shell/skill modules with a short
repository-local temporary path recorded **251 passed, 1 failed, 1 skipped** in
**68.55 seconds**, without source or assertion changes. The remaining shell
monitor/readiness fixture did not produce its information file; its cause
remains unresolved. All rechecked Git/package/registry/reference-reader cases
passed. The full-run clone/handle failures are not relabeled passing, their
full-run causes remain unresolved, and no full run is claimed clean. Unrelated
pending installer/UI/localization repair remains separate and preserved.

Live provider/model generation remains unrun and separate from the native Word
and scripted SDK gates. No API credentials or real provider requests were used.
Compilation, dependency consistency, accepted manifest/budget verification and
whitespace checks pass. The Office schema digest remains unchanged.

Evidence is retained in the isolated checkout's ignored
`state/word-write-completion/`. Pre-change pending-file hashes, workflow backup,
refs/worktree inventory and a verified complete-history bundle are under the
active checkout's `state/backups/word-write-completion-20261016/`.
