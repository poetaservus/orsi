# Vault picture stacking and fades

9 October 2026. Bounded change from local main `e21cd84` on
`codex/vault-picture-fade`.

The loading picture previously raised itself once but had no persistent
topmost flag. It now uses Qt's
[WindowStaysOnTopHint](https://doc.qt.io/qt-6/qt.html#WindowType-enum).
Only this temporary public picture is topmost; the normal application retains
its existing window behavior and the supplied portable asset is unchanged.

Both transitions animate native
[window opacity](https://doc.qt.io/qt-6/qwidget.html#windowOpacity-prop) over
240 ms with InOutCubic easing. Fade-in completes before synchronous private
composition, so it cannot freeze halfway through while loading. Fade-out starts
after the replacement is shown, revealing that ready view (or the locked error
view). A short local event loop keeps paint/animation timers alive while queued
user input and socket notifiers remain excluded. The existing transition guard
remains active; retired views are collected after fading to avoid destroying
the old page inside the local event loop. Animation and picture cleanup run in
`finally`, including failure and application quit.

## Focused verification

| Ignored report under `state/` | Result | Scope |
| --- | --- | --- |
| `vault-picture-fade-focused.xml` | 18 passed, 33.57 s | Existing local/portable keyboard unlock, idle lock, stale activation/unlock, rejected action, failed drain and actual backend credential choices |
| `vault-picture-fade-shutdown.xml` | 5 passed, 1.26 s | Existing worker cancellation, preference failure, entrypoint failure and ownership cleanup |

All 23 existing cases passed with Qt's native Windows platform, with zero final
failures/errors/skips. The full 2000+ suite was not run.

A native probe used a relocated copy of the picture module/asset, synthetic
encrypted profiles and an owned second application process. Normal/local,
maximized/portable and failed-load/portable cases all verified:

- Actual Windows `WS_EX_TOPMOST`, and `WindowFromPoint` still resolving to the
  picture after raising the other process's overlapping normal window.
- Both fades produced monotonic intermediate Qt opacity and native layered-window
  alpha values, ending exactly at 1/255 and 0/0 respectively.
- Full opacity before deliberately blocked composition; the replacement was
  visible before fade-out and was not itself topmost.
- An obsolete unlock callback during each fade did not create another owner.
- Preserved geometry/maximization, one final MainWindow and no loading picture.

Each fade yielded 12–16 native samples. Native display captures of fade-in,
full opacity and fade-out were visually inspected. The helper process and all
synthetic windows closed. Evidence:
`state/vault-picture-fade-native/3e8b992738cc4650bd49873f2060bcd5/`.

An actual `app.main` event-loop probe with a synthetic encrypted profile and
Responses backend also passed: two secondary launches, keyboard unlock,
obsolete unlock and retired activation left one visible main window and one
backend composition. No extra key-entry prompt and no provider request. Evidence:
`state/vault-picture-fade-entry.json`.

Changed Python parses and `git diff --check` pass. All eight pre-change
configuration/selection hashes or absence match. Content-free preservation
evidence is under `state/backups/vault-picture-fade-20261009/`. No real vault was
opened, real key read or user process stopped. An already running instance needs
a restart. Physical portable media/minimum-host, live provider/model and
independent security qualification remain deferred.
