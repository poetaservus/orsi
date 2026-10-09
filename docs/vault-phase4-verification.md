# Personal Vault phase 4: verification record

9 October 2026. Started from verified local `main` `30053f6` on
`codex/vault-phase4`. The user authorized all of phase 4, including 4.1, and
requested necessary tests only. This overrides the usual full-suite requirement.
The 2000+ suite was not run. Real SSD, minimum-machine and independent security
qualification remain deferred. See [the implementation contract](vault-phase4-contract.md).

## Delivered scope

Settings now provides local/portable profile creation and selection, encrypted
or unencrypted personal storage, locked startup, usage/quota/free-space figures,
manual/optional idle lock, password/recovery controls, encrypted backup/restore,
verified relocation, separate credential policies/consent, opt-in migration and
original cleanup, saved records, retention/deletion and dismissible storage
guidance. Imported preferences reload through actual application composition.
Supported existing personality/templates/memory files are protected/importable;
this does not introduce new personality editors, memory engines or media features.

Unconfigured startup remains quiet. Desktop plaintext connections use session-only
credentials with no environment-key fallback. No actual user profile was created,
selected or migrated as part of implementation. Prompts, routing, accepted model
profiles, sampling, context policy and acceptance prompts remain unchanged.

## Focused evidence

All test profiles, documents, conversations, images and credentials are synthetic.
No real model/provider calls were made. All temporary paths/caches use repository-local
`state/vault-phase4-tests-*` and `state/vault-phase4-cache-*` directories.

| Report under ignored `state/` | Result | Focus |
| --- | --- | --- |
| `vault-phase4-release.xml` | 59 passed, 44.94 s | 54 new control/application cases and five existing shutdown cases |
| `vault-phase4-regression.xml` | 199 passed, 99.96 s | Existing engine, application, UI, inference and selected startup regressions |
| `vault-phase4-cleanup-final.xml` | 17 passed, 10.59 s | New destination-picker/interrupted-cleanup checks and affected migration cases |
| `vault-phase4-native-cleanup-release.xml` | 16 passed, 9.65 s | Native verified deletion, credential cleanup and restore/relocation recheck |
| `vault-phase4-last-safeguards.xml` | 6 passed, 1.52 s | Changed/shared originals, write/delete locking, interrupted receipts and overlapping restore destinations |

Across these reports **267 distinct checks passed**, with no final failures,
errors or skips. Repeated cases/refinement runs are counted once. The focused
regression was explicitly limited to `test_vault_engine`, `test_vault_application`,
`test_settings_panel`, `test_skill_settings_ui`, `test_attachment_composer`,
`test_image_viewer`, `test_inference_lifecycle`, three relevant skill-registry
startup cases, one model-selection restore case and four application bootstrap
cases. No repository-wide test invocation was used.

The new coverage exercises local/portable setup, minimal public bootstrap,
restart/wrong-password/recovery, portable application-tree relocation, quota and
actual disk-free reporting, source-preserving backup/restore/relocation, failed
copy/drain retry, session renewal and old-handle revocation. Plaintext profile
composition and actual startup retain isolated state and session-only credentials.

Migration checks cover all supported categories, shared attachment relationships,
prepared text/previews, archived active history, encrypted receipts, selected
conflicts, changed originals, interrupted publication and separately consented
cleanup. All four supported credential fields use the credential domain; cleanup
removes only the chosen JSON field. Windows cleanup holds the verified original
open against writes/renames through deletion, refuses hardlinks and changed bytes,
and preserves the vault copy if receipt update is interrupted. Restore rejects
backup/destination overlap before changing the active profile or creating folders.

Qt checks exercise locked startup, keyboard unlock, disabled private composer,
idle lock, guidance dismissal, recovery export/password changes, restore/relocation
through controls, import/reload of greeting preferences, encrypted image keep/export
and durable draft promotion, current-draft preservation, switching and quiet normal
startup. Existing shutdown tests now use an actual Qt application with the new
owner and retain checks that failures still release inference resources.

Initial runs exposed plaintext-root lease assumptions and an enabled locked
composer; both were fixed. Fixture errors were corrected without changing
acceptance prompts. Restricted-shell crypto reads/Windows ownership handles also
failed during verification. Native-shell reruns passed; those environment errors
are recorded separately and are not product failures or passed checks.

The compact setup, unlocked profile, retention and locked profile screens were
rendered offscreen and visually inspected. A low-contrast control style was fixed.
The final layouts fit the checked 560×400 setup and 760×600 application windows,
with vertical scrolling and visible keyboard focus. This is not physical-host or
complete accessibility qualification. Screens are under ignored
`state/vault-phase4-visuals/` and contain synthetic data only.

Changed Python modules compile, `git diff --check` passes, and the bundled
runtime's dependency check reports no broken requirements. Normal `app.main`
import leaves `nacl` unloaded. The Windows dependency extra now pins PyNaCl 1.6.2;
this checkout's bundled runtime received the existing available PyNaCl 1.6.2,
cffi 2.1.1 and pycparser 3.11 after validating 84 RECORD hashes/sizes. Installation
refused existing target files, copied no network downloads and replaced no
existing package/runtime settings.

## Preservation and deferred qualification

Pre-change refs/worktree maps and content-free hashes are preserved under ignored
`state/backups/vault-phase4-20261009/`. All seven recorded configuration/state
paths match their initial hashes/absence after verification. No real credentials,
conversation contents or file bodies were recorded in preservation evidence.
Other worktree tips remain unchanged. The prior integration tip is preserved at
`archive/2026-10-09/main-before-vault-phase4`; the bounded feature is committed,
fast-forwarded into local main and its merged feature branch removed. No remote
publication is authorized or performed.

Still deferred: physical SSD removal/reconnection and cross-host/account/drive
qualification, minimum-host RAM/performance (large selected migration batches can
use substantial memory), real model/provider/login sessions, hardware power loss,
forensic erasure/host compromise and independent format/key/path/recovery security
review. Close source applications/editors before migration/credential cleanup;
multi-file cleanup can be partial after interruption, and missing originals are
filtered from retained-original review. Independent backups/exports/source copies
remain unless explicitly removed. Phase 5 has not started; phase 4's deterministic
checks do not establish a security-qualified release.
