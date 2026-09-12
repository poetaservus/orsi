# O.R.S.I status report

Date: 2026-09-12

## Overall status

Phase 10 is continuing on `codex/phase-10-filesystem-move`, based on approved copy checkpoint
`9376a7e`. The fourth development checkpoint adds approved moving of one bounded regular file with
exact source, destination, and collision-policy preview. Phase 10 is not complete: trash remains
unimplemented.
The user requested this progression while Phase 9 bounded search and the dedicated text-read
real-model matrix remain outstanding. Phase 9's enabled file-reading workflow was manually
confirmed on 2026-09-12. Phase 10 text writing, copy, and move were manually reported working on
2026-09-12.

## GUI status: approved and integrated

- The mockup-aligned dark interface is now the project baseline.
- The custom PNG background is stored under `app/ui/assets/`.
- The central conversation block uses a uniform opaque fill, independent of the background image.
- The context-window meter appears in the main chat and moves to a centered header in compact mode.
- The composer is smaller, darker, vertically balanced, and centered at wide and compact sizes.
- Assistant responses and user bubbles keep balanced gutters inside the central block in compact
  windows.
- The settings menu remains available from the left navigation rail.

## Runtime status

- General conversation works through local or cloud inference.
- `filesystem.stat`, `filesystem.list`, and `filesystem.read_text` are enabled in the checked-in
  development configuration at the user's explicit request. Missing configuration still defaults
  to disabled, and invalid configuration or native startup failures retain the chat-only fallback.
- Full-local read scope requires explicit acknowledgement on every application launch. Declining
  confines the enabled read capabilities to the portable root.
- Text reads default to 16,384 bytes and 200 lines, with hard limits of 65,536 bytes and 1,000 lines.
  UTF decoding is strict, binary content is rejected, and byte/line truncation is reported.
- Explicit Windows paths and unique exact-name/stem references from an active listing are routed
  deterministically. This path displays the actual returned excerpt directly and does not generate
  a summary in the same turn.
- UI status and host/cloud disclosures now cover requested file content. File contents remain
  untrusted data; the deterministic read path does not execute instructions found inside them.
- `filesystem.mkdir` has a separate enabled development gate, disabled when configuration is absent.
  An explicit create-folder request with an absolute path opens an exact-path approval dialog.
  Cancel is the default; approval is single-use and expires after 60 seconds. Read acknowledgement
  never grants write authority. Missing parent folders and existing targets are not changed.
- Host-write policy rejects redirected, network, device, ambiguous, protected application/state,
  standard OS, recovery, and installed-application paths. Execution pins ancestors, checks the
  approved parent's identity, creates one child atomically, and verifies the returned directory handle.
- Read and ordinary model turns cannot access the write capability. Folder creation uses the
  explicit user target and a deterministic result, without model tool selection or generated claims.
- `filesystem.write_text` has a separate enabled development gate and mandatory approval. An exact
  write request must include an absolute file path and exact text. The approval dialog shows the
  path and content as readonly plain text; Cancel remains the default. Text writes are bounded to
  65,536 UTF-8 bytes and 1,000 lines.
- Text writing uses a same-directory temporary file, flushes it, atomically replaces the target, and
  verifies the final file by identity and SHA-256 digest. If the target appears, disappears, or is
  replaced after preview, the write is denied and the newer entry is preserved.
- `filesystem.copy` has a separate enabled development gate and mandatory approval. Exact copy
  requests include a source path, destination path, and collision policy. Default collision behavior
  refuses an existing destination; explicit replace binds the destination identity before replacing.
- File copying is limited to 16 MiB, copies only regular non-reparse files, writes through a
  same-directory destination temp file, atomically places the result, and verifies final identity and
  SHA-256 digest. If the source or destination changes after preview, the copy is denied.
- `filesystem.move` has a separate enabled development gate and mandatory approval. Exact move
  requests include a source path, destination path, and collision policy. Default collision behavior
  refuses an existing destination; explicit replace binds the destination identity before replacing.
- File moving is limited to 16 MiB and regular non-reparse files. Same-drive moves use native
  rename/replace placement and verify the destination digest. Cross-drive moves copy through a
  same-directory destination temp file, verify placement, then remove the source. If the source or
  destination changes after preview, the move is denied.
- Interrupted or unverified writes require review before further operations, including across restart.
  A failed result save also blocks the live session. No automatic retry, rollback, or deletion occurs.
- Other filesystem mutation, shell/process execution, window control, clipboard access, network
  paths, device namespaces, and host-wide search are not enabled.

## Verification

- Complete integrated Phase 10 suite after move: 429 passed, 14 skipped on Windows on
  2026-09-12.
- The 131 Phase 10 cases cover actual native folder creation, exact approval, denial, expiry, cancellation,
  collisions, changed parents, protected/reparse paths, read/write isolation, unknown outcomes,
  result-save failure, restart recovery, exact text-write previews, create/replace behavior, target
  replacement after approval, exact copy previews, collision policy, source/destination changes after
  approval, exact move previews, source removal, hostile read-content isolation, and real Qt
  worker/dialog interactions.
- Folder approval-dialog screenshot inspected with actual Windows fonts; path and controls are readable.
- Historical Phase 9 suite after enablement: 298 passed, 14 skipped.
- Deterministic tests cover list-to-read actual content, direct-path reads, literal Markdown fences,
  untrusted-content isolation, strict decoding/bounds, permissions, cancellation, and disclosures.
- Manual Phase 9 workflow acceptance: user confirmed the enabled app works on 2026-09-12.
- Manual Phase 10 text-write application acceptance: user reported it works on 2026-09-12.
- Manual Phase 10 copy application acceptance: user reported it works on 2026-09-12.
- Manual Phase 10 move application acceptance: user reported it works on 2026-09-12.
- Folder create/cancel manual acceptance if not already tested and real-model follow-up conversation
  after writes remain pending.
- The dedicated automated text-read real-model call/no-call matrix has not been run.
- Historical GUI baseline visual checks passed at 1920-pixel and 1280-pixel window widths.

## Known follow-up work

- In-progress inference cancellation is not yet immediate for every backend.
- Malformed conversation JSON still needs a preserve-and-recover path.
- Conversation state is persisted during the active run but is not replayed visually; each new
  application launch currently starts a fresh private session.
- Complete the dedicated automated text-read real-model matrix, including ordinary conversation
  after a read, before proceeding to the next separately designed capability, bounded search.
- Fresh-runtime packaging and real-model/UI acceptance remain before portable release promotion.
- Phase 10 is a development-only feature-branch checkpoint. Confirm move preview/create/replace/cancel
  workflows were manually accepted before continuing to trash. See `phase10-mkdir-threat-review.md`,
  `phase10-write-text-threat-review.md`, `phase10-copy-threat-review.md`, and
  `phase10-move-threat-review.md` for protection scope and recovery limitations, including
  nonstandard application/service locations.

## Checkpoint scope

- The Phase 10 folder-creation checkpoint is committed on `codex/phase-10-filesystem-mkdir` at
  `076007f`. The text-write checkpoint is implemented and tested on
  `codex/phase-10-filesystem-write-text` and committed at `6a8fcbb`; the user reported the
  text-write workflow works on 2026-09-12. The copy checkpoint is committed locally at `9376a7e`;
  the user reported the copy workflow works on 2026-09-12. The move checkpoint is implemented,
  tested, and manually accepted on `codex/phase-10-filesystem-move` but is not pushed, merged, or
  release-promoted.
- The private Desktop `statusreport.md` remains outside Git and records the resulting commit ID.
