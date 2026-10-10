# Portable encrypted-profile packaging, 10 October 2026

This bounded change starts from local main `8335102` on
`codex/portable-vault-packaging`. It closes the first packaging gap identified
in the portable-instance readiness assessment: fresh runtimes did not install
PyNaCl, and their package check could pass without exercising encryption.

## Change

`requirements.txt` now includes `PyNaCl==1.6.2`, matching the existing Windows
extra in `pyproject.toml`. The shared offline runtime verifier checks both
declarations against the installed crypto version. The portable runtime builder
and the existing Nuitka preflight both use that verifier.

The added check creates a unique fixture beneath the package's ignored `state/`
directory, with its own application root and portable profile locator. It writes
and reads fixed synthetic personal and credential records, locks the profile,
checks that a locked read is denied, reconstructs the profile manager, unlocks
and reads the durable records again. It then checks that keys were zeroed,
vault leases were released and the owned fixture was removed. Exceptions fail
the package gate; the CLI reports only the exception type. The selected user
profile is never opened by this encryption check.

The fresh cloud build also exposed a PowerShell argument bug: a one-element
array produced by an `if` expression became a string, so splatting passed
`--cloud-only` as individual characters. A typed string array now preserves
the single option. The build still writes `runtime/READY.txt` only after its
verification gates pass.

No application prompts, routing, tool behavior, model profiles, sampling,
context policy or existing acceptance assertions changed. The current user
runtime was not rebuilt or replaced.

## Focused verification

An unrestricted native Windows shell ran the new packaging cases plus the
existing OpenAI qualification, vault-engine and llama-server inference tests:
**125 passed in 29.88 seconds**. Temporary data and pytest cache were kept under
`state/pvp-focused` and `state/pvp-focused-cache`.

The five added cases cover a real encrypted round trip with existing-instance
sentinels preserved; encryption-failure cleanup of keys, leases and files;
missing/mismatched dependency declarations; and a fresh subprocess where nacl
imports are blocked. That public CLI check exits unsuccessfully, emits only a
fixed exception-type report, and does not expose the synthetic environment key.

The changed Python files parse successfully, `git diff --check` passes, and the
current runtime's dependency consistency check passes. Focused evidence:
`state/portable-vault-packaging-focused.xml` and the matching `.log`.

## Fresh cloud runtime

The actual portable builder completed successfully in
`state/pvp-fresh-cloud-fixed`, starting with 227 tracked public source,
configuration and build files and no copied runtime, state or models. It
downloaded the hash-verified official Python 3.12.10 x64 embeddable runtime and
installed the declared requirements from scratch.

The installed SDK is 2.54.0, PyNaCl is 1.6.2 and PySide6 is 6.12.0. The SDK
transport/lazy-client check, real vault create/write/read/lock/reopen/release
check, cloud native-tool startup and off-screen GUI startup/teardown all passed.
`runtime/READY.txt` was produced; dependency consistency passed; no owned Python
processes or temporary verification vaults remained. No live provider request
was made. Dependencies with floating ranges resolved to current versions in
this new runtime; the working runtime remains unchanged.

The first isolated build in `state/pvp-fresh-cloud` installed crypto correctly
but failed on the cloud-option argument bug described above, before writing a
READY marker. Its evidence is retained separately. The successful build used a
new empty staging folder after that correction.

Fresh-build evidence is recorded in
`state/portable-vault-packaging-fresh-build-fixed.log`,
`state/portable-vault-packaging-fresh-pip-check.log` and
`state/portable-vault-packaging-fresh-summary.json`. This is an isolated build
check, not a sanitized release archive or physical-portability qualification.

## Regression run

The first full-suite attempt used native Windows Qt and ended with access
violation `0xC0000005` in Python's `mimetypes.read_windows_registry`, called by
an existing attachment-import worker during
`test_cloud_picker_accepts_multiple_in_order_without_small_cap`. It ended before
the new packaging tests and is recorded as an aborted run, not a passing gate.
Evidence: `state/portable-vault-packaging-full.log`.

The subsequent full suite used the same off-screen Qt platform as the readiness
baseline, an unrestricted Windows shell, disabled opt-in live gates and
repository-local `--basetemp state/pvp-full-offscreen`. It completed with
**3,041 passed, 9 failed, 60 skipped and 15 subtests passed in 829.53 seconds**.
The failure identities and skipped-case identities exactly match the baseline;
all five new packaging cases passed. The full suite remains a failing release
gate, with no new regression found in this comparison.

The nine unchanged failures are:

- Two attachment lifecycle and three skill/history persistence cases still
  inject failures into an old JsonStore instance rather than the current save
  boundary. These are the five persistence cases in
  `test_attachment_lifecycle.py`, `test_skill_reference_conversations_v1.py`
  and `test_turn_outcomes.py` identified in the readiness assessment.
- Two startup cases in `test_inline_approvals.py` still supply a paths mock
  without the application root now required by desktop ownership.
- The local/portable profile-tab cases in `test_vault_controls.py` still fail
  to select the Saved credential policy with off-screen synthetic interaction.
  Both passed natively in the earlier readiness assessment; this step leaves
  their platform discrepancy unresolved.

The 60 skips are recorded separately: 51 opt-in live cases, seven host symlink
cases and two native UI-platform cases. No live gate is counted as passed.
Evidence: `state/portable-vault-packaging-full-offscreen.xml`, its matching
`.log`, and `state/portable-vault-packaging-full-comparison.json`.

## Remaining qualification

This step qualifies the encryption dependency and package preflight. A sanitized
release archive, CPU/CUDA runtime rebuilds, compiled executable, live provider
and model gates, physical SSD relocation, another Windows host/account,
minimum-hardware measurements and independent vault security review are still
separate release work.

All fourteen preservation fingerprints match the starting values, and all four
other worktree tips and branch attachments are unchanged. Recovery refs,
worktree tips and content-free preservation fingerprints are stored beneath
ignored `state/backups/portable-vault-packaging-20261010/`. Prior main is retained
at `archive/2026-10-10/main-before-portable-vault-packaging`. No remote branches
are published or deleted by this change.
