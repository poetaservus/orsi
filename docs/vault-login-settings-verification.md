# Vault login and settings controls

9 October 2026. Bounded change from local main `f7eb507` on
`codex/vault-login-settings`.

All application dropdown constructors now use a shared wheel-safe combo box.
Ignored wheel events leave selection unchanged and allow the surrounding page
to scroll. Keyboard navigation and opened-menu selection remain available.
The unused credential-file import button is removed; existing migration helpers
are retained. Vault quota and idle minutes share the same 72 × 36 typed number
control with no spinner arrows or wheel changes. Quota's GiB label sits outside
the field, beside a 128 × 36 Change quota button. Saving refreshes usage figures.

Locked startup uses a dedicated login frame rather than the Settings panel.
Its rounded gradient, typography and fields match the existing app. Password
and recovery entry, new/existing profile selection, legacy-storage selection and
encrypted backup restore remain accessible. Failed authentication stays at login
without private consumers. Successful login opens chat; Settings remains closed.
Locking returns to login. The bundled topmost loading picture and fades remain
in the existing transition, with retired-window guards preserved.

## Focused verification

`state/login-controls-final.xml`: **26 passed**, zero failures/errors/skips, on
Qt's native Windows platform with repository-local temporary/cache directories.
Existing startup coverage now asserts the separate login, failed-password retry,
Settings exclusion, successful keyboard unlock and return to login after lock.
Other selected checks cover local/portable recovery, backup/restore/relocation,
profile setup/selection, saved-key startup, obsolete unlock/activation rejection,
single consumer ownership, settings navigation/model mode/image/sound controls
and application shutdown. The full 2000+ suite was not run.

Isolated native checks used synthetic local and portable encrypted profiles.
Each checked all 17 app dropdowns plus quota/minutes under focused/unfocused
wheel input; setup selectors/quota were also checked (155 wheel cases per mode).
Window-level wheel dispatch verified actual page scrolling over a dropdown.
Keyboard selection and opened-menu scrolling still worked. Typed quota save
refreshed usage and survived lock/unlock. Password errors cleared entry, recovery
unlock worked, and the dedicated panel and restore controls remained reachable
at the 760 × 600 minimum window size. Normal/error/minimum-size login and quota
captures were visually inspected. Final evidence:
`state/vault-login-settings-native/ed04ed9d29fb49268cd31dffb0511352/`.

An actual desktop-entrypoint probe passed with one visible main window, one
private composition and two repeated launches. Its actual Responses backend
accepted a synthetic saved key without prompting; no network/model call occurred.
Evidence: `state/vault-login-settings-entry.json`.

Changed Python parses and whitespace checks pass. All eight pre-change user
configuration/selection hashes or absence match; other worktrees are untouched.
Recovery fingerprints and refs are under ignored
`state/backups/vault-login-settings-20261009/`. No real user vault was opened and
no user process was stopped. Physical media/minimum-host performance, live
provider/model and independent security qualification remain deferred.
