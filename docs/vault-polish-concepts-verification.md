# Vault controls, login blur, image reveal and layout concepts

9 October 2026. Bounded change from local main `dc2eb8d` on
`codex/vault-polish-concepts`.

Managed backup count and age now share quota's wheel-safe 72 × 36 typed control.
Aligned rows replace the two full-width spin boxes; a 128 × 36 Apply retention
button sits alongside them. The existing confirmation, count/age ranges and
zero-value meanings remain. Applying interprets both typed values before storing.

The locked login blurs only the underlying application root with a 12-pixel
quality blur. The login panel is a sibling of that root, leaving text and inputs
sharp. The unlocked replacement is a new unblurred view.

The loading picture retains its bundled portable asset, geometry, topmost style
and 240 ms fade-in. Fade-out now lasts 560 ms. The replacement is raised,
activated and painted before that fade, so chat is visible underneath. Event
processing continues to exclude queued user input and socket notifications;
transition/reentrancy guards and delayed retired-window collection remain.

## Necessary verification

`state/profile-polish-pytest.xml`: **21 passed in 29.72 s**, zero failures/errors/
skips, using native Windows Qt and repository-local temporary/cache directories.
Selected existing checks cover locked/failed/keyboard startup, idle lock,
password/recovery/backup/restore/relocation, saved-key startup, stale activation/
unlock, failed transitions/drains and application shutdown. No full suite.

Synthetic local and portable native controls checks passed: 16 focused/unfocused
wheel cases per profile, exact field/button sizes, minimum-window layout, page
scrolling over a numeric input, cancelled Apply preserving policy, typed Apply,
policy persistence after unlock, blurred login and crisp unlocked root. Captures
were visually inspected. Evidence:
`state/vault-polish-controls-native/32c3dd3f00e04a54ba4434725973a68c/`.

Native fade checks passed for normal, maximized and failed composition, including
a relocated portable asset. Actual window opacity had intermediate native alpha
values, remained monotonic and reached zero before closing. Final observed
fade-out durations were 562–578 ms, with 25–37 timer samples. The cover stayed
above an owned second test process, preserved geometry, rejected obsolete unlock
callbacks and left one main window. Mid-transition capture showed chat beneath
the partially transparent cover. Final evidence:
`state/vault-polish-fade-native/1cf70ed5d90a4cae99ebe3bf6953720f/`.

## Design deliverables

After the three fixes were verified, primary Microsoft/Fluent settings, layout
and button guidance informed two imagegen mockups: a grouped overview and focused
tabs. Both were visually inspected and saved with exact prompts and an existing-
function map under [design/personal-profile](design/personal-profile/README.md).
The synthetic current-UI capture supplied style only. The full tab redesign is
a proposal, with no new provider calls, backup scheduling or persistence policy.

Changed Python parses and whitespace checks pass. All eight user configuration/
selection fingerprints or absence match; other worktree tips are unchanged.
Content-free preservation evidence is under ignored
`state/backups/vault-polish-concepts-20261009/`. No actual user vault/credential was
opened, no user process stopped, and no remote branch published. Physical media,
minimum-host performance, live provider/model and independent security gates
remain deferred.
