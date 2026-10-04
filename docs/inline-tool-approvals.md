# Inline approvals and quiet startup, 4 October 2026

The bounded `codex/inline-tool-approvals` change starts from local main
`e5d4831`. Startup uses the configured full-local-read flag without its
per-launch warning. Switching to cloud or sending a cloud message no longer
opens a privacy warning. A missing API key still opens the existing session-only
credential input.

Tool review replaces the message input inside the existing composer. It shows
the exact path, file content or diff, operation details, or allowlisted launch
details. Enter and keypad Enter approve; Esc denies the operation. The review
has no dialog or action-button window. Scrollable, read-only previews preserve
the full supplied details. The composer returns to its normal size after a
decision, cancellation, expiry, or shutdown; any unsent draft is preserved.
Shortcuts are scoped to the review and do not repeat when a key is held.

The existing runtime still binds approvals to exact operations, checks expiry,
permits one consumption, and applies filesystem and application allowlist
policies. Unsupported or malformed proposals are denied. A second proposal
cannot replace the one being reviewed. File operations and application launch
share this input-area review. Model prompts, routing, sampling, context limits,
accepted profiles, credentials, and user runtime settings are unchanged.

Verification:

- Final focused UI, filesystem, and host-access run: 268 passed, 1 existing
  skipped gate, 5 subtests passed.
- Existing application-launch authorization checks: 21 passed.
- Full unrestricted regression: 1,719 passed, 49 existing skips, 15 subtests
  passed, no failures.
- Native Windows UI run: 47 passed, 5 subtests passed. This covers Enter, keypad
  Enter, Esc, focus restoration, draft preservation, malformed/stale requests,
  and startup configuration. The later launch-review case is covered in the
  final focused and full runs.
- Native screenshots were inspected at 1280 × 800 and 760 × 600, including
  folder/file review and the restored composer. Synthetic paths and text only
  are retained under ignored `state/inline-approval-review/`.

Windows file-handle checks failed in the sandbox because their isolated folders
could not be opened by the native handle API. The unrestricted focused rerun
passed; this sandbox limitation is not a product failure. Tests use
repository-local temporary directories. Live provider/model qualification is
not part of this UI change and is not reported as passed.

All refs and the worktree map are preserved in a verified recovery bundle under
ignored `state/backups/inline-approvals-20261004/`. After verification, the
bounded change is committed, local main fast-forwards, and the merged feature
branch is removed according to the repository workflow. Other worktrees and
remote branches retain their existing state.
