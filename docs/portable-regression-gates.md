# Portable regression test maintenance, 10 October 2026

This bounded change starts from local main `c6aa4f9` on
`codex/portable-regression-gates`. It repairs the nine existing failures recorded
in the portable-runtime verification. Only test code and verification notes
change; application behavior and acceptance prompts remain unchanged.

## Repairs

Five persistence cases now inject failure or pause at
`ConversationStore._save_document`, the current save boundary, instead of an
old `JsonStore` instance that is no longer used for saves. Their assertions still
require draft ownership retention after failed persistence, serialization of
abandonment against commit, reference revocation, retention of completed writes,
retry blocking, and journal recovery without replaying an edit.

The two configured-access startup cases now provide an application root and use
the real Qt application, desktop owner and profile controller. Only the event
loop, backend composition and unrelated loading cover are stubbed. They retain
the original exact configured-access assertion and startup-warning rejection,
and also check that no-profile composition requests session credentials. Created
windows and profile controllers are cleaned up explicitly.

The local/portable profile-tab cases previously clicked the center of a
stretched radio button. That click did not select the intended choice on the
off-screen Qt platform. They now scroll to the choice and click the style's
radio-indicator rectangle, then explicitly check the selected choice before
continuing. They still exercise actual mouse input, uncommitted tab edits,
encrypted saving, lock clearing and unlock retention; no policy assertion was
removed or bypassed.

## Necessary verification

Following the user's request to run only necessary tests, this step did not
repeat the full suite or run live provider/model gates.

- An initial nine-case run passed all seven repaired setup cases and failed the
  two off-screen profile cases at the added choice-selection assertion. This
  isolated the input problem before saving: **7 passed, 2 failed in 6.19 s**.
- After fixing that click, the two off-screen profile cases passed:
  **2 passed in 5.76 s**.
- The final combined run of all nine affected cases passed on off-screen Qt:
  **9 passed in 7.84 s**.
- Only the four changed UI cases were additionally checked on native Windows:
  **4 passed in 6.07 s**. This covers both configured-access values and both
  local/portable profile modes on each platform.

These runs used an unrestricted Windows shell for native filesystem handles,
fresh repository-local `--basetemp` and cache directories under `state/prg-*`.
The final runs had no skips. `git diff --check` passed. Evidence is beneath
ignored `state/` as `portable-regression-gates-{repro,ui-offscreen,affected,ui-native}`
with `.xml` and `.log` extensions. No new full-suite pass is claimed.

All fourteen settings/runtime/artwork fingerprints match the starting values,
and all four other worktree tips and branch attachments are unchanged. Recovery
refs, worktree records and content-free fingerprints are under ignored
`state/backups/portable-regression-gates-20261010/`.

Prior main is preserved at
`archive/2026-10-10/main-before-portable-regression-gates`. Integrate by local
fast-forward and remove only the merged feature branch. No remote publication.

The next release task is to assemble a sanitized pilot package with fresh
instance state, then qualify that exact artifact on portable media and another
Windows host/account. The previous fresh cloud-runtime check remains recorded
in [portable-runtime verification](portable-vault-packaging.md).
