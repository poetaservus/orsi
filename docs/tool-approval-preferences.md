# Tool approval preferences

This change starts from verified local `main` at `d850fd7` on
`codex/tool-approval-preferences`.

The General settings **Tool execution approval** switch is active. ON is the
default and retains the existing inline composer review, including Enter to
approve and Esc to deny. OFF runs eligible tool calls automatically without
opening a review, resizing the composer, or raising an approval notification.

The selection persists as the boolean `tool_approval_required` in ignored
`state/ui_preferences_v1.json`. Loading does not rewrite preferences. Missing,
invalid, or unreadable values default to ON; saving preserves other preference
fields and leaves unreadable documents intact. Changing the switch applies to
future approval requests. A request already displayed still needs a decision.
Scoped skill runtimes share the same selection.

Automatic execution still validates arguments and paths, evaluates the existing
permission rules, and obtains a consumed approval bound to each exact call.
Explicit DENY rules, protected paths, application allowlists, resource identity
checks, cancellation, expiry, executor checks and durable outcome receipts retain
their existing behavior. The preference does not enable additional tools.

File operations report transient activity through the existing working-status
area, for example `Writing xyz.py…` or
`Copying xyz.py from Documents to Desktop…`. Renamed copy/move destinations are
included. Read operations retain their generic labels. File contents and edit
fragments never enter these messages or the content-free journal.

Prompts, routing, model profiles, sampling, context policy and installed skills
are unchanged. User runtime settings are not migrated or replaced during
implementation. This bounded change remains on `codex/tool-approval-preferences`
as requested; local `main` and other worktrees are not advanced.

## Verification

- Final expanded focused Windows checks: **258 passed**, no skips, failures or
  errors (91.815 seconds). Coverage includes persistent ON/OFF selection,
  reopening, mouse/keyboard access, preserved drafts and unrelated settings,
  invalid/unreadable preferences, shared skill-runtime selection, independent
  exact-call consumption, DENY/schema rejection, cancellation, unchanged pending
  reviews and re-enabling human review.
- Full unrestricted Windows regression: **2,753 tests and 15 subtests passed**,
  **58 optional/host skips**, no failures or errors (546.63 seconds), using
  repository-local `state/ta-full` temporary state and `state/ta-cache-full`
  cache. The result is retained in ignored `state/tool-approval-full.xml`.
- Native filesystem checks perform real writes, edits, folder creation, copies
  and moves with OFF, including changed-target rejection and content-free
  receipts. The allowlisted launch check substitutes a synthetic launcher.
- A real conversation worker with saved OFF writes its fixture and delivers
  `Writing xyz.py…` without an approval signal, notification or composer review.
  Qt runs offscreen; synthetic settings/status renders at 1280 × 800 were
  inspected under ignored `state/tool-approval-ui-preview/`.
- Compilation, dependency consistency and whitespace checks passed.

Live provider/model gates are not run for this change. Existing opt-in/host
skips remain separate from passed deterministic checks. Early development runs
are retained under ignored `state/tool-approval-*.xml`; sandbox handle failures
are separate from unrestricted Windows verification.
