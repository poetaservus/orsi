# Vault unlock picture

9 October 2026. Bounded change from local main `c7f8916` on
`codex/vault-unlock-picture`.

## Result

The user's supplied Desktop `orsi_start.png` is copied byte-for-byte into
`app/ui/assets/orsi_start.png`. Runtime lookup uses the UI module's own asset
directory. Package data explicitly includes the image; the existing Nuitka
portable build includes the whole UI asset directory.

Successful unlock presents a frameless public picture at the locked window's
geometry before retiring that view and composing personal services. Native
exposure/paint is processed before the synchronous composition begins, excluding
queued user input. The picture fills the area with proportional centered cropping
and smooth drawing. It carries no password, profile content or provider data,
cannot be dismissed by an ordinary image click, and does not create another
personal/backend owner. Cleanup runs in `finally`, including initialization
failure. Initial locked startup and unsuccessful unlock do not load private
consumers or show an unlocked loading view.

## Focused verification

| Ignored report under `state/` | Result | Scope |
| --- | --- | --- |
| `vault-unlock-picture-focused.xml` | 18 passed, 27.81 s | Existing local/portable keyboard unlock, idle lock, retired activation, obsolete unlock, rejected action, failed drain and actual backend saved/manual/cancel key choices |
| `vault-unlock-picture-shutdown.xml` | 5 passed, 1.62 s | Existing worker cancellation, preference failure and entrypoint/ownership cleanup |

All 23 existing cases ran with Qt's native Windows platform. No final
failures/errors/skips; no new broad test suite or full 2000+ run.

An isolated native visual probe copied both the picture module and asset into a
different portable tree and loaded them there. It exercised normal/local,
maximized/portable and failed-load/portable cases. During a deliberately blocked
composition, each case verified a visible, already painted picture at exactly
the previous geometry and no visible MainWindow. Native display captures showed
the white logo and were visually inspected. A click kept the picture visible.
After composition there was one MainWindow, the same geometry/maximization,
no visible loading picture and the correct active/locked state. Evidence:
`state/vault-unlock-picture-native/7e372f3bdd82431c86526fa2bc0caf05/`.

An additional actual `app.main` event-loop probe retained the Responses backend
with a synthetic encrypted profile and no local model/provider request. Two
secondary launches, keyboard unlock, obsolete unlock and retired activation left
one visible MainWindow and one backend composition, with a synthetic saved key
ready without another key-entry prompt. Evidence:
`state/vault-unlock-picture-entry.json`.

Changed Python parses, packaging asset inclusion checks and `git diff --check`
pass. All eight pre-change configuration/selection hashes or absence match.
Preservation evidence is under
`state/backups/vault-unlock-picture-20261009/`; no actual user vault was opened,
no real key read and no user process stopped. The already running instance needs
a restart to load the changed Python code. Physical portable media/minimum-host,
live provider/model and independent security qualification remain deferred.
