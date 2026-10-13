# Main integration and publication, 14 October 2026

The user requested that all current work be consolidated on main, published to
GitHub, and left with clean Git history and branch layout. Local main started at
`51caff8`, fifteen commits ahead of `origin/main`; every outstanding feature tip
was already included. `codex/final-integration-20261014` contains only the pending
notification sound, corresponding test maintenance, and this integration record.

## Integrated changes

The user's existing `noti_1.ogg` is retained byte for byte. Its source duration is
1,290,317 microseconds, calculated from the final Ogg granule and sample rate.
The decoder/cache/cancellation test now checks each sound's own source duration
within two milliseconds instead of assuming both assets last about three seconds.

Six existing integration tests had stale expectations after the already merged
compact policy and question-presentation changes. Policy assertions normalize
whitespace and check the current equivalent operational requirements. Scripted
models explicitly answer the isolated question-form request; the tests check its
exact system prompt, roles and original request/reply payload. File access,
permissions, execution-journal and no-guessing assertions remain in place.
Production prompts, acceptance requests, routing and model profiles are unchanged.

## Verification

The first audio/notification/branding run passed 35 checks and failed the obsolete
sound-duration expectation. The corrected run passed all 36 in 10.93 seconds.
The first full native suite passed 3,779 checks and 15 subtests, skipped 61 and
failed the six stale expectations plus one immediate Windows directory rename,
in 781.30 seconds. The unchanged complete skill-reference and Git-installer handle
groups subsequently passed all 133 checks in 20.46 seconds. The affected policy,
file-access and question-presentation groups passed all 101 checks in 12.39 seconds.

The final complete native suite passed **3,786 checks and 15 subtests**, with
**61 skips**, no failures/errors, in **773.73 seconds**. Results are retained in
`state/integration-20261014-verified.xml` and `.log`. All runs use checkout-local
temporary/cache directories and XML/log reports under ignored `state/`.
Opt-in live-model, paid API and unsupported host gates remain separate skips;
these deterministic checks do not qualify model quality or live integrations.
Changed Python files parse, dependency consistency and whitespace checks pass,
and an AST comparison confirms every existing acceptance `run` call is unchanged.

## Recovery and branch layout

The original refs, worktree inventory, status, pending sound and verified
complete-ref history bundle are retained in
`state/backups/git-integration-20261014/`. The pre-integration main tip is preserved
at `archive/2026-10-14/main-before-final-integration`.

Inactive historical archive branches become recovery tags with identical names
and commit IDs. The already merged `codex/profile-personalities` tip is preserved
as `archive/2026-10-14/codex-profile-personalities` before removing its branch.
The separate historical checkout and all detached worktrees retain their paths,
HEADs and files. No historical code replaces current main, and no other checkout
is reset or removed. Publication sends only main, without forcing or rewriting
remote history; recovery tags stay local as in the existing repository workflow.

The outgoing-commit audit checks for private runtime paths and credential
patterns without printing secret values. Private state, profiles, model weights,
runtime dependencies, recovery bundles and generated test files remain ignored.
The fifteen existing outgoing commits (153 unique blobs) and all nine staged
integration files passed this audit with no private-path or credential-pattern
findings. These checks do not claim to detect every possible secret format.

## Development direction

The user intends to polish the cloud experience in this repository. A future
local-first ORSI will be developed separately in a new repository, with a smaller
instruction and capability budget suitable for CPU/system-memory inference.
This is a future direction; this integration does not remove existing local mode.
