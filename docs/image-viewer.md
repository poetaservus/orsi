# Image viewer and follow-up composer

Click an image in a message, or focus its miniature and press Enter/Space, to open
a frameless overlay filling the available screen. The chat behind it is blurred
and dimmed, with a large, sharp image and the same centered composer as chat.
The image fits the large canvas without cropping. Previous/next buttons and
Left/Right keys browse the message's images; arrow keys inside the prompt continue
editing text. Escape and the close button return to the chat.

The viewer reads the verified saved original on a worker, through its pinned
snapshot handle. A separate two-entry cache holds images bounded to 4096 × 4096;
small originals are kept at native resolution. The thumbnail cache retains its
existing bounds. Missing or changed sources show a safe fallback and cannot be
resent. Closing clears the viewer cache and blurred backdrop, and cancels outstanding work.
The backdrop captures only the app's own widget once, stays in memory and is
bounded to 1280 × 900 before blurring. The foreground image and controls remain
sharp. No desktop capture or continuously recomputed background is involved.

The shared 54px chat composer sends the viewed image with an explicit new prompt.
Its pill, controls, icon sizes, input typography and send styling come from
`app/ui/composer.py`, also used by the main window. The plus menu chooses which
of the message's images to include; the folder icon retains its existing
placeholder role. Extra files are attached through the chat composer.
Enter sends;
Shift+Enter adds a line. Cloud users may check “Include all images”; local users
send one image. Browsing retains the prompt. Working sessions disable sending, and
existing main-composer drafts are preserved rather than replaced.

Follow-ups prepare the saved references on the existing attachment worker. They
reuse the original bytes, never the displayed resized pixels, without claiming
ownership of saved sources. Once prepared, the existing send path handles model
support, API readiness, admission, manual skill selection and rejected-draft
recovery. If the viewer closes during preparation, automatic submission is cancelled
and the prompt/attachments remain available in the main composer. Unsupported models
or preparation errors similarly retain the staged draft and its normal error notice.

## Future generated images

Cloud image generation is not implemented by this change. The UI can display
explicitly supplied, app-owned output image references using
`ChatView.add_message("Agent", text, images=references)` and opens them in the same
viewer. Future image generation must import the output into the attachment store
and supply/persist that metadata. Assistant Markdown still cannot automatically
load arbitrary local files or remote images. Output display metadata is separate
from existing user-input references and does not change inference history.

## Overlay redesign verification, 7 October 2026

The focused UI group passed **96 tests and 15 subtests**. Checks cover filling
the screen, blurred/dimmed chat with a sharp foreground image, the shared
composer's dimensions and position, original 2800 × 3900 portrait detail,
navigation, local/cloud resend, missing sources and cleanup. Synthetic previews
were rendered and inspected at both the test viewport and 1920 × 1080; their
artifacts remain ignored under `state/chat-image-preview-artifacts/`.

Two earlier combined UI runs aborted in the existing copy-feedback wait with a
native Qt access violation. The viewer test fixture now retains one QApplication
for the session and detaches its temporary parent before cleanup; the final
combined run passed. Copy-button behavior and its assertions were not changed.
The full regression suite passed **2,292 tests and 15 subtests**, with **58
optional gates skipped**, in **357.51 seconds**. No live model/API qualification
was rerun for this presentation change.

## Initial implementation verification

Expanded native checks passed 162 tests and five subtests. Final viewer/composer
checks passed 41 tests. They cover high-resolution original pixels, near-screen
geometry, actual mouse/keyboard activation, navigation, prompt editing, current/all
selection, local limits, missing sources, Escape cleanup and native handle release.
Integration checks cover successful local/cloud follow-up sends, model image gates,
existing draft protection and cancellation during asynchronous preparation.
Synthetic app rendering was visually inspected; artifacts remain ignored under
`state/chat-image-preview-artifacts/`. The preview fixture's initial missing store
binding was corrected before visual acceptance.

Full regression results are recorded in [the integration workflow](git-workflow.md). Live model/API
gates are separate and were not rerun for this UI change; no API key or real user
image was accessed. User settings, model profiles, inference policies and GPU
architecture remain unchanged.

The initial full run recorded 2,287 passed, one unchanged native skill-reader
depth-fixture directory-rename denial, 57 skipped and 15 subtests in 373.36 seconds.
The first isolated 73-test reader recheck hit another directory-rename denial in
its root-replacement fixture (72 passed); these failures remain explicit evidence
and were not hidden by changing reader behavior or weakening its assertions.
The fresh second isolated reader recheck passed all 73 tests in 1.26 seconds.
The final full rerun recorded **2,287 passed, one failure, 57 skipped and 15
subtests** in **378.15 seconds**. Its failure was a different unchanged native
skill-registry directory-rename check (`test_reload_obeys_limits_and_releases_directory_and_file_handles`).
The combined final registry/reader recheck passed **all 112 tests** in **1.95 seconds**.
Both full-run denials remain unresolved Windows verification evidence; they are
not labeled passing full regressions or fixed by this display change.
