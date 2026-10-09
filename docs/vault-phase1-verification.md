# Personal Vault phase 1: implementation and verification

9 October 2026. Branch: `codex/vault-phase1`, based on local main `aeb350d`.
The user authorized phase 1 and explicitly requested only necessary tests,
overriding the repository's usual full-suite requirement. The requested feature
branch is retained for review; local main and remote refs are unchanged.

## Delivered scope

- [Storage map](vault-phase1-storage-map.md): current local/portable persistence,
  all roadmap personal-data categories, proposed destinations and deletion/retention.
- [Format/lifecycle contract](vault-phase1-contract.md): profile identity and
  location, limited public bootstrap, authenticated shared layout, separate keys,
  locked visibility, job ownership, failure behavior and relocation/restore.
- `app/vault/prototype.py`: explicit synthetic-only creation, password unlock,
  lock, immutable encrypted objects, bounded authenticated headers/frames, profile
  and credential-domain binding, complete-read verification and no plaintext fallback.
- `app/vault/benchmark.py`: reproducible synthetic PNG experiment, relocation,
  marker scans and content-free timing/size reports. No real credentials/content.
- Optional `vault-prototype` dependency in `pyproject.toml`: `PyNaCl==1.6.2`.
  The library was installed only under ignored `state/vault-phase1-deps/`.
  Normal startup and base dependencies do not acquire a vault backend.

This is an executable storage experiment plus a design contract. It does not
enable encrypted application storage, migrate files, expose setup/lock UI,
persist real credentials or implement the later transactional/quota/backup engine.
Synthetic `.pending` files are encrypted; crash-safe orphan recovery and multiple
process ownership are explicitly phase 2 work. Prototype reads use bounded
whole-object RAM after chunk authentication, not a production media streaming API.

## Focused verification

Initial prototype: **33 passed**, no skips/failures, in **3.21 seconds**.
Self-review then found that JSON escaping can expand Unicode logical names beyond
the metadata frame bound and that a source returning `None` could be mistaken for
EOF. Both are now rejected before invalid publication; ordinary Unicode paths
round-trip. Source-size failure cleanup is also covered. No existing tests or
acceptance prompts were changed.

Final focused run: **36 passed**, no skips/failures, in **3.80 seconds**.
Coverage includes local/portable simulated roots, source-preserving relocation,
reopening, wrong passwords, locked access, owned key-buffer clearing, limited
public header, plaintext marker exclusion, authenticated header edits, duplicate
fields, header/cost/frame bounds, profile/domain/object substitution, corruption,
truncation/missing FINAL, reordered/duplicated chunks, appended bytes, a valid
12 MiB+ image, zero-length content, failed publication, removed storage, handle
release, logical traversal and metadata/input edge cases.

The two native runs used repository-local temporary/cache folders and JUnit
results under ignored state:

```text
state/vault-phase1-tests/                 state/vault-phase1-cache/
state/vault-phase1-focused.xml
state/vault-phase1-tests-final/           state/vault-phase1-cache-final/
state/vault-phase1-focused-final.xml
```

Source compilation and Git whitespace checks passed. A fresh normal-runtime
import of `app.vault` and `app.startup` succeeded without importing `nacl`, proving
the optional experiment is not required by application startup. Preservation
hashes matched for all seven config/preference paths, including absent files.
Ref/worktree maps and those content-free hashes are retained under
`state/backups/vault-phase1-20261009/`. No other worktree or historical tip was changed.

## Large-image experiment

Windows, Python 3.12.10, PyNaCl 1.6.2. A synthetic RGB PNG measuring **3072 × 3072**
and **28,318,532 bytes** was created only in RAM. For each policy and location,
the experiment stored a synthetic record, credential and image; verified all
three; measured three unlocks; copied ciphertext to a new directory while locked;
verified the relocated image; and scanned both copies for synthetic private
names/content/password/image marker bytes. No scanned plaintext marker was found.

| KDF candidate | Location simulation | Median unlock | Image write | Verified image read | Original encrypted usage |
| --- | --- | --- | --- | --- | --- |
| Argon2id, 2 operations / 64 MiB | Local | 42.266 ms | 72.961 ms | 86.469 ms | 28,319,972 bytes |
| Argon2id, 2 operations / 64 MiB | Portable | 49.241 ms | 65.449 ms | 88.476 ms | 28,319,972 bytes |
| Argon2id, 3 operations / 256 MiB | Local | 291.953 ms | 70.733 ms | 90.026 ms | 28,319,973 bytes |
| Argon2id, 3 operations / 256 MiB | Portable | 289.829 ms | 70.205 ms | 93.801 ms | 28,319,973 bytes |

The 64 MiB measurement precedes the metadata/input edge-case refinement; the
256 MiB measurement uses the final implementation. Both validate complete
large-image round trips. Final focused tests exercise the unchanged 64 MiB
candidate as well. No timing is an acceptance assertion or a security guarantee.

Reports with fixed labels/counts/versions only:

```text
state/vault-phase1-experiment/report-ea05d25e9ddb4d09aa55d47025230de8.json
state/vault-phase1-experiment-final/report-0c30a7ac361c43c9b209e6dd0eaef8ba.json
```

## Reproducing necessary checks

With an ordinary development Python installation, install the optional extra
using `python -m pip install -e ".[vault-prototype,test]"`. Then run only:

```powershell
python -m pytest tests/test_vault_prototype.py --basetemp=state/vault-checks -o cache_dir=state/vault-cache
python -m app.vault.benchmark --output-root state/vault-experiment
python -m app.vault.benchmark --output-root state/vault-experiment-moderate --kdf-policy moderate
```

This checkout's bundled Windows Python ignores `PYTHONPATH`; its isolated
prototype dependency folder was supplied by inserting its absolute path into
`sys.path` and invoking pytest/the benchmark with `runpy`. No interpreter path
configuration or existing runtime dependencies were edited.

The first download attempt was blocked by sandbox networking (`WinError 10013`).
The explicitly scoped native download succeeded. The sandbox then could not
read newly installed dependency subdirectories, so tests/experiments ran in the
native Windows shell. These environment restrictions are not product failures;
there were no failed pytest checks. No broad permissions/ACL changes were made.

## Gates deliberately not claimed

- **Full existing regression suite: not run**, as explicitly requested. Only the
  36 vault cases, source/whitespace checks and import isolation smoke were required.
- **Physical SSD and second Windows account/host: not qualified.** Both storage
  modes used different simulated directories on this development machine, with
  actual encrypted copying/reopening. The benchmark accepts explicitly chosen
  parent paths for later real-location exercises, and reports the simulation flag.
- **Minimum-supported-machine unlock measurements: pending.** The repository
  does not provide a qualified minimum host for this new storage feature. The
  development timings compare two policies without selecting the release cost
  or claiming a minimum-host responsiveness guarantee.
- **OS forensic preview/cache/temp audit: pending.** Source sinks/consumers are
  mapped, and known prototype outputs were marker-scanned. Host thumbnails,
  paging, crash dumps, external editors and OS/security-tool copies were not
  exhaustively inspected and are not covered by a zero-trace claim.
- **Independent format/key/path/recovery security review: pending.** The storage
  map/contract received implementation self-review, not independent qualification.
- **Live models/APIs and application lifecycle integration: not run.** This phase
  needs no network inference, real API keys or model switching. Production
  concurrency, quota, crash recovery, password change/recovery and all feature/UI
  wiring retain their later-phase gates.

The phase 1 code and design deliverables are ready for review. Its full roadmap
exit condition remains conditional on minimum-host/real-location evidence and
review; it is not represented as a security-qualified vault release.
