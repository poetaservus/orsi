# Bounded edit recovery, 9 October 2026

Phase 4 is a separate runtime/progress change from verified main `3650e22` on
`codex/bounded-edit-recovery`. Core prompts, acceptance requests, routing, native
tool contracts/limits, permissions, model profiles/sampling and context policies
remain unchanged. The cloud step budget stays 128 and the global semantic
correction allowance stays four. Successful reads do not reset that allowance.

## Recovery and progress

Turn-local recovery groups rejected exact edits by normalized target and operation,
including path case/separator aliases and superficially different arguments.
Three rejected edits to one target without a novel, settled changed revision stop
that recovery group. The global four-correction limit remains cumulative and can
stop earlier. There is no cap on valid edits to a file beyond existing turn budgets.

After a missing match, stale digest or no-change rejection, another edit to the
target requires a fresh successful source read returned before that retry was
constructed. A read and recovery patch in the same model batch cannot satisfy
this requirement. Its proposed old text must occur
in that returned text, and an optional expected digest must equal the returned
complete-file digest. Failed/unrelated reads and unseen targets do not satisfy
recovery; supported larger reads can recover truncated source. Rejected attempts
never reach approval or mutation. Runtime feedback supplies the recovery steps
without embedding source/patch contents or granting replacement/copy authority.
If only runtime preflight rejected a prematurely planned retry, its untouched read
remains usable in the next response; the model need not reread it redundantly.

For a no-change or already-applied patch, the fresh read can show the proposed text
is already present. Feedback asks the model to check whether the requested change
is satisfied and report source inspection; the rejected call remains a failure.
A repeat of a previously successful exact patch is rejected when a fresh read
confirms that same successful file revision. No task completion is inferred.

Known complete-file digests expose reversals: one return to an earlier revision
is allowed, while two such returns stop a cycle. Distinct valid revisions continue.
Successful writes without a known previous digest do not prove byte change or
reset failed-edit allowance. Unchanged writes do not renew read allowances. The
existing identical-call/read guards and read-after-settled-change handling remain
intact; failed edits do not renew exhausted identical-read allowances.

## Stopped work

Repeated-call and semantic-correction stops now carry a locally constructed report
of settled file operations, their targets, the last actual tool failure and the
failed target even when no change succeeded, and remaining completion uncertainty.
Saved operations are evidence of settled work,
not proof that the task is complete. No extra model call constructs this report.

The service retains its error contract through `IncompleteResponseError`, a
`RuntimeError` subclass. Its partial report and interrupted completion state use
the existing UI-worker rendering path instead of a generic exception log. Original
terminal statuses, call/result pairing, approval consumption and durable journal
authority are preserved. Restoring history never starts work, and later user turns
can inspect the recorded outcomes without replaying mutations. Cancellation and
unknown write outcomes retain their existing stop/review protections.

## Verification

The initial native harness recorded 17 failures/one pass in 27.75 seconds; its
incorrect persisted-outcome call lookup and too-small fake context were corrected
before implementation. The corrected pre-fix reproduction recorded **16 expected
failures and three passes** in **29.29 seconds**, including the missing recovery
guards and generic worker failure. Its requests/assertions remain frozen. Production
context settings were untouched; a roomy scripted adapter isolates runtime behavior.

Twenty-eight new native regressions cover missing/stale/no-op recovery, fresh digests,
truncated targets, failed/unrelated reads, normalized aliases, per-target/global
failure bounds, eight valid edits to one file, repeated completed patches, revision
cycles, uncertain/unchanged writes, UI delivery, persistence and cancellation.
Initial focused qualification passed 154 tests with one host symbolic-link skip in
87.32 seconds. The expanded focused qualification passed **160 tests**, with the same skip,
no failures/errors, in **94.68 seconds**. Reports are ignored
`state/phase4-before-final.xml` and `state/phase4-focused-final.xml`.

The first full unrestricted run passed **2,663 tests and 15 subtests**, with **58
optional/host skips**, no failures/errors, in **371.46 seconds**. A subsequent
isolated batch regression reproduced one failure: a recovery patch could be planned
alongside its read before the model received the source. The final guard now checks
the read's model step. All 12 successful edits from the initial cloud recovery/
compatibility runs already used a read returned in an earlier response.
The batch regression's failed reproduction is retained in
`state/phase4-batch-before.xml`. A final presentation regression exposed an omitted
failed filename when no changes had succeeded; the report now names it, with the
original failed reproduction in `state/phase4-failed-target-before.xml`.
Final focused delivery checks passed **101 tests**, with one host symbolic-link
skip, no failures/errors, in **66.18 seconds**, including both fixes and reuse of
returned source without a redundant read. The report is ignored
`state/phase4-focused-delivery.xml`.

The final full unrestricted recheck passed **2,666 tests and 15 subtests**, with
**58 optional/host skips**, no failures/errors, in **382.18 seconds**. Its report
is ignored `state/phase4-full-recheck.xml`. The cloud recovery gate seeds one native missing-match, stale-digest or no-op rejection, then delegates
to the unchanged real cloud provider. It uses the existing Phase 2 natural request
verbatim with synthetic fixture paths, screenshots and the 453-line source. Each
case runs with and without the unchanged Python skill. Already-fixed no-op fixtures
require a fresh sufficient read and an honest no-change report, with no mutation.
Separate unchanged Phase 3 requests qualify valid two-file edits and requested
copies. These gates verify saved files/source, without executing Python or a GUI.

All six recovery cases passed initially and again on the final code using the
default `gpt-6-luna` backend. Missing-match and stale-digest cases each used three
settled calls (one native rejection, one complete read and one approved exact edit).
No-change cases used two calls (rejection/read), made no mutation, and reported that
the requested text was already present. Every case retained exactly one failed
`invalid_arguments` result and one semantic correction; reads did not erase it.
All saved bytes were exact, the complete base 12-tool catalog remained available,
coding screenshots generated no images, reports disclosed unrun execution checks,
and all transports were released.

The four unchanged Phase 3 fix/copy cases also passed, using 6/12 settled calls
without the skill and 7/11 with it. Existing fixes made two approved edits each;
copy tasks made four approved mutations each and preserved both originals. These
compatibility cases preceded the final batch/presentation refinements; their valid
edits already used prior-response source reads, and neither refinement changes
the completed, non-recovery path. The final full suite rechecks that path.

All ten cloud reports equaled the models' persisted final answers. An independent
audit verified all 12 successful cloud edits used a read returned in an earlier
provider response. The unchanged Python skill retained SHA-256
`ab4643c14f92c4c176a11f3f6f6bb8767b9c16515f168b60422970a4e6aa23b2`.
Content-free summaries are ignored `state/phase4-recovery-cloud-final/summary.json`
and `state/phase4-coding-compatibility/summary.json`.

The first final-code full run recorded **2,665 passes**, **58 skips**, and one
existing Git-installer cleanup failure plus a related teardown error in **375.23
seconds**. It is the same `test_repository_limits_reject_before_copy[bytes]`
failure recorded during the independently qualified reporting prerequisite; the
installer implementation and its assertions are unchanged. Its complete 60-test
native group then passed unchanged on recheck in **16.86 seconds**
(`state/phase4-installer-recheck.xml`), followed by the successful final full suite.
The failed full result remains
ignored `state/phase4-full-final.xml`, separate from the successful final recheck.

Compilation, dependency consistency, whitespace and credential-exclusion checks
also passed. Cloud summaries contain only numeric/fixed-category metadata; fixture conversations
stay under ignored `state/`. Keys are read into memory from the authorized existing
file and are excluded from output/versioned files. Baseline preservation snapshots
contain only paths, sizes and hashes. Optional provider/local-model/UI and host
symbolic-link gates remain separate from passed deterministic/cloud checks.

## Integration

Pre-integration refs/worktree maps, a verified complete-history bundle and settings/
configuration preservation hashes are saved under ignored
`state/backups/bounded-edit-recovery-20261009/`. Preserve prior main at
`archive/2026-10-09/main-before-bounded-edit-recovery`, commit after verification,
fast-forward local main and the requested active checkout without switching its
settings branch, and remove only the merged feature branch. Other worktrees,
remote refs, settings edits and historical tips remain intact. Restart ORSI to load
the change. Phases 5–6 remain separate.
