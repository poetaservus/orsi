# Compact idle-lock controls

9 October 2026. Bounded change from local main `8a6b7b2` on
`codex/vault-idle-controls`.

The previous full-width spin field and separate full-width button become one
compact row. The existing tool-approval `NotificationSwitch` enables/disables
a centered 72 × 36 typed minutes field. Spinner buttons are hidden and its
wheel handler ignores changes whether focused or unfocused. The 128 × 36
Save idle lock button applies the switch and value together. Existing positive
intervals populate unchanged; off remains stored as zero. The unsaved field
starts at five minutes for an off profile. Enabled input stays bounded to
1–1440 minutes. No new settings schema or idle-detection policy.

## Focused verification

`state/vault-idle-controls-final.xml`: **7 passed in 8.26 s**, zero
failures/errors/skips, using Qt's actual Windows platform. Existing cases cover
local/portable idle locking and guidance persistence, locked startup and keyboard
unlock, profile restart/minimal bootstrap and the shared tool-approval switch.
The first run's local bootstrap assertion matched the word `idle` in its
temporary directory path. A neutral repository-local `state/profile-controls-final`
base directory resolved that fixture-path interaction without changing tests.
The full 2000+ suite was not run; no new permanent tests were added for the layout.

An isolated native probe checked both local and portable synthetic encrypted
profiles: disabled defaults, keyboard typing, explicit save, eight wheel cases
per mode (both directions, larger deltas, focused/unfocused), positive-value
persistence after lock/unlock, saved disable, no idle locking after disable and
off persistence after another unlock. Both layouts fit at the 760 × 600 minimum
window size. Normal/off/on and minimum-width captures against the real Settings
panel background were visually inspected. Evidence:
`state/vault-idle-controls-native/87a90508e87045d2bcffefa81a3f8f77/`.

Changed Python parses and `git diff --check` pass. All eight pre-change user
configuration/selection hashes or absence match. Content-free preservation
evidence is under `state/backups/vault-idle-controls-20261009/`. No actual vault
was opened, credential read or user process stopped. Restart the running app
to load the UI change. Physical media/minimum-host performance, live provider/model
and independent security qualification remain deferred.
