# Content-free route, turn and stream diagnostics

Phase 6 starts from verified main `1186871` on the bounded
`codex/content-free-diagnostics` branch. Its scope is diagnostics only. Routing,
source selection, prompts, sampling, model/context limits, tool contracts,
permissions, recovery budgets, journal authority and the installed Python Coder
1.0.1 package retain their accepted behavior.

## Diagnostic contract

The worker logs one `[route]` JSON record after obtaining the shared route
decision. UI previews do not emit it. Labels describe the chosen route, the
existing reason, the source (`none`, `submitted`, `current_visual_task`), selected
attachment kinds (`none`, `file`, `image`, `mixed`) and effective skill scope
(`none`, `message`, `session`). Numeric fields count submitted/selected references
and selected images/files. Empty selection has source `none`. No attachment
identity, digest, filename, path, MIME value, skill name or content is included.

The worker logs one `[turn]` record for a durable terminal result. It includes
terminal status, steps, model requests, planned capability calls, settled calls,
successful/failed settled calls, semantic corrections, protocol failures,
completion failure reason and a histogram of fixed capability error codes.
Planned calls can exceed settled calls when work stops. Counts come from the
accepted result; logging does not settle, normalize or replay any call. Requests
rejected before durable admission and local control commands have no terminal
record. Result text, partial replies, call arguments, error messages and result
metadata are excluded.

`[stream]` records distinguish protocol interruption, SDK-consumed error
envelopes and provider terminal errors with fixed `origin` categories. They
contain a reviewed public event type/category, whether that type is supported by
the current text/image stream parser, an approved error code, a fixed failure
reason, the locally installed OpenAI SDK version and numeric protocol counters.
For an envelope consumed by the SDK before the parser sees it, the event fields
refer to the last parser-observed event; `origin=sdk_envelope` identifies that
distinction. Some failures produce both an originating error record and a stream
interruption record; these are diagnostic observations, not additional requests.

The event taxonomy was reviewed against OpenAI SDK **2.54.0** and the
[official Responses streaming event reference](https://developers.openai.com/api/reference/resources/responses/streaming-events).
The logging allowlist includes public audio/provider-tool/queued events so an
unsupported known event can be named without accepting it. Unknown or private
event types/codes stay `unrecognized`; unexpected labels and SDK versions stay
`unknown`. Versions accept only bounded numeric release/prerelease syntax.
Provider messages, parameters, payloads, response/item IDs, encrypted reasoning
and arbitrary exception strings are excluded. Diagnostic handler failures cannot
fail a turn or trigger recovery.

ORSI's owned rotating application-log handler also excludes all records from
`openai`, `httpx` and `httpcore` namespaces, at every level. Their raw library
debug bodies, headers and URLs cannot enter that file. ORSI's sanitized
application diagnostics remain available. This filter does not change a caller's
other logging handlers or SDK settings.

## Stream investigation and mutation ownership

Unsupported-event/provider-stream failures and `invalid_arguments` from a native
edit are distinct diagnostic domains. A rejected missing-text edit increments
the capability-error histogram and semantic corrections; a later SDK
`server_error` reports `provider_unavailable` separately. Public unsupported
events remain unsupported, with no reconnection after a stream starts. Existing
pre-stream SDK retry ownership is unchanged.

A successfully settled edit followed by an unsupported event remains saved and
durable. Reopening the conversation does not send requests or replay the edit.
Cancellation and bounded repeated-edit stops retain the same settled-work and
journal authority. The earlier retained `unrecognized` logs still cannot identify
the original private event/provider failure: this change improves future
evidence and does not reconstruct missing historical messages or SDK payloads.

## Qualification and preservation

The initial twelve new diagnostic cases failed before implementation because the
records were absent. Later fixture corrections supplied all required strict-wire
arguments and placed editable targets outside the protected portable application
root. Intermediate fixture failures are retained separately; no permissions,
acceptance prompts, existing assertions or tool behavior were changed to fix them.

Final focused native qualification passed **223 tests**, with no failures,
errors or skips, in **64.641 seconds**. Nineteen new cases exercise worker/preview
separation, message/session skill scope, image creation/follow-up identity
exclusion, public/private unsupported types, SDK envelope and provider-terminal
errors, raw-library log exclusion, malicious metadata rejection, settled-edit
no-replay and durable cancellation/repeated-stop counts. Existing streaming,
routing, inference-diagnostics and native recovery checks pass unchanged.

Final full native regression passed **2,691 tests and 15 subtests**, with
**58 optional/host skips**, no failures/errors, in **484.479 seconds**, using a
fresh repository-local temporary directory and an unrestricted Windows shell.
The skips are not passed live gates. Compilation, dependency consistency,
whitespace, protected-source preservation and credential exclusion checks pass.

All **four unchanged cloud coding cases** passed on default `gpt-6-luna`, with
the full twelve-tool catalog, using isolated synthetic files/screenshots and the
previously authorized credential in memory only. Existing-file tasks made two
approved edits each; requested-copy tasks made four approved mutations each and
preserved original bytes. Plain fix/copy turns settled 7/11 calls in 6/9 model
requests; installed-skill fix/copy turns settled 8/10 calls in 7/8 requests.
All cases had zero failed calls, semantic corrections and generated images,
exact saved bytes, grounded edits, honest unrun-check disclosures and released
transports. The installed skill entry remains unchanged. Four route and four
terminal records passed strict key/value allowlist checks and matched the actual
durable outcomes; no stream failures occurred during these live gates.

Native forced unsupported-event, SDK-envelope and provider-terminal reproductions
qualify the failure diagnostics separately from successful live coding. Existing
deterministic image-generation/edit, attachment and cancellation checks pass in
the full suite. Live image and local-model gates were not rerun for this
diagnostics-only change. ORSI did not execute Python, imports, tests or a GUI in
the cloud coding cases; saved-byte/static checks are not execution proof.

Pre-change refs/worktree maps, a verified complete-history Git bundle, numeric
test summaries and content-free settings/configuration preservation hashes are
retained under ignored
`state/backups/content-free-diagnostics-20261009/`. Diagnostics collect only fixed
categories, numeric counters and the permitted SDK release. Synthetic gate files
and conversations are separate test inputs, not diagnostic baseline snapshots.
The user's source, active conversation, runtime selection, uncommitted settings
work, installed skill, other worktrees, historical tips and remote refs are
preserved. All fourteen installed Python skill package files and twelve other
installed skill files remain unchanged. Prior main is archived before the bounded
feature commit is integrated by fast-forward; only its merged feature branch is
removed. The final guarded integration audit verifies preservation again.
