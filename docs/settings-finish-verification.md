# Settings consistency, transitions and loading logo

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
