# Attachment input: phase 5 context and lifecycle

The final implementation phase preserves sources through context pressure, interruption,
reopening, archives and manual mode changes. It also closes two composer lifecycle gaps:
worker rejection before durable admission lost the visible draft, and abandoned prepared
drafts left app-owned snapshot files behind.

## Draft ownership and admission

Only composer imports opt into draft ownership. An in-process ownership/lock object is
shared by canonical storage root, including reopened stores and equivalent root spellings.
The history transaction locks draft ownership while verifying sources, saving the user turn
and transferring those sources to durable history. A failed save leaves ownership unchanged.
Concurrent closing/removal cannot delete a source between its verification and successful save.

The composer keeps prepared cards disabled while the worker checks admission. On a successful
durable turn save, an admission event clears those cards; their snapshots now belong to history.
On rejection before that boundary, the worker restores the exact original editor text, ordered
references and explicitly selected skill chip. Its unsaved user bubble is removed. Retry remains
a user action using the same immutable copies; no repeated snapshot import or automatic model/
tool replay occurs. Once admitted, even a stopped/failed turn retains its source references.

Removed drafts, preparation failures, late prepared results after cancellation and window closing
discard only this process's owned unsent snapshots and prepared cache. Cleanup validates the
manifest, expected file names, ordinary entries and resolved root membership, pins Windows
parents and deletes individual files without recursive traversal. Original selected files,
unowned historical snapshots, saved/archived sources and unexpected storage contents remain.
Unknown snapshots from an older process are not inferred to be garbage. Cleanup errors log a
fixed content-free warning and defer deletion rather than broadening authority.

## Context and interruption

Existing context policy, prompts, routing, sampling, tool permissions, accepted model profiles,
step budgets and manual skill/model selection are unchanged. Source-bearing groups remain
atomic. Recovery can explicitly excerpt tool results, with existing provenance markers, while
preserving user requirements, source references, original bytes and call/result identities.
If protected source content still cannot fit, admission stops rather than silently shortening it.
Cloud source-count preflight now checks that its actual input leaves minimum reply space under
the account ceiling before saving a turn. Final provider context-overflow failures record
`context_limit`, distinct from model unavailability.

Counting and streaming use the existing owned cancellable SDK transport. Cancellation before
admission leaves a restorable draft; after admission it retains the stopped turn and partial
response. Interrupted streams are not reconnected/replayed. Explicit follow-ups reuse verified
sources. Reopening settles unfinished turns without automatically dispatching models or tools.
Stopped/crashed references survive archiving, and cloud → local → cloud switches retain source
identity and content without changing the user's selection automatically. An incompatible local
image model still stops explicitly; one combined local attachment per outgoing message remains.

## Deterministic and real-model evidence

Expanded native checks passed **291 tests in 25.952 seconds**. The final canonical-root ownership
recheck passed **85 tests in 8.943 seconds**. Coverage includes exact rejected-draft restoration,
skill chip recovery, manual retry without duplicate imports, cancellation during actual SDK
counting and streaming, released owned transports, failed persistence, commit/removal races,
shared root ownership, unknown/tampered entries, preparation/removal/close cleanup, stop/crash
reopening, archives, intact source groups under tool-result projection, explicit overflow and
cloud/local/cloud document switching. The original Windows source-lock fixture now forwards
the new optional draft flag; its source write/delete assertions remain unchanged.

The first new archive fixture omitted required completed-run assistant text, and the first
context-status test exposed generic model-unavailable classification preceding context overflow.
The fixture was corrected and context classification now precedes generic unavailability.
A command referencing a nonexistent test file did not execute tests; corrected batches above
passed. Compilation, dependency consistency and Git whitespace checks passed.

Real cloud lifecycle and the unchanged phase 4A continuation gates passed **2 tests in 111.593
seconds** on `gpt-6-luna`, using the authorized key's first line held only in memory and synthetic
sources in isolated ignored state. Stopped PDF recovery, a simulated crashed image turn, archive
recall and abandoned-draft deletion passed. Their three real responses used **845 / 958 / 999**
input tokens. The original mixed-source/scanned-PDF, follow-up/reopen/archive and actual
`filesystem.stat` continuation gate passed with all twelve production tools, actual 1,050,000
context and unchanged 128,000 profile output setting. Its turns used **1,350 / 1,467 / 1,489 /
4,111** input tokens; the restored turn executed one native call. Owned clients/threads closed
and session credentials cleared.

GPU vision passed its unchanged real format/recall/archive/tool/switch gate: real 14B → VL 4B →
14B switches, actual **16,384 context / 4,096 output**, requested GPU layers **-1** at each stage,
and verified memory bounds. Owned processes exited and user selection/profile bytes stayed
unchanged. No forced CPU vision gate was run in this phase.

The 14B document gate read the text/PDF sources and follow-ups/reopened sources correctly, including
the natural CV read without disk lookup. It failed the final explicit `filesystem.stat` assertion
on both branch runs: it answered the attached dispatch count while omitting that requested call.
The **same unchanged gate failed identically on baseline `b61f602`**, loading prior production
modules in memory without changing any checkout. This isolates an existing model tool-choice
limitation; it is not labeled a passing tool qualification or repaired by changing prompts,
sampling, routing or tool policy. Numeric summaries confirm released owned processes and
unchanged profiles. This limitation remains separate from passing attachment reading/lifecycle
and GPU vision/cloud tool gates. Other optional gates retain their prior qualification status.

Final full native regression passed **2,260 tests and 15 subtests**, with **57 optional skips**,
zero failures/errors, in **266.097 seconds**. Live gates ran separately and retain the qualification
distinctions above; skipped optional gates are not relabeled as passing. All five implementation
phases are delivered, with the existing 14B tool-choice limitation explicitly retained. No original
conversations, skills, runtime selection, credential files or accepted configurations were modified.

The bounded branch starts at `b61f602`. Pre-integration refs and worktree identities are preserved
in the verified complete-history bundle under ignored `state/backups/attachment-lifecycle-20261007/`;
prior main is retained at `archive/2026-10-07/main-before-attachment-lifecycle`. The standing user
instruction authorizes fast-forward integration and publishing main. Only the merged local feature
branch is removed; other active worktrees and remote feature/archive branches remain untouched.
