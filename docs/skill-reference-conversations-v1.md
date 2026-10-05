# Skill references in conversations v1 (Phase 4)

Date: 5 October 2026. Starting main: `f31a483`.
Implementation branch: `codex/skill-reference-conversations-v1`.

This is the Phase 4 implementation record. See [Phase 5 qualification](skill-reference-qualification-v1.md)
for the subsequent live results and remaining model-compliance/access limitations.

Phase 4 connects the Phase 3 reader to selected-skill conversations. The first
request includes `SKILL.md` guidance and a compact inventory of canonical paths,
an opaque package identity and its content version. Supporting document bodies,
host paths, per-document hashes and sizes are absent from this prompt. The
controlled storage adapter still snapshots the bounded package to verify its
identity, contents and inventory; lazy loading refers to model context, not to
skipping filesystem validation.

## Reading and authority

Only a valid active package with reference documents, in an enabled tool
conversation, gets `skill.read_reference`. Its arguments select one inventory
path, the advertised version and bounded continuation offsets. Existing reader
limits remain: 2,048 bytes/40 lines by default, at most 4,096 bytes/80 lines per
read, with UTF-8 boundaries and explicit completeness/provenance metadata.

The conversation constructs a temporary registry and exact read permission for
that reader. The base runtime, executor, journal, approval broker, model and run
limits stay shared; the base registry and permission rules are never mutated.
The reader binds to one session and turn. Its package storage is independent of
ordinary host-file read roots; it cannot select another package or search the
host. Write approval and execution restrictions remain binding. Skill files
cannot register tools, grant permissions or change configuration.

Both native function calls and the existing local text fallback use this
inventory and the same bounded reader. Guidance instructs the model to request
only relevant documents, use continuation offsets where necessary, and avoid
reference reads for unrelated questions. There is no extra model request to
select documents. Existing automatic skill selection still sees only candidate
names and descriptions.

## Follow-ups, changes and cleanup

Successful excerpts remain durable tool evidence. Follow-ups can reuse them
only when a newly verified active package has the same identity and content
version. There is no separate body cache. Durable turn metadata records the
reference scope before any model response or tool result; it cannot be changed
after evidence is recorded.

History reconstruction removes raw reference exchanges and opaque provider
replay outside the matching scope. This includes read-free follow-ups whose
provider response may retain earlier reference knowledge. At most one short
unavailable-reference notice per historical turn replaces hidden exchanges.
Earlier visible answers remain conversation history, explicitly distinguished
from the current skill specification.

Every model step and the final answer check the package again. Observed changes,
replacement or storage failures revoke access and stop an in-progress turn.
The same selected package stays unavailable until an explicit skill refresh;
restoring its previous bytes alone does not revive authority. A changed entry
point must first be refreshed in the skill catalog. Skill switching/removal,
message attachment expiry, session reset, tool disablement, model selection,
cancellation and shutdown revoke the old reader. Shutdown and turn cleanup
release shared owned resources through their existing lifecycle.

Cleanup hides scoped reference material while retaining completed non-reference
operations when history saving fails. A failed save blocks another inference
turn; the existing journal recovery still retains completed writes and prevents
automatic replay. No new approval dialog or warning is introduced.

## Context limits and unavailable references

Main guidance, inventory, tool schemas, excerpt text, provenance and replay all
count toward the existing request budget. Explicit skill admission retains the
entire current user task and fails if its requirements cannot fit. Optional
automatic guidance can be dropped, together with its inventory and reader,
using the existing admission policy. Model profiles, sampling, context window
and response limits are unchanged.

When existing context recovery projects a reference result, it retains a
contiguous UTF-8 prefix and recomputes byte offsets, continuation and
`complete_document`. Durable original evidence is unchanged. If even a bounded
projection cannot fit, continuation stops before another physical model request.

Chat-only operation, disabled reference access or invalid/missing packages
advertise unavailability without preloading document text or falling back to
host search. Guidance asks for required content or a refresh rather than
inventing reference rules. Plain single-file skills retain their original
prompt payload and tool catalog.

## Verification

The deliberately tiny integer-clamp fixture and frozen acceptance prompts are
unchanged. Scripted offline providers verify conversation wiring, not actual
model compliance or output quality. Real local/cloud qualification is Phase 5;
no live model request or API credential was used here.

The broad focused check passed 329 tests. After final revocation coverage, the
Phase 4 checks passed 34 tests. The first full run found four cleanup regressions
(three closed-session cases and one failed-history-write case): 1,868 passed,
4 failed, 49 skipped, 15 subtests passed. These were product regressions and were
fixed, not treated as sandbox or intermittent failures. Added failure coverage
also checks scoped reads and completed writes when persistence fails. The final
cleanup/reference/outcome focused check passed 69 tests, including all 37
Phase 4 cases and shutdown cancellation failure coverage.

The next full run passed the corrected cleanup cases but recorded one native
directory-rename failure (`WinError 5`) in
`test_reload_obeys_limits_and_releases_directory_and_file_handles`: 1,873 passed,
1 failed, 49 skipped, 15 subtests passed. Its registry/discovery/loader code and
test are unchanged. The isolated registry/conversation recheck passed 76 tests.
The cause was not established; this failure is retained as verification evidence.

The final full confirmation passed **1,875 tests and 15 subtests**, with **49
existing skips and no failures**, including the directory-rename case. Tests use
the bundled runtime, an unrestricted Windows shell for native handle checks,
repository-local `--basetemp` directories and ignored cache directories under
`state/`. The final suite used `.pytest-tmp-reference-conversations-full-final`.
Existing skipped gates and unattempted Phase 5 live qualification remain separate
from deterministic passes; the earlier rename failure remains recorded above.
