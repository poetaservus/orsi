# Desktop unlock/window and saved-key follow-up

9 October 2026. Started on `codex/vault-unlock-lifecycle` from local main
`39da460` after the user reported a key prompt after unlock and two O.R.S.I
windows remaining visible. The user was unsure which credential policy was
selected. No real vault was opened or real key inspected to investigate this.

## Findings and correction

A simple isolated native Windows unlock initially produced one visible window
and loaded a synthetic saved key under the saved policy. That did not reproduce
the user's exact sequence. Six local/portable regression reproductions then
demonstrated three actual lifecycle defects:

- A retired locked window's activation callback could show it again.
- A delayed second unlock from the retired page could close the newly unlocked
  session, attempt an empty password and leave the replacement locked again.
- An action rejected before changing the session still rebuilt consumers against
  the same active authority, retaining a second hidden owner until later lock.

Replacement now marks the previous window closing, disables/hides it and shuts
down activation/sound resources. Page actions are accepted only from the current
window, and the transition guard stays active through replacement. Rejected
actions that leave the current session unchanged preserve its existing window,
consumers and credentials and display the error in place. Failed-drain owners
remain hidden/alive until they can be retried safely. Geometry/maximization is
carried forward. The locked shell now says Locked/Unlock your personal profile;
it does not show the generic welcome as though personal preferences had loaded.
Locking also rejects pending credential dialogs; an obsolete modal callback
cannot bind a key after its profile/window has been retired.

The desktop previously admitted repeated launches without coordination. A
per-application-directory Qt lock now admits one owner, with same-user local
socket activation of its current window. Secondary launches exit before importing
the full UI, reading selected profile contents or composing inference. Locks are
released on shutdown/startup failure, recovered after an owner process crashes,
and do not exclude another application directory. This follows Qt's
[long-running lock](https://doc.qt.io/qt-6/qlockfile.html) and
[local-server](https://doc.qt.io/qt-6/qlocalserver.html) APIs; the explicit lock is
needed because Windows local servers alone can share a pipe name. IPC carries
no password, credential, profile command, file body or tool request.

The key prompt could also be intentional Ask behavior, which the old screen
did not make sufficiently clear. Settings now reports whether an API key is
saved for this connection/profile and whether automatic use is enabled. Ask
mode with a saved key presents an explicit Use saved key / Enter a different
key / Cancel decision. Only Use saved key enables the saved policy; manual and
cancel paths preserve Ask. No value is displayed. An unavailable cloud provider
does not present silently ineffective credential-save controls. Readiness errors
are fixed actionable messages rather than unhandled UI exceptions.

## Focused verification

| Ignored report under `state/` | Result | Scope |
| --- | --- | --- |
| `vault-unlock-lifecycle-controls.xml` | 22 passed, 22.55 s | Retired/second unlock/rejected action, locked startup and previous saved-key/import UI cases |
| `vault-unlock-lifecycle-new.xml` | 16 passed, 14.98 s | Five launch-ownership cases, five shutdown cases, six real-backend unlock/key-choice cases |
| `vault-unlock-lifecycle-regression.xml` | 55 passed, 36.16 s | Affected profile transitions, retry, migration, settings, notification, credentials and inference checks |
| `vault-unlock-lifecycle-windows-release.xml` | 13 passed, 13.63 s | Critical launch/window/key cases using Qt's actual Windows platform |
| `vault-unlock-lifecycle-entry-final.xml` | 5 passed, 0.95 s | Startup/loop/service failures release ownership and inference |
| `vault-unlock-lifecycle-modal-final.xml` | 12 passed, 12.73 s | Native Windows key choices, lock during a key dialog, image-viewer lock and saved-key replacement |

**95 distinct checks passed**, including 23 using Qt's native Windows platform,
with zero final failures/errors/skips; repeated cases across reports are counted
once. Six new lifecycle reproductions failed
on the original code (`vault-unlock-lifecycle-repro.xml`). An initial native
batch exposed a test constructor/import interaction; exiting secondary startup
before importing the full UI removed that interaction and unnecessary imports.
No acceptance prompts were changed. All temporary/cache directories are local
`state/vault-unlock-lifecycle-*`. The full 2000+ suite was not run.

The new real-backend cases retain actual Responses configuration/catalog storage,
the provider-specific connection ID and encrypted paths, restart at the locked
shell, use keyboard unlock, load the protected greeting and exercise the actual
saved-key decision dialog. They test saved, manual and cancel choices, future
unlock reuse and exactly one visible MainWindow. Backend readiness binds only
synthetic credentials; no provider request is made.

An additional isolated desktop-entrypoint probe ran `app.main` with Qt Windows,
the actual Responses backend and a synthetic profile. Two secondary processes
launched the same application directory, once before unlock and once afterward.
Both exited without composing a window. The primary exercised keyboard unlock,
an obsolete second unlock and retired activation, then processed events: one
visible main window, one private/backend composition, greeting loaded and saved
key ready without a key-entry prompt. The content-free result is
`state/vault-unlock-native-entry.json`. Its Settings capture was visually inspected
at `state/vault-unlock-native-entry.png`; the saved-key status is legible. All
temporary probe windows/child processes closed. The real desktop launcher still
invokes this same entrypoint from its own directory.

Changed Python files compile, `git diff --check` passes and ordinary `app.main`
import leaves crypto unloaded. All eight pre-change configuration/state/selected
profile hashes/absence match after verification. Content-free refs/worktree maps
and hashes are under `state/backups/vault-unlock-lifecycle-20261009/`. Preserve
prior main at `archive/2026-10-09/main-before-vault-unlock-lifecycle`, commit the
bounded fix, fast-forward local main and remove only its merged local branch.
Other worktrees, actual vault contents and remote branches remain untouched.

These checks do not establish that the user's particular profile contains an API
key. Settings now exposes that fact without showing the value. Keys in another
profile/provider connection are not automatically searched, copied or enabled.
Already running pre-fix processes must be closed once to load the updated code.
Physical SSD/minimum-host/live-provider and independent security gates remain
deferred; no remote publication is performed.
