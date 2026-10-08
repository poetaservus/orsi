# Notification corrections, 8 October 2026

The bounded `codex/notification-bugfixes` change starts from local main `696162a`.
It addresses foreground sounds, clipped audio onset and notification settings
controls that were not visible in the user's settings view.

Automatic notification events now check whether ORSI is active before playing
sound or posting a desktop notification. Responses, approvals, images and errors
all stay quiet while the user is in ORSI. Background and minimized windows retain
notifications. Returning to ORSI cancels an automatic sound or pending decode;
the explicit preview button remains available in the foreground. The condition
is checked again after asynchronous decoding to prevent a late alert after focus
returns.

The sound is decoded completely before playback, then supplied as an uninterrupted
PCM buffer to the output device. Playback adds 150 ms of silence before the first
original frame, allowing the output device to start before the audible onset,
and another 150 ms after the last original frame for draining. Every decoded
sample remains in order, without trimming or fading the beginning. The selected
sample is cached until the file, selection or file metadata changes. The original
OGG files and existing user preferences remain untouched.

Playback uses owned decoder, buffer and audio-sink resources. Cancellation,
selection changes and shutdown stop decoding/output and the short-lived output
status timer. This portable PySide version exposes the audio state signal using
the old enum namespace; reading the typed state getter avoids its conversion
error. A native smoke run exposed that incompatibility, and the repaired run
completed successfully.

The enable checkbox, sound selector and preview button now occupy their own
full-width rows beneath the notification labels. Controls no longer depend on
space to the right of the explanatory text. The preview uses a bundled vector
play icon, avoiding unavailable font glyphs at larger display scaling. General
settings retains `noti_1.ogg`, `noti_2.ogg`, Silent and custom-file choices, and
preserves saved values across closing/reopening settings and restarting ORSI.

## Verification

- Focused unrestricted Windows regression: 64 passed in 25.12 seconds, including
  existing settings, approval and image acceptance checks.
- Final targeted notification/audio/settings recheck after the scalable preview
  icon change: 31 passed in 11.33 seconds at 200% scaling.
- Byte-level tests prove the complete PCM stream, including first and last frames,
  is surrounded by silence rather than trimmed; actual decoding of both bundled
  OGG files covers their complete duration and cache reuse without output.
- Native Windows smoke verification played `noti_1`, `noti_2` and `noti_1` again
  to completion without audio errors. Each submitted playback buffer contained
  the entire decoded original, and owned output resources were released.
  Automatic foreground events created no player. This checks the submitted
  audio and device completion; no acoustic recording was taken.
- Normal/minimum settings renders were inspected at 100% and 200% scaling.
  Tests exercise actual checkbox clicks, sound selection, scrolling and opening/
  reopening settings with isolated preferences. New controls remain visible,
  clickable and within the viewport.
- Compilation and whitespace checks passed. Final full unrestricted Windows
  regression passed 2,437 tests and 15 subtests, with 58 separately skipped
  optional/live/host gates, no failures or errors, in 400.28 seconds. Live
  model/provider gates were not run for these UI/audio fixes.
- The initial unrestricted full suite reported 2,436 passed, one failure and one
  teardown error in the unchanged skill installer's temporary-folder cleanup,
  with 58 skips and 15 passing subtests, in 426.33 seconds. The failed run remains
  recorded separately; installer code and acceptance prompts were not changed.
- The first installer-only recheck recorded 59 passed plus the same failure and
  teardown error in 21.93 seconds. A further isolated recheck of all four process-
  ownership exit paths passed, including the failed case, with no native cleanup
  errors. Its observer recorded only error codes and did not alter cleanup or
  test assertions. These rechecks are separate from the final full-suite result.

Content-free verification artifacts are retained under ignored
`state/notification-fixes-preview/`, `state/notification-fixes-focused-final.xml`,
`state/notification-fixes-final-icon.xml`, `state/notification-fixes-full.xml`,
`state/notification-fixes-installer-recheck.xml`,
`state/notification-fixes-cleanup-diagnostic.xml` and
`state/notification-fixes-full-final.xml`.
Preserve prior main at `archive/2026-10-08/main-before-notification-bugfixes`,
commit after verification, fast-forward local main and remove only the merged
feature branch. Other worktrees and remote refs remain outside the operation.
