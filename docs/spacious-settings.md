# Spacious Settings and centered login

General, Models, Skills, Image Generation and Appearance use a shared card and
row layout within the existing full-window Settings shell. The content column
centers at up to 1040 pixels wide, with 28-pixel page insets, 22-pixel card
insets, 20-pixel row padding and 32-pixel group gaps. Descriptions are visible
under their labels; controls align on the right and stack below their labels
when a narrow window needs more room. Page headings use 30-pixel type, controls
and setting names use 18 pixels, and descriptions use 16 pixels. Explicit
antialiasing and vertical hinting follow the selected theme/font override.
Long action captions wrap inside narrow cards rather than widening them.

Skills separates import/review from installed skills. Source entry has its own
line and compact file/folder/preview actions. Install and Remove remain distinct
actions. Installed entries show their descriptions, preserve native selection
and keyboard behavior, and use a scrollable list. Empty installations show a
plain empty state. Image preferences share the same responsive rows and retain
their explicit Save/Reset actions. Existing theme imports/exports, setting
persistence, skill review/installation, busy states and draft handling retain
their owners and behavior.

The regular unlock panel has a password field without the redundant caption,
a centered 18-pixel Unlock button and a centered More/Less link beneath it.
The field keeps its accessible name and password behavior. The existing
recovery and alternate-profile options remain behind More. These adjustments
apply to the login instance in `profile_login.py`; the shared Personal profile
workspace source and its presentation remain unchanged.

## Essential verification, 15 October 2026

The final essential native run passed **54 tests in 151.84 seconds**, with no
failures, errors or skips. After the last visual correction to wrapped action
heights, all **nine targeted checks passed in 18.19 seconds**. They cover compact
translated controls, settings descriptions, image saving, real skill import/
installation/removal and font selection. The prior expanded run also passed
the encrypted-profile font lock/restart/unlock check separately. Four final
compact-language checks passed in 4.62 seconds, including native button content
measurements to verify that wrapped captions fit vertically.

Native previews and reachability checks cover all five redesigned modules in
Original and Conformist at 760×600, 1280×900 and 1920×1080: 30 screen states,
plus collapsed/expanded login previews. Personal profile geometry and font
measurements match its pre-change baseline in all 20 theme/size/section states;
transient page-animation covers are excluded from these measurements.

The initial essential run exposed missing greeting wrapping and clipped sound
text, corrected in the final layout. Its obsolete full-width greeting and old
type-size expectations were updated to the requested cards/typography; a
missing test import was repaired. The unchanged Skills composer-enabled
assertion also fails on an untouched archive of starting main `7b15478`:
full-window Settings already disables the chat backdrop. That test now closes
Settings before using the picker and verifies that the composer is enabled
again, without changing application busy-state behavior. A later compact
Armenian overflow was fixed by wrapping long action captions; its unchanged
reachability checks pass in both themes.

Reports, synthetic previews and the content-free Personal profile measurements
are under ignored `state/spacious-*.xml` and `state/spacious-settings-preview/`.
All pytest runs use repository-local basetemp paths. The full suite and live
model/API gates are outside the user's necessary-UI-test scope. Translation
catalogs, accepted model profiles, prompts and inference policy were untouched.
