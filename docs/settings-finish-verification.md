# Settings consistency, transitions and loading logo

## Missing selected profiles, 10 October 2026

Branch `codex/missing-profile-entry` starts from local main `e596c1a`. A saved
locator no longer implies that its profile is present. Startup inspects public
file metadata before presenting the login form. A missing directory shows
**Profile not found**, explains deletion, relocation or disconnected storage,
and offers Create profile, Check location again, Select existing, current
unencrypted storage and encrypted-backup restore. Password and recovery-key
fields are absent until the location is present again. The previous path stays
visible as a previous location; its locator and copy registry remain intact.

Selection and unlock repeat this check, including when storage disappears
during opening. Missing required files in an existing directory report recovery;
access failures report unavailable storage. Missing paths are never recreated
by an unlock attempt. Rechecking a reconnected profile restores its login flow;
canceling creation preserves the missing-profile screen and choosing a new
profile opens only that profile. Fresh startup without a saved selection still
offers only Create profile. Pending deletion retains its retry screen.

Only necessary checks ran on native Qt 6.12.0: **32 distinct targeted cases
passed**, covering local/portable and encrypted/plain missing selections,
reconnection, actual folder deletion and replacement, disappearance before and
during unlock, missing required files, denied access, existing onboarding,
password/recovery/backup controls, deletion retry, and five real `pythonw`
startup cases. The first run passed 30 cases; two replacement-flow assertions
incorrectly counted fields in a closed dialog. Their corrected visible-field
checks passed. Four storage-error cases passed again after making access-denied
errors consistent across profile types. There were 38 executions total; no
full-suite repeat. All runs used repository-local `--basetemp`. Raw logs/XML are
under `state/missing-profile*-native.*`; the final distinct results are in
`state/missing-profile-final-native.xml`.

An isolated appearance check captured normal and compact missing-profile panels
and the reconnected login, with all actions reachable. The three visually
inspected captures and report are under `state/missing-profile-preview/`.
Zero chat compositions or network attempts; the owned profile was released.
No live provider/model gates or portable rebuild were run.

Fourteen settings/runtime/artwork fingerprints and all four other worktree tips
and attachments are unchanged. Recovery evidence is under
`state/backups/missing-profile-entry-20261010/`, with prior main preserved at
`archive/2026-10-10/main-before-missing-profile-entry`. Commit, fast-forward local
main and remove only the merged feature branch; no remote publication.

## Profile-first startup and terminology, 10 October 2026

Branch `codex/profile-first-startup` starts from local main `02b20d4`. The login
lock mark and O.R.S.I wordmark are removed. Profile-facing headings, fields,
storage/import/export actions and quota feedback now consistently say "profile";
internal encrypted-storage identifiers and record formats are unchanged.

With no saved selection, startup shows the same dark panel with only **Create
profile**, before composing chat or inference clients. Canceling or failing
creation keeps this panel and preserves existing files. Successful creation opens
the selected local or portable profile. Existing encrypted/plain profiles,
unreadable selections and deletion recovery retain their appropriate actions.
An explicit choice to use current unencrypted storage still works for that app
session; a later fresh launch without a selected profile returns to creation.

Only necessary checks ran on native Qt 6.12.0: **28 distinct targeted cases
passed**, including five new onboarding cases, six actual `pythonw` desktop
launch cases, locked startup, explicit legacy transitions, deletion retry,
password/recovery/backup controls, image storage/export, skill management and
configured host-access propagation after profile selection. The first run had
25 passes and three stale test assertions: two old image-export labels and a
button inventory that included a closed dialog. Only the seven cases sharing
those assertions were rechecked, all passing; application logic was unchanged
for those repairs. There were 35 executions total, without a full-suite repeat.
Both test runs used repository-local `--basetemp`; raw XML/log evidence is under
`state/profile-first*-native.*`, with final distinct results in
`state/profile-first-final-native.xml`.

A separate native appearance check rendered the create-only panel, normal and
compact unlock panels and authentication feedback. It verified removal of the
branding, profile wording and reachability of all five existing login actions.
Four visually inspected captures and its report are under ignored
`state/profile-first-preview/`. Zero network attempts; the owned profile was
released. No live provider/model gates or portable rebuild were run.

Fourteen settings/runtime/artwork fingerprints and all four other worktree tips
and attachments are unchanged. Recovery evidence is under
`state/backups/profile-first-startup-20261010/`, with prior main preserved at
`archive/2026-10-10/main-before-profile-first-startup`. Commit, fast-forward local
main and remove only the merged feature branch; no remote publication.

## Vault login redesign, 10 October 2026

Branch `codex/vault-login-redesign` starts from local main `6d6117d`. The login
panel now uses the Settings gradient (`#090c15` to `#1d2637`) and a centered,
600-pixel-wide card with a vault mark, O.R.S.I wordmark, profile summary, explicit
field labels and a prominent unlock action. Profile choices, unencrypted storage
and encrypted-backup recovery remain separate visible actions beneath the form.
The entire card content scrolls when needed in smaller windows. Existing action
handlers, password/recovery semantics, backdrop blur and 16-pixel radius remain.

Only necessary checks ran: **11 existing native cases passed in 12.30 seconds**
on Qt 6.12.0, using `--basetemp state/vault-login-native`. They cover failed and
successful password entry, lock/unlock isolation, profile creation/selection,
continue-without-profile transitions, deletion retry and post-deletion choices.
Native XML/log evidence shares that prefix. No new tests, full-suite repetition
or live provider calls.

A separate synthetic native check verified every login button is reachable at
1280×800, 1000×700 and 760×600; failed authentication shows feedback and clears
secrets; New/Select open the existing dialogs; Restore opens the existing backup
picker; recovery-key Enter and the password unlock button both open the vault.
Four captures were visually inspected. Evidence is under ignored
`state/vault-login-preview/`; zero network attempts and the synthetic profile
released. Only local source changed; no portable package was rebuilt.

Fourteen settings/runtime/artwork fingerprints and all four other worktree tips
and attachments are unchanged. Recovery evidence is under
`state/backups/vault-login-redesign-20261010/`, with prior main preserved at
`archive/2026-10-10/main-before-vault-login-redesign`. Commit, fast-forward local
main and remove only the merged feature branch; no remote publication.

## Slate-blue Settings controls, 10 October 2026

Branch `codex/settings-accent-palette` starts from local main `6650355`. Shared
Settings control surfaces now use flat muted slate blue `#243247`, with related
hover, pressed, selection and border colors. The palette covers fields, buttons,
lists, dropdown popups, profile menus and switch tracks, including app-owned
Settings dialogs. Existing geometry, radii, gradient and number-field fix remain.

Only necessary checks ran: **8 existing native cases passed in 17.79 seconds**
on Qt 6.12.0. They cover numeric editing/save/reopen, profile setup quota, section
geometry in both profile modes and window sizes, greeting persistence, switch
mouse/keyboard input, and embedded skill preview/install/remove. Pytest used
`--basetemp state/settings-accent-native`; XML/log evidence shares that prefix.
No new tests, full-suite repetition or live provider calls.

An isolated synthetic encrypted profile rendered all six Settings sections,
five profile tabs, dropdown/menu popups and three dialogs. Fifteen visually
inspected captures and the sampled-surface report are under ignored
`state/settings-accent-preview/`. Text/control contrast is 10.30:1; disabled
button text/control contrast is 5.82:1. The profile was released and there were
zero network connection attempts. This is a local update; the next portable
package has not been built.

Fourteen settings/runtime/artwork fingerprints and all four other worktree tips
and attachments are unchanged. Recovery evidence is under
`state/backups/settings-accent-palette-20261010/`, with prior main preserved at
`archive/2026-10-10/main-before-settings-accent-palette`. Commit, fast-forward
local main and remove only the merged feature branch; no remote publication.

## Requested darker Settings gradient, 10 October 2026

Branch `codex/settings-gradient` starts from local main `8c2796f`. The only
application change is replacing the Settings panel's two gradient stops with
the user's colors: darkest `#090c15`, brightest `#1d2637`. Its bottom-left to
top-right direction, 16-pixel radius, border, geometry and controls are unchanged.
The previous number-field correction remains included.

Only necessary checks ran: **2 existing native Settings geometry cases passed
in 5.11 seconds**, covering local/portable profiles, all sections and normal,
maximized, full-screen and minimum-size windows. Pytest used Qt 6.12.0 and
repository-local `--basetemp state/sg-native`. No new tests or full-suite repeat.

The exact portable update was extracted only into an owned synthetic pilot.
Its actual `pythonw` runtime rendered the new panel, passed sampled-pixel checks
against the requested gradient interpolation, and produced a visually inspected
preview. Existing encrypted records and archived chat remained accessible;
keys, leases, helpers, inference clients and desktop ownership were released.
No live API call: zero network connection attempts and zero remaining owned
pilot processes. Evidence is under ignored `state/settings-gradient-*`, including
the native XML/log and `settings-gradient-preview.png`.

The **6,345-byte** `dist/orsi-settings-update-20261010.zip` includes only the
updated `app/ui/settings_panel.py`, the previously corrected `app/ui/inputs.py`,
instructions and a file manifest. It works whether or not the earlier input fix
was applied. Close O.R.S.I, copy its `app` folder into the existing portable
application folder, allow replacing those two files, and restart. Profiles,
state, configuration and runtime folders are not included. Archive SHA-256:
`3a677f9daa23d841d1783b96fd58efded09d7c1b5ce0112c3d05efe5a569fdb2`.

Fourteen settings/runtime/artwork fingerprints and all four other worktree tips
and attachments are unchanged. Recovery evidence is under
`state/backups/settings-gradient-20261010/`. Preserve prior main at
`archive/2026-10-10/main-before-settings-gradient`, commit, fast-forward local
main and remove only the merged feature branch. No remote publication.

## Original Settings update, 10 October 2026

10 October 2026. Branch `codex/settings-finish`, from local main `73304f5`.

## Delivered behavior

- Removed the Other credential types explanation, provider-revocation footer
  and Local/Portable, encryption and Unlocked badges shown by the user. Credential
  type choices, explicit save consent and underlying policies are unchanged.
- Settings dropdowns and ordinary action buttons use one shared palette, borders,
  hover/focus/disabled treatment and typography. Dropdowns use the same chevron
  and 36-pixel height, including image and notification controls. App-owned
  Settings dialogs use the same controls. Navigation and icon buttons keep their
  existing roles. Save and Delete credential now use the shared neutral buttons.
- Selected saved records use a padded rounded blue highlight without the native
  white focus outline. Long paths elide in the middle and retain a full tooltip.
- Both outer Settings pages and inner profile tabs reveal over 200 ms with eased
  opacity. Selection/actions remain immediate, the latest navigation wins, and
  the outer panel keeps its normal size/position. Snapshot covers are discarded
  after completion, hiding, resizing and profile lock; unsaved edits retain their
  existing behavior.
- Preserved the user's already-modified `orsi_start.png` byte-for-byte and bundled
  the exact desktop `bsw_o.png`. The logo is centered, preserving its proportions,
  with a 3.2-second breathing cycle: 94–100% scale and 70–100% opacity. The whole
  cover retains its topmost, nonactivating presentation and 240/560 ms fades.

Profile composition blocks the main UI thread, so a main-thread animation would
freeze during the actual load. A public-artwork helper has its own Qt loop for
continuous motion. Its entrypoint runs before runtime-directory initialization,
desktop ownership and private service composition. Only geometry is passed in
arguments; the private pipes exchange readiness and fade/EOF commands. It receives
no password, key, profile location, file contents or personal UI snapshot.
The replacement is raised and painted before the helper fades out and exits.
Closing its parent pipe exits it, even before first paint; failed startup falls
back to the existing in-process cover instead of blocking profile access.

The package-data rules include public PNG/SVG/font assets and the font license.
The existing portable build includes the entire asset directory. No Desktop asset
path is used at runtime. The source portable runtime is verified; a compiled
Nuitka distribution was not rebuilt for this change.

## Focused verification

**29 distinct native Windows pytest cases passed**, with no failures, errors or
skips in the final reports. The full 2000+ suite was not run.

- `state/settings-finish-smoke.xml`: ten cases for transition interruption,
  hide/resize cleanup, continuously animated helper, EOF/fallback, normal/maximized/
  full-screen/minimum-size Settings geometry, dragging and profile save/lock.
- `state/settings-finish-focused.xml`: 17 additional existing cases for desktop
  ownership and entrypoint isolation, application shutdown, greeting/image
  settings, vector control feedback and local/portable unlock/stale-view guards.
- `state/settings-finish-launcher.xml`: six final presentation cases, overlapping
  four smoke cases and adding early-before-paint EOF plus the windowless runtime
  used by `orsi.cmd`. The test captures the helper's native window twice while
  deliberately blocking the parent thread and verifies different rendered frames,
  the actual Windows topmost flag, one visible helper window and clean exit.

The native visual probe passed for local and portable synthetic profiles, checking
all five profile sections at 1536 × 1024, 1280 × 800 and 760 × 600 without horizontal
clipping, compact actions, consistent dropdown heights, wheel-safe values, menu
contents, explicit credential save and lock/unlock clearing. It also captured all
five ordinary Settings pages, credential menus, selected records and the centered
logo. Captures of Cloud access, Data selection, General, Models, Skills, Image
Generation, a credential popup, minimum-size Cloud access and the loading cover
were visually inspected. Evidence is ignored under
`state/settings-finish-native/2d41669818fd4d578e3147f79faedc88/`.

Python syntax, package-data inclusion and Git whitespace checks passed. All nine
pre-change configuration/artwork fingerprint or absence entries match, as does
the exact copied logo. Other worktree tips are unchanged. Recovery refs/worktree
maps, content-free checks and a copy of the user's modified background are under
`state/backups/settings-finish-20261010/`. Prior main is retained at
`archive/2026-10-10/main-before-settings-finish`.

No live provider/model call, actual user-vault access or running-user-process
termination was needed. Physical SSD, minimum-machine performance and independent
security qualification remain separate deferred gates.

## Smaller splash and faster tabs, 10 October 2026

Branch `codex/splash-motion-tuning`, from main `e1e7da0`: the splash logo is capped
at 64 pixels wide instead of 280. The centered layout and slow breathing cycle
remain. Both outer Settings and inner profile transitions now take 100 ms rather
than 200 ms. Existing intermediate-frame test waits were shortened accordingly.

Three existing focused native checks passed in `state/splash-motion-focused.xml`:
tab interruption/hide/resize cleanup and continuous splash animation/exit using
both console and windowless launcher runtimes. No full suite or live gates.
A native 1280 × 800 capture was visually inspected; its peak logo measured
64 × 56 pixels, centered within two pixels. Preview is ignored at
`state/splash-motion-preview.png`. Syntax and whitespace checks passed. All ten
settings/artwork fingerprints and other worktree tips are unchanged. Recovery
evidence is under `state/backups/splash-motion-tuning-20261010/`; prior main is
retained at `archive/2026-10-10/main-before-splash-motion-tuning`.

## Quicker Settings navigation, 10 October 2026

Branch `codex/settings-navigation-speed`, from main `b62882a`: both Settings
sections and Personal profile tabs now reveal in 50 ms with OutCubic easing.
The new page is mostly visible within 20 ms, removing the previous slow start.
The existing transition check verifies that early reveal and completion while
retaining immediate navigation, interruption and hide/resize cleanup.

Six focused native Windows cases passed: two navigation/presentation checks in
`state/settings-navigation-speed.xml`, plus four local/portable profile geometry
and edit/save/lock checks in `state/settings-navigation-profile.xml`. The first
run had a pytest cache-write warning; both tests passed, and the second run used
an isolated repository-local cache. No full suite or live provider/model gates
were run. Ten configuration/artwork fingerprints and other worktree tips were
preserved under ignored `state/backups/settings-navigation-speed-20261010/`.
