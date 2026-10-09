# Personal Vault phase 1: format and lifecycle contract

9 October 2026. Design candidate for Windows local and portable encrypted
profiles. Phase 1 adds an isolated synthetic experiment, not production vault
support. See [storage map](vault-phase1-storage-map.md) for all categories and
[verification](vault-phase1-verification.md) for evidence and unresolved gates.

## Profile identity, location and relocation

Generate a canonical random UUIDv4 once at profile creation. This identifier is
authenticated in the header and every object context and survives relocation,
password changes and restoration. User-facing profile names are encrypted.
Never derive a key or the profile ID from a drive letter, absolute path,
Windows username/SID, machine name or DPAPI identity.

Default local root: `%LOCALAPPDATA%/ORSI/profiles/<profile-id>/vault/`.
Default portable root on the explicitly selected volume:
`<selected-volume>/orsi-profiles/<profile-id>/vault/`. The application, runtime,
models and public defaults stay outside both. A portable application can locate
its adjacent `orsi-profiles/locator_v1.json` relative to its launch root, or the
user can select the volume/profile. Do not scan arbitrary disks or infer a host
project. Selecting a directory is not authorization to migrate its contents.

Public locators are hints, not authority. Check the actual authenticated header
UUID after unlock. Reject mismatches instead of adopting another profile. A
drive-letter change requires resolving the relative locator or explicitly
choosing the moved profile, never a password/key change. On reinstall, the user
selects the existing local/portable root or a verified backup. No account-bound
decryption is required. Moving/restoring is explicit: close the profile, copy
ciphertext, unlock/verify records/assets at the destination, then update the
locator. Preserve the source until the user explicitly disposes of it. There is
no automatic merge or synchronization. Two restored copies share identity but
must not be opened together by one application; divergence requires an explicit
choice of source, not last-writer-wins merging.

## Public bootstrap allowlist

Local bootstrap: `%LOCALAPPDATA%/ORSI/bootstrap_v1.json`. Portable bootstrap:
`<launch-root>/orsi-profiles/locator_v1.json`. Both are bounded versioned records
with only `bootstrap_version`, `selected_profile_id`, `storage_mode`,
`locator_kind` and `locator`. For a portable vault adjacent to the launcher,
`locator` is relative to its known root. A separately selected location can use
an absolute location hint on that host; the hint necessarily exposes the vault
directory, potentially including the account folder. It must never contain
recent projects, document paths, custom profile labels, credentials or content.
Do not persist additional volume fingerprints or account identities. This
limited location disclosure is the explicit bootstrap exception.

No full setup preferences, cloud/provider choice, personality, skill list,
history, titles, tags, image names/previews or personal indexes may be read before
unlock. Locked controls use shipped public labels and the location hint only.
The public header itself contains the format/version, UUID, algorithm identifier,
KDF salt/costs and encrypted wrapped key bundle. The salt/nonce are not secrets.
Do not put a plaintext password verifier or unwrapped key in bootstrap/header.

No content-bearing public recovery journal is allowed. The proposed format uses
opaque transaction names and encrypted manifests. After a crash, unlock before
examining recovery state; merely detecting encrypted staging can show a generic
recovery message. If phase 2 proves it needs any additional public recovery
field, it must revise this explicit allowlist before shipping it.

## Format candidate and executable experiment

Choose PyNaCl 1.6.2 with its bundled libsodium. Use Argon2id version 1.3 for
password derivation, XChaCha20-Poly1305 AEAD for wrapping the key bundle, and
libsodium secretstream XChaCha20-Poly1305 for chunked objects. These are maintained
library constructions; no cipher or streaming nonce scheme is invented here.
See [PyNaCl release/dependency information](https://pypi.org/project/PyNaCl/),
[password derivation](https://pynacl.readthedocs.io/en/latest/password_hashing/),
[AEAD](https://pynacl.readthedocs.io/en/latest/secret/) and
[secretstream](https://libsodium.gitbook.io/doc/secret-key_cryptography/secretstream).

The executable prototype deliberately uses format `orsi-vault-prototype`, version
`1`. It cannot be mistaken for an enabled release format. Its layout is:

```text
<root>/header.json
<root>/objects/<random-128-bit-id>.bin
<root>/objects/<same-id>.pending     # encrypted, only during an object write
```

`header.json` has exactly `format`, `version`, `profile_id`, `cipher`, `kdf`,
`wrapped_keys`. `kdf` has exactly `name`, `operations`, `memory_bytes`, `salt`.
Canonical sorted compact ASCII JSON of all fields except `wrapped_keys` is the
AEAD associated data. Salt is 16 random bytes. The wrapped value contains its
random 24-byte nonce, the 64-byte secret bundle and authentication tag, encoded
as base64. The bundle consists of independent random 32-byte personal-data and
credential keys. Keeping both in one wrapped bundle gives one unlock password
and distinct encryption domains. The v1 design uses this random master-key bundle
as its key topology; rewrapping changes the password wrapper without rewriting
objects. The proposed release identifier is `orsi-personal-vault`, version `1`,
with the same header/key/object encoding plus an encrypted catalog and transaction
manifests. Independent review can require a new version before release. Never
silently reinterpret a versioned header or accept the disposable prototype
identifier as a release vault. Rewrapping/password recovery implementation belongs
to phase 2.

The initial measured KDF candidate is two operations with 64 MiB. The prototype
accepts only integer operations 2–6 and memory 64–256 MiB, checked before invoking
the KDF. No weakened fast-test KDF is used. The final release cost requires
minimum-supported-host measurement, including a stronger 256 MiB candidate and
an explicit responsiveness budget; a fast development-host result is not that
qualification. Password bytes are supplied directly, never through argv, a log,
environment fallback or a settings file.

Each object begins with the 24-byte secretstream header. Each encrypted frame has
a four-byte big-endian ciphertext length. First frame: encrypted JSON containing
only `logical_path`, tagged MESSAGE. Following frames: up to 1 MiB plaintext
each, tagged MESSAGE. Last frame: empty plaintext tagged FINAL; EOF must follow.
Authenticate canonical `format`, `version`, `profile_id`, `object_id`, `domain`
as associated data on every frame. This binds each object to its profile, key
domain and opaque identity. Framing lengths are bounded before allocation and
authentication detects modified, substituted, reordered and duplicated chunks.
Require FINAL to reject truncation at an otherwise valid chunk boundary and
reject trailing bytes. No partial plaintext is returned before complete
verification. Per-object bound is 512 MiB. Writes stream bounded chunks; prototype
reads verify into RAM and therefore require memory proportional to object size.

The proposed release format keeps opaque physical names and a separately
encrypted catalog containing logical paths, references, ownership, retention
and private metadata. Personal consumers receive only the personal-data store;
the provider credential service receives the distinct credential store. Neither
credentials nor catalog internals become filesystem/model tools. The prototype
returns object references in memory and does not implement a durable catalog,
quota, deletion, password change, backup engine or concurrent-process lease.

Proposed consumer interface: read a verified record/asset; commit an atomic
record/asset set under a profile write lease; remove a logical record and its
unshared derivatives; open a verified in-memory asset stream. A separate
credential provider begins/ends a provider session and loads/replaces/deletes
explicitly saved secrets. Consumers do not receive a general plaintext filesystem
root. Relative logical paths in the storage map are serialized inside encrypted
records, never used to construct host paths. Reject traversal/absolute paths.
Phase 2 freezes the concrete interface alongside transactional semantics.

## Version and persistence rules

Reject unknown major versions and unknown/duplicate fields before use. Never
guess an older parser or rewrite an unreadable original. Any future schema/key
topology change needs an explicit version and verified opt-in upgrade with source
preservation. The prototype only creates new directories, never an existing
profile, and has no migration path for real data.

Only complete authenticated objects are published. Prototype writes encrypted
staging, flushes/fsyncs and renames to a random final name; errors are fixed
messages and do not trigger plaintext fallback. A process crash can leave
encrypted orphan staging; directory durability, multi-object commits, disk-space
reserve, quota and safe reclamation are phase 2 gates. Storage usage includes
all encrypted originals, previews, indexes, staging overhead and retained managed
backups. Limits do not preallocate the requested quota. Refuse a quota below
actual usage. Lack of space or missing/read-only storage must preserve the last
consistent committed state and report the failed save.

## Lifecycle and job ownership

| State | Allowed access and transition |
| --- | --- |
| Unconfigured | Public setup/defaults only. Explicit selection/creation leads to locked; an explicit unencrypted legacy choice keeps existing behavior. No credential persistence without encryption. |
| Locked | No keys or protected readers, previews, preferences or provider sessions. Unlock success verifies identity and encrypted recovery/catalog consistency, then enters unlocked. Wrong password/failed unwrap stays locked with an ambiguous password-or-corruption error. Missing location enters unavailable. |
| Unlocked | Read/write only through the selected profile and valid generation-bound leases. Saved credentials load only for the configured provider connection; unlock alone never sends personal data to a model/provider. |
| Locking | Freeze admission of requests, jobs, reads and new write leases immediately. Cancel provider/image/preview/background jobs. An already admitted atomic commit may finish under its original lease before closure; it cannot start a new save. Drain/retire all old readers/leases before clearing references/keys. On timeout/error, remain blocked from new work rather than switching with active old work. |
| Unavailable | Storage disappeared, became read-only or could not persist safely. Invalidate leases, cancel jobs, release provider sessions/keys, stop protected views. Reconnect/reselect only the expected UUID and return to locked for explicit unlock/verification. No recreation at a missing path and no fallback storage. |
| Recovery required | Invalid/unsupported structure, authenticated object/catalog inconsistency or interrupted transaction requiring review. Freeze mutations. Offer explicit verified recovery/restore; show no protected contents while locked. Never retry or replay an uncertain host mutation. |

Each request/image job/background writer captures `(profile_id, session_epoch)`
and holds a bounded lease. The session epoch changes whenever access is revoked
or a profile is selected. A late callback must be discarded if either value
differs; it cannot save in a newly selected profile, resurrect a preview, load
an old credential or use a plaintext fallback. Retire the old worker/reader
references before allowing a new profile session. Manual/idle lock and exit
follow the same locking boundary. The synthetic prototype serializes calls with
an in-process lock and only models locked/unlocked plus failed-storage key
release; it does not claim application lifecycle wiring.

| Event | Required behavior when the application is connected in later phases |
| --- | --- |
| Switch profile | Cancel/drain old work, retire its leases, release cloud clients/credentials, clear composer/viewer/history/preference caches, lock old profile, then locate/unlock the new profile. Never merge old drafts/outputs into it. |
| Switch into cloud (session-only policy) | Ask on each transition, keep key in memory only for that provider session. Unlocking is not consent to save it. |
| Switch away from cloud | Cancel/drain relevant requests/images, release session key/client references. Keep only already committed encrypted results; incomplete outcomes remain explicit. |
| Independently used image provider | Use its own explicit connection-session boundary, ending on disconnect/lock/profile switch/exit. Apply the same session-only versus explicit-save policy to keys and tokens. |
| Lock during generation/streaming | Stop new admissions/writes, cancel work, dispose uncommitted frames/drafts and clear views after draining readers. Do not silently save late output after locking starts. An already committed result stays with its original profile. |
| SSD removal/local I/O failure/full disk | Enter unavailable, fail the save visibly, invalidate old callbacks and keys, preserve committed ciphertext. Reconnection requires identity verification; a provider result does not authorize another destination. |
| Forced exit | On restart start locked, inspect only the limited header/locator, unlock before recovery. Reconcile authenticated records and journal, report unknown outcomes; do not rerun tools. |
| Password change/recovery/restore | Requires phase 2 engine and explicit UI action; never a password-reset backdoor. Restore is verified ciphertext copy, not synchronization. |

## Locked visibility, previews and host boundary

While locked, a disk observer sees profile UUID/location, format and KDF parameters,
wrapped-key length, object count, encrypted file sizes/frame boundaries and file
timestamps/access patterns. This leaks approximate usage/timing and can link
copies of a profile. V1 does not promise padding or concealment of the vault's
existence. Names/titles/tags, project/recent-file lists, filenames, personality,
preferences, thumbnails, extracted text, relationships and indexes remain encrypted.

The current app has RAM image caches but still opens plaintext snapshots by real
path or descriptor. Later adapters must use verified in-memory `QBuffer`/streams
and clear previews on lifecycle changes. Do not pass vault assets to shell preview
or external editors implicitly. No persistent decrypted temp file is permitted by
default. A path-only feature remains unavailable until its narrow opt-in temp
policy and crash cleanup are audited; never describe that as zero host traces.

The prototype rejects static symlink/reparse paths but does not pin Windows
directories against races. It is a controlled offline experiment, not a tool-path
security boundary. Production path exclusions must cover aliases, traversal,
reparse paths and application-owned temporary locations and credentials. Neither
these exclusions nor encryption sandbox arbitrary host code.

Best-effort overwriting/dropping owned buffers does not erase Python/native/OS
copies, paging or crash dumps. Encryption protects stored data on a locked disk,
not an unlocked/compromised host. Explicit exports/clipboard copies, host project
originals, external provider retention and independent backups remain separate.
Security-qualified v1 requires independent review in phase 5.
