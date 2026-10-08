# Desktop notifications, 8 October 2026

The bounded `codex/desktop-notifications` change starts from local main `d6c2d6b`.
ORSI sends one attention event when a response finishes, an actionable inline tool
approval appears, an image result arrives, or a task fails. Streaming updates,
restored history, duplicate/resolved approval requests, cancelled tasks and late
callbacks during shutdown remain quiet. An image result uses one image event,
rather than a second response event.

Notifications are enabled by default. The selected sound plays in foreground or
background; desktop notifications and taskbar attention appear when the window
is inactive or minimized. Clicking a desktop notification restores ORSI and
focuses a pending approval, or the message input. Notification messages use fixed
status text, without conversation content, prompts, filenames or tool previews.

General settings replaces the Notifications placeholder with an enable checkbox
and a sound selector/preview control. Choices include `noti_1.ogg` (default),
`noti_2.ogg`, Silent, and a custom local audio file. The two supplied desktop
files are bundled byte-for-byte under `app/ui/assets/sounds/`; the original desktop
files remain in place. A missing custom file falls back to the bundled default.
The asynchronous audio picker preserves the previous choice on cancellation.

The existing ignored `state/ui_preferences_v1.json` stores the notification
selection. Startup does not rewrite user preferences. Saving merges the existing
document and retains unrelated fields; unreadable preference documents are not
replaced with partial notification settings. Greeting saving retains notification
settings. No user runtime settings were edited during implementation or testing.

Playback uses an owned Qt media player, created on demand. Windows shell
notifications explicitly suppress the extra system chime, so only the selected
sound plays. The owned notification-area entry handles click callbacks and
re-registers after Explorer restarts. Closing the app stops/releases playback,
rejects an open audio picker and removes the owned tray entry. Platforms without
native tray support retain sound/taskbar attention; notification preferences do
not modify tool approvals, prompts, routing, model profiles or inference policy.

## Verification

- Focused unrestricted Windows regression: 51 passed in 18.39 seconds, covering
  notification events, playback paths, preference merging/restoration, custom
  picker cancellation, silent mode, click restoration, native ABI/sound flags,
  Explorer recovery, shutdown and existing settings/approval/image acceptance.
- A native Windows smoke check played both OGG files to end-of-media without
  audio errors, confirmed shell delivery acceptance, restored the minimized
  window and released owned resources. This verifies API acceptance and playback;
  Windows notification preferences still determine visible banner delivery.
- Native renders at 1280 × 800 and 760 × 600 were inspected; the new General
  controls remain reachable without clipping.
- Both bundled audio hashes match the supplied desktop originals. Compilation
  and whitespace checks passed.
- The initial restricted run encountered two existing attachment-store Windows
  handle access denials. The same image checks passed with unrestricted native
  access; these are sandbox evidence, not product failures. A synthetic test
  fixture and handled native callback were corrected before final verification.
- Final full unrestricted Windows regression: 2,424 tests and 15 subtests passed,
  with 58 separately skipped optional/live/host gates, no failures or errors,
  in 391.68 seconds. Live model/provider gates were not run for this
  notification-only change.
- The initial unrestricted full suite reported 2,423 passed, one failure and one
  teardown error in the unchanged Git skill installer's temporary-folder cleanup,
  plus 58 skips and 15 passing subtests, in 386.99 seconds. All 60 installer tests
  passed an independent recheck in 18.35 seconds. The initial full run is retained
  as failed verification evidence; no installer code or assertions were changed.

Ignored verification artifacts are under `state/notifications-preview/`,
`state/notifications-focused-verified.xml`, `state/notifications-full.xml`,
`state/notifications-installer-recheck.xml` and `state/notifications-full-final.xml`.
Preserve prior main at
`archive/2026-10-08/main-before-desktop-notifications`, commit after verification,
fast-forward local main, and remove only the merged local feature branch. Other
worktrees and remote refs remain outside this operation.
