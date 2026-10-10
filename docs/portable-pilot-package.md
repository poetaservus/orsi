# Cloud-only portable pilot, 10 October 2026

The sanitized Windows x64 pilot is assembled and checked from its ZIP. The user
selected cloud-only; no local model is bundled. This step starts from local main
`bdf3d66` on `codex/portable-pilot-package` and changes only package assembly,
its checks and documentation.

## Deliverable

- ZIP: `dist/orsi-cloud-pilot-20261010-bdf3d66.zip`
- SHA-256 sidecar: the same filename followed by `.sha256`
- Archive size: **305,193,322 bytes (291.1 MiB)**
- SHA-256: `d6f0ecbfc7cac5247d9deefefcfffff778912fcef56fd1af8b8f8541b668d1fe`
- Application source: `bdf3d66ddd5fdf3e23174f1df59a977538e68343`
- Inventory: **7,142 payload files**, plus `PACKAGE_MANIFEST.json` itself.

The manifest records every payload size and SHA-256, the exact application
source commit, and the assembler's SHA-256. The archive checksum also covers the
manifest. The application commit precedes this packaging-tool commit; no
application code or configuration changed during this step.

The ZIP and its pristine unpacked sibling remain under ignored `dist/`. All
smoke-test state is confined to separately extracted copies under ignored
`state/`; none was added to the deliverable.

A later Qt 6.12 correction restores the four profile number fields. Apply the
small `dist/orsi-number-fields-fix-20261010.zip` overlay to this original pilot;
see [the correction and update instructions](profile-number-fields.md). The
original pilot ZIP and checksum are unchanged.

## Use the pilot

Extract the entire ZIP to a writable folder and run `ORSI.cmd`. Before personal
work, open **Settings > Personal profile > New profile**, choose portable
storage inside that application folder, and enable encryption with your own
password. In **Cloud access**, enter your own OpenAI API key; use session-only
entry or explicitly consent to encrypted saving. The bundled `START_HERE.txt`
contains these instructions.

Close O.R.S.I fully before moving or copying its complete folder, including the
profile. Keep independent instances in separate folders. A profile permits only
one active owner. Internet access and the user's own API account are required
for cloud inference.

## Assembly boundary

`tools/assemble_portable_pilot.py` exports the committed `app/` tree and an
explicit list of public launch/configuration/verification files using Git. It
does not copy working-tree configuration edits, developer state, profiles,
credentials, `.env`, Git metadata, tests or untracked application files.

The runtime input is the previously verified fresh cloud build at
`state/pvp-fresh-cloud-fixed/runtime`, not the user's working runtime. The
assembler requires the cloud READY marker, complete embedded Python and
application-relative import paths, rejects filesystem links, and keeps vendor
licenses/data. It omits runtime bytecode caches and absolute-path pip launchers.
It creates empty `state/` and `models/`, inventories and verifies the result,
then writes a ZIP and checksum without replacing an existing output.

To assemble another pilot from the current committed application, use a fresh,
verified cloud runtime and a new output name:

```powershell
runtime\python\python.exe -m tools.assemble_portable_pilot `
  --runtime state\pvp-fresh-cloud-fixed\runtime `
  --destination dist\orsi-cloud-pilot-new
```

Build a replacement runtime only in a separate clean public staging tree, using
`packaging/build-portable-runtime.ps1 -Backend cloud`. Preserve the active user
runtime. Each new archive needs its own extracted-artifact checks.

## Necessary verification

At the user's request, this step ran only the checks needed for the package.
It did not repeat the full repository suite or call a live provider.

- **9 unit cases passed in 3.73 seconds**, covering committed-public export,
  private-source preservation, licenses, cache omission, existing-output
  preservation, four invalid runtime inputs, and three payload/state/profile
  tampering cases. Pytest used repository-local `--basetemp state/ppp-unit`.
- Both the initial package and a fresh ZIP extraction matched all **7,142**
  inventory entries. The final pristine deliverable also passed; its archive
  checksum and assembler identity still match.
- The extracted `ORSI.cmd` opened a real native Windows window from an unrelated
  working directory, with spaces in the extraction path. Normal window close
  released all processes belonging to that extracted runtime.
- The extracted runtime passed the offline SDK transport/lazy-client check,
  real encrypted-vault round trip and cleanup, cloud capability composition,
  off-screen GUI startup and dependency consistency (`pip check`). Installed
  versions: Python 3.12.10, OpenAI 2.54.0, PyNaCl 1.6.2 and PySide6 6.12.0.
- Native `pythonw` startup created a synthetic encrypted portable profile,
  retained personal/credential records and chat history, then locked and exited.
  A new process began locked without composing personal consumers; password
  entry unlocked it and verified the records and archived chat. Moving that
  whole extracted folder to a new parent and repeating restart also passed.
- The native profile probes used the package's real application/backend code,
  isolated synthetic user directories, no API keys and a network-denying audit
  hook: **zero connection attempts**. They verified loading-helper exit, closed
  inference clients, zeroed keys, released vault leases and reusable desktop
  ownership. No owned test processes remained.

The first restart probe incorrectly expected prior messages in the active chat.
Existing startup behavior archives those messages and starts empty. After
correcting the probe to check the encrypted archive and empty current chat, the
restart and relocation passed. Application behavior was unchanged; the failed
probe reports are retained separately.

Evidence is under ignored `state/portable-pilot-package-*`: unit XML/log,
assembly/extraction/final reports, launcher report, preflight/dependency logs,
and fresh/restart/relocated native reports. The reusable native observation
probe is `tests/pilot_package_probe.py`; run it only against an owned synthetic
extraction with isolated user directories. It is not shipped in the ZIP.

## Preservation and remaining qualification

All fourteen starting settings/runtime/artwork fingerprints match, and all four
other worktree tips and attachments remain unchanged. Recovery evidence is in
`state/backups/portable-pilot-package-20261010/`. Prior main is preserved at
`archive/2026-10-10/main-before-portable-pilot-package`; integrate by local
fast-forward and remove only the merged feature branch. No remote publication.

This artifact is ready for pilot qualification. Physical SSD/removable-media
handling, another Windows host/account, minimum-host performance, live provider
acceptance and independent security review remain unqualified. Same-host folder
relocation is recorded separately from those gates. Earlier suite results and
the repaired regression cases remain in
[runtime verification](portable-vault-packaging.md) and
[regression maintenance](portable-regression-gates.md).
