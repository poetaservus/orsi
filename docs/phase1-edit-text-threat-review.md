# Phase 1: exact text editing threat review

Date: 2026-09-26
Status: implemented and deterministic/local-model verified; production gate remains off pending review and manual acceptance.

## Authority and scope

`filesystem.edit_text` edits one existing UTF-8 regular file at an exact absolute local
path. It uses a separate default-off gate and WRITE/ASK permission. Model output,
file content, and previous approvals cannot authorize execution. No fuzzy matching,
patch parser, file creation, shell, or additional path authority is introduced.

## Preparation and approval

- Strict arguments specify nonempty `old_text`, `new_text`, optional `replace_all`
  (false by default), and optional expected SHA-256 of the complete source bytes.
- The existing host-write policy rejects protected, redirected, UNC, device, ADS,
  relative, and ambiguous paths. Every ancestor is pinned during preparation and execution.
- Read the source through a non-following Windows handle that excludes write/delete
  sharing. Validate regular-file identity on that same handle. Bound source and result
  size before materializing a diff; reject binary controls and invalid UTF-8.
- Derive preview and identity/digest binding together from one snapshot, avoiding a
  preview-versus-identity race between separate preparation hooks.
- Match exact text, preserving BOM and all bytes outside replacements. Do not normalize
  newlines. Reject missing, ambiguous, overlapping, and no-op replacements.
- Show a complete bounded diff; reject oversized previews rather than hide changes.
  Escape diff lines so CR/LF, tabs, control characters, and invisible Unicode are explicit.
- Approval binds canonical arguments, target path, parent/file identity, source digest,
  and the trusted preview through the existing request hash. Approval remains expiring
  and single-use; closing or cancelling the dialog denies the edit.

## Execution and failure

- Recompute the edit from a fresh snapshot and compare the approved identity/digest.
  Recheck again after the temporary file is flushed, immediately before atomic replacement.
- Reuse same-directory temporary creation, flush/fsync, atomic replacement, cleanup,
  and final identity/digest verification. Cancellation before replacement removes the
  temporary file; interruption or unverifiable outcomes retain existing journal review blocks.
- The inherited path-based atomic-replace primitive cannot provide an OS-level compare-and-swap
  against hostile concurrent leaf replacement in the final handle-close/replace interval.
  Ancestor pinning and immediate revalidation narrow this interval; do not claim a fully
  race-free transaction against adversarial concurrent writers.
- Return only path, changed-line counts, replacement count, and final SHA-256. Ordinary logs
  and the durable journal must not contain source text, replacement text, or diff content.
- Leave the production gate off until deterministic, UI, and live-model acceptance passes.

## Verification targets

Exact approved edit of the 65 KB CSS fixture; UTF-8 BOM/CRLF preservation; complete escaped
preview; zero/multiple/overlapping matches; optional digest mismatch; changed content with
unchanged file identity; target/parent replacement; pre-replace race; cancellation and cleanup;
denial/expiry/replay; protected paths/reparse targets; unknown-outcome restart blocking;
read-only turn isolation; default-off registration; real Qt approval; opt-in local-model workflow.

## Implementation and verification

- `app/capabilities/filesystem_edit_text.py` enforces a 1 MiB source/result ceiling,
  10,000-line ceiling, 16,384-character fragments, and a 32,768-character complete diff.
  Non-overlapping replace-all is explicit. BOM is retained and newline bytes are never normalized.
- `Capability.approval_details` allows snapshot-based preparation without altering the
  existing capabilities' preview/identity hooks. The Windows snapshot reader validates identity
  and regular-file attributes through the same non-following handle used for the bytes.
- `filesystem.read_text` supplies `sha256` only when its byte read reaches EOF. A line-limited
  response can still carry the full-byte digest; a byte-limited excerpt returns `sha256: null`.
  This adds no paging or increased read limits.
- Exact edits are integrated with feature configuration, catalog, WRITE/ASK permissions,
  current turn routing, full/compact prompts, and the readonly Qt diff approval surface.
- Final full suite on 2026-09-26: **674 passed, 46 skipped**. Command:
  `runtime\python\python.exe -m pytest -o addopts='' -q -p no:cacheprovider --basetemp C:\Users\yaboy\Desktop\orsi_phase1_final_20260926`.
  This includes 55 additional passing deterministic tests compared with Phase 0. Additional
  skips are the opt-in live edit test and a symlink fixture the host could not create.
- With `ORSI_RUN_LIVE_EDIT_TEXT=1`, `tests/test_phase1_edit_text_live.py` passed against the
  configured bundled Qwen 14B model in 61.26 seconds. The model read a bounded excerpt of
  the 65 KiB CSS fixture, requested one approved compact edit, and preserved every other byte.
  Approval was supplied by the fixture callback; this is not manual UI acceptance.
- Qt offscreen acceptance verifies the exact target, readonly escaped diff, Cancel default,
  and successful approved execution. Visible launcher checks and manual accept/deny checks
  remain pending. Reparse rejection relies on the existing policy and native attribute check;
  the new actual symlink test requires a host with symlink creation privileges.

## Development activation and handoff

The checked-in production configuration remains unchanged. For manual acceptance, set
`ORSI_ENABLE_FILESYSTEM_EDIT_TEXT=1` along with the existing metadata and text-read gates,
then launch the development application. Each edit still needs its own dialog approval.
Use a disposable file outside O.R.S.I. and AppData. Check an accepted edit, a denied edit,
and an externally changed source after preview; verify the context meter and unchanged
surrounding text. Review the residual close/replace race described above before promotion.

Phase 1 is not merged. Phase 2 remains queued until Phase 1 review and merge; multi-block
patching and fuzzy matching are not introduced in this checkpoint.
