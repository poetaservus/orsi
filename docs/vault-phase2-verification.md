# Personal Vault phase 2: verification record

9 October 2026. Started on `codex/vault-phase2` from local main `abcd943` after
fast-forwarding the verified phase 1 commit. The phase 1 tip is preserved at
`archive/2026-10-09/vault-phase1`; prior main is preserved at
`archive/2026-10-09/main-before-vault-phase1`. No remote refs or other worktrees
were changed. See [the engine contract](vault-phase2-contract.md).

The user authorized the next phase, explicitly deferred real SSD, minimum-machine
and independent security qualification, and requested only necessary tests.
These instructions supersede the usual full-suite requirement and the previous
phase 1 review-branch deferral. The verified phase 2 change is committed and
integrated locally under the repository workflow; no remote publication is authorized.

## Delivered

- Password unlock/lock, header-only password rewrap and explicit optional recovery
  key generation, rotation, disable and recovery unlock. Separate key domains.
- Encrypted private/credential catalogs and immutable authenticated large-object
  streams, with one atomic catalog commit for record/asset/preview/index batches.
- Actual encrypted usage accounting, adjustable quota, transient staging bounds,
  physical free-space reserve and fixed no-fallback failure behavior.
- Verified managed/independent ciphertext backups and password/recovery restoration
  into a new location, preserving originals. Managed count/age retention controls.
- OS process lease, Windows ancestor pins/snapshot handles, stale-lock recovery,
  safe unsupported-location selection and rejection of linked lease files.
- Shared-asset ownership, explicit deletion, default 24-hour temporary records,
  expiration, orphan reclamation and deletion visibility preceding physical cleanup.

Engine, codec, owned-file layer and data types are under `app/vault/`. Optional
`.[vault]` installs the already selected `PyNaCl==1.6.2`; the existing disposable
prototype extra remains supported. This checkout reuses the ignored phase 1 test
dependency folder. Base runtime dependencies/configuration and normal startup do
not import cryptography or enable encrypted user storage.

## Focused checks and refinements

The first engine run recorded **48 passed and two failed** in **14.18 seconds**.
Both failed marker-scan fixtures tried to read the OS-exclusive lease byte while
the vault was open. The fixtures now close the vault and scan all persisted files,
including the lease, then reopen for the separate credential-envelope assertion.
No product behavior or existing acceptance assertion was relaxed to pass this check.

The next engine/shared-writer run passed **55 cases in 15.66 seconds**. Self-review
then added checks/refinements for:

- Equal-second backup ordering, ensuring the newest verified snapshot is retained.
- Released relocation handles and the unavailable state for a missing root.
- Default temporary retention, failed snapshot preservation and corrupted restore.
- Header validation before lease-file creation in an unsupported directory, and
  rejecting a hardlinked lease before its first byte can affect an external file.
- Normalizing bounded Windows snapshot errors into the engine's recovery state.

Four targeted edge cases passed in 0.66 seconds. The expanded combined checks
passed **65 cases in 16.22 seconds**, then **69 cases in 18.22 seconds** before the
final oversized-header normalization. The final focused run passed **71 cases**
with **zero failures, errors or skips in 18.56 seconds**: 66 engine cases across
both simulated storage modes plus five existing atomic-state writer cases.

All tests use synthetic bytes only and run both local and portable directory
simulations. The focused set contains engine acceptance plus the existing five
atomic-state writer cases; no large general regression run was invoked.

Content-free reports and repository-local temporary/cache folders:

```text
state/vault-phase2-initial.xml
state/vault-phase2-focused.xml
state/vault-phase2-edge.xml
state/vault-phase2-final.xml
state/vault-phase2-qualified.xml
state/vault-phase2-release.xml
state/vault-phase2-tests-*/
state/vault-phase2-cache-*/
```

Verification covers wrong/changed passwords, optional recovery and rotation,
large synthetic PNGs over 12 MiB, limited public fields, separate credential
envelopes, marker exclusion, object/catalog/header corruption, truncated or
missing-final streams, appended bytes and excessive frame/header/KDF bounds.
It also covers shared source/preview/extraction/index deletion, expiration before
cleanup, interrupted physical deletion, real process death immediately before
and after catalog publication, post-publication error ambiguity, quota rejection,
full-disk/read-only failure injection and actual concurrent child-process opens.
Backups cover managed count/age/timestamp ties, independent old credentials,
failed-new-copy preservation, existing-destination preservation, corrupted-copy
rejection and relocation/restore through both unlock methods.

The native tests use Windows OS locks/handles and child processes. Their isolated
subprocesses receive synthetic password bytes through stdin, not command-line
arguments, and exit or are synchronously reaped. No model/server/API process is
started. Engine tests inspect emitted logging and known owned persistence for
synthetic markers without reading or copying actual user conversations/keys.

## Reproduction and remaining qualification

For a normal development interpreter:

```powershell
python -m pip install -e ".[vault,test]"
python -m pytest tests/test_vault_engine.py tests/test_atomic_state.py --basetemp=state/vault-phase2-checks -o cache_dir=state/vault-phase2-cache
```

The bundled interpreter needs the existing isolated dependency directory inserted
into `sys.path`, followed by `runpy.run_module('pytest', run_name='__main__')`.
The Windows sandbox cannot read the native-installed dependency subdirectories,
so focused checks ran in the native shell. Source compilation, whitespace,
normal-startup import isolation and seven configuration/preference preservation
hashes all passed separately. Ref/worktree maps and content-free preservation
hashes are under `state/backups/vault-phase2-20261009/`.

The full existing suite, live models/APIs, real removable SSD, second Windows
host/account, minimum-host cost tuning, independent security review and OS
forensic/power-loss qualification are **not run or claimed**. Disk-full/read-only
cases are deterministic injection; ordinary local Windows persistence/relocation,
real child-process death and cross-process locking are actually exercised.
The engine's Windows scope and memory/durability limits are explicit in its contract.

Phase 3 still needs to connect personal-data consumers and the credential provider,
then enforce job/profile boundaries and model/tool exclusions. Setup/migration/UI
remain phase 4. This phase does not encrypt the user's existing application data
or change their credential policy, accepted models, prompts, routing or tool behavior.
