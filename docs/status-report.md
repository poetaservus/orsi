# O.R.S.I status report

Date: 2026-09-12

## Overall status

Phase 9 bounded text reading is implemented and enabled in the development copy on
`codex/phase-9-filesystem-read-text`, based on approved GUI checkpoint `2313d56`.
The user confirmed the enabled app workflow works on 2026-09-12. Full Phase 9 is not yet complete;
bounded search remains unimplemented.

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
- Filesystem mutation, shell/process execution, window control, clipboard access, network paths,
  device namespaces, and host-wide search are not enabled.

## Verification

- Complete integrated suite after enablement: 298 passed, 14 skipped on Windows on 2026-09-12.
- Deterministic tests cover list-to-read actual content, direct-path reads, literal Markdown fences,
  untrusted-content isolation, strict decoding/bounds, permissions, cancellation, and disclosures.
- Manual workflow acceptance: user confirmed the enabled app works on 2026-09-12.
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
