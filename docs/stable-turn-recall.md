# Stable conversation recall

This fix starts from local main `3b9ed54` on `codex/stable-turn-recall`.

The reported first cloud turn read a project and began an answer, then stopped
after repeated history calls. A deterministic regression reproduced the exact
`conversation.read_turn` error: “The recalled turn changed; restart at offset zero.”
Each page's durable receipt changed the active turn being paged. Restarting also
embedded prior recall output inside later recall output, increasing its size.
The return to model work after the initial answer is the existing completion
review; its tools and request budgets remain available.

Recall now retains immutable snapshots addressed by turn ID and content revision.
Continuations use the snapshot from their `expected_revision`, even after later
receipts or the target's completion. An initial read without a revision can
capture newer work without invalidating an older chain. Nested recall output is
replaced by explicit receipt headers; original durable records remain intact.
Expired skill bodies and opaque provider reasoning remain excluded.

Snapshots stay in memory only, with ceilings of 16 snapshots and 64 MiB combined.
Reaching either ceiling refuses an additional snapshot without evicting pages
already in progress. Starting another user turn or conversation, or locking the
protected profile, clears the cache. Session checks, UTF-8 boundaries, revision
checks, approvals, cancellation and repeated-call limits remain in force.
No acceptance prompts, routing or model profiles change.

Qualification passed 155 distinct focused checks across recall, long context,
context admission/recovery, durable conversations, completion review, provider
replay, cloud streaming and the default local context budget. Thirteen new
regressions include a first-turn cloud flow using the real SDK/stream adapter
with a simulated transport, plus continued pages after context projection.

The initial focused run exposed four failures in two older replay test scripts;
an isolated process using unchanged main production modules reproduced them.
Those scripts now supply the existing completion-review response and locate
replayed output by identity rather than a fixed pre-task-frame index. Exact
output order, arguments, results, permission and persistence assertions remain.
The final replay recheck passed all 29 checks; the other 126 distinct checks had
already passed with the final production code. Reports and content-free Git
preservation evidence are under `state/` and
`state/backups/stable-turn-recall-20261011/`. Full-suite, live provider/model and
browser/app visual gates were not run for this history-only fix.
