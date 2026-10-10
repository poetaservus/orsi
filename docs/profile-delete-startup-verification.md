# Profile deletion and no-profile loading splash

Bounded follow-up from main `c8be6fc`, on `codex/profile-delete-startup`.

Manage profile now includes Delete profile. Its confirmation lists the selected
profile and recorded copies, accepts older unlisted backups through a folder
browser, and enables permanent deletion only after entering DELETE. Both personal
and credential records, complete profile directories and their managed backups
are removed, together with all recorded external backups/restored/relocated copies
of the same identity. Other profiles and imported source files remain separate.
Files exported elsewhere and unknown manual copies are outside this operation.

A locator-only registry in application state records subsequent profile selection,
creation, backup, restore and relocation. Existing in-memory known locations also
participate. Old external copies that were never recorded must be included in the
review. Portable locators inside the application use relative paths. No credentials,
keys, conversation bodies or document contents are placed in the registry/journal.

Deletion drains and clears profile resources and revokes streams/keys before any
file is removed. All locations are verified before starting, then acquired with
exclusive leases. Copies are moved into uniquely named sibling staging folders;
their leases remain held during content removal. A pending journal and folder
markers allow retries after locked files, unavailable drives, shutdown failures
or restart, including a copy opened elsewhere between attempts. Failed completion
retains its pending state and the retry screen rather than reporting success or
forgetting remaining copies. Successful deletion returns to profile choices.

The previous splash condition only admitted a locked-to-unlocked profile transition.
It now also admits a locked/open profile becoming no-profile mode, presenting before
the unprofiled builder and dismissing over the replacement window. Retired signals
cannot restart composition. The splash artwork, size, pulse and fades are unchanged.

## Focused verification

**40 native Windows cases passed**, without failures, errors or skips, in
`state/profile-delete-startup-final.xml` (33.34 seconds). This is a focused group;
the full 2000+ suite was not run.

Coverage includes local/portable encrypted and unencrypted deletion, all recorded
copies across restart, encrypted credentials and managed backups, key zeroing and
stream revocation, unrelated-profile preservation, explicit consent, application
scope refusal, directory junction rejection, malformed registry preservation,
busy/unavailable/replaced copies, partial removal, failed drain, staged-copy lease
conflicts, cancellation, adding an old backup, retry/completed UI, stale signals,
existing backup/restore/relocation, unlock ownership and no-profile splash wiring.
The real splash helper was separately exercised within the same group under console
and windowless Python, verifying continuous animation while its parent blocks,
topmost state and exit. No live provider or model process was needed.

Synthetic delete-confirmation, retry-at-minimum-size and completed-choice captures
were visually inspected under ignored
`state/profile-delete-preview/437730440e594528999439baac75517d/`.
Syntax and whitespace checks passed. Twelve configuration/artwork absence or hash
entries and other worktree tips are preserved under ignored
`state/backups/profile-delete-startup-20261010/`. Prior main is retained at
`archive/2026-10-10/main-before-profile-delete-startup`.

No actual user profile was deleted, unlocked or migrated, and no running user
instance was terminated. Physical SSD durability, minimum-machine performance
and independent security qualification remain deferred.
