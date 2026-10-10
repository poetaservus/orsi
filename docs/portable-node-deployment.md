# Deploy portable nodes from Settings

Open **Settings > Personal profile > Storage > Deploy portable node…**. This
feature is available in the local app and in newly deployed nodes. It does not
need Git, a developer installation or a download during deployment.

Choose **Include my current profile** to copy the open profile, or **Fresh node**
to start with profile creation and no instance data. Current-profile deployment
includes all stored personal and credential records: skills and their imported
references, imported files, images, conversations, settings, preferences,
retention policies and managed backups. Files outside the profile remain outside
the copy. Encrypted profiles retain their password, recovery key and saved
connections. Session-only credentials stay in memory on the source computer;
plain profiles remain unencrypted.

**Include installed local models** is optional and off by default. Leaving it
off produces a cloud-only node. Turning it on copies installed GGUF models and
projectors, the local server, its runtime dependencies and license files. The
application's versioned model configuration is copied without changing its
sampling, routing, context limits or model selection policy.

Choose a drive or parent folder; the dialog proposes a new `ORSI-node` folder.
Edit that path to give another node a different name. Deployment checks free
space, copies in the background, verifies the files and publishes the finished
folder. Existing destinations are preserved. Progress and cancellation are
available, including safe cancellation when the profile locks or the app quits.
Run **ORSI.cmd** in the new folder. Close the node before moving its complete
folder to another drive or computer.

The source profile stays selected and active. This is an independent snapshot,
with no synchronization of later edits. The source records the exported profile
in its copy registry, so normal profile-copy/deletion management can account for
it. The new node contains only a relative locator and registry entry for its
own profile; it does not inherit the source computer's paths or copy inventory.

## Implementation boundary

`app/portable/deployment.py` assembles public application code/assets,
allowlisted launch/configuration files and a portable embedded Python runtime.
It omits root instance state, Git metadata, `.env`, tests, runtime caches and
absolute-path script launchers. Cloud-only export omits local inference and
NVIDIA packages. Its runtime READY marker and START_HERE guide describe the
selected variant. `NODE_MANIFEST.json` records payload sizes and SHA-256 values;
verification applies before first launch changes profile/runtime state.

Encrypted export holds the engine's snapshot lock, acquires the managed-backup
leases, copies ciphertext and verifies the current authenticated catalog and
both record domains. It preserves the backup catalog and required empty
directories, including backups made before a password change. Verification and
copying honor cancellation between chunks. Output errors do not revoke the
source session. Plain-profile copying preserves its files and checks for source
changes; only the root process-lease file is omitted.

Outputs must be new independent directories outside the installation and known
profiles, including paths spelled with `..`. A unique sibling staging directory
is removed on failure or cancellation. Successful publication changes neither
the source profile selection nor its data. If recording an otherwise verified
export in the source copy registry fails, the dialog reports the ready node and
the copy-tracking limitation separately.

## Focused verification, 10 October 2026

Branch `codex/deploy-portable-nodes` starts from local main `1627bfb`. Only
necessary checks ran, as requested: **41 distinct focused cases passed** on
native Qt 6.12.0. These cover complete encrypted and plain copies, managed
backups with older passwords, relocation, fresh variants, optional local
resources/licenses, source preservation, invalid and aliased destinations,
missing application/runtime files, insufficient space, cancellation during
copy/authentication/verification, competing destinations, busy backups,
copy-registry failure, real dialog controls, pending preference saves, locking
and unprofiled shutdown. Existing encryption, backup/recovery, onboarding and
Settings geometry checks also passed. All pytest runs used repository-local
`--basetemp`; final distinct results are in `state/deploy-node-final-results.xml`.

Early checks found a test using the wrong read API and an omitted empty
`backups` directory inside exported managed snapshots. Both were corrected and
the affected paths rechecked. The native observation helper also needed its
exercise scheduled after the launch cover closed and its history check changed
to read the actual encrypted conversation archives. Raw runs, including these
diagnostics, remain under ignored `state/deploy-node-*`.

A real cloud-only node was assembled from owned application/runtime inputs,
with **9,085 files** and about **947 MiB** of uncompressed payload verified at
deployment. Its whole folder was moved to a path with spaces, then its actual
`pythonw` desktop entry opened locked and unlocked the copied profile. The
native check verified imported skill discovery, a stored file, greeting
preferences, archived conversation history, managed backup retention, saved
credential-policy/API-key/token access and exclusion of a memory-only
connection. The source profile remained independently open and its selection
and record contents stayed intact. The final dialog/shutdown hook and optional
license filter were applied to the owned check node for the concluding launch.
`pip check` passed. Both loading helpers exited, provider clients closed, keys
were zeroed, leases released and desktop ownership was reusable. Network
attempts: **zero**. No live inference/provider calls, full-suite run, real local
model deployment or physical USB/second-PC qualification were performed.

The content-free native result is `state/deploy-node-native-result.json`.
Visually inspected login/dialog captures are in the owned fixture named there.
The reusable native observer is `tests/deployed_node_probe.py`; it is not shipped
in a node. The developer's real profile was not exported by these checks.

All sixteen original settings/runtime/artwork/locator/registry fingerprints and
the four other worktree attachments are unchanged. Recovery evidence is under
`state/backups/deploy-portable-nodes-20261010/`, with prior main preserved at
`archive/2026-10-10/main-before-deploy-portable-nodes`. Commit, fast-forward local
main and remove only the merged feature branch. No remote publication.
