# O.R.S.I status report

Date: 2026-09-16

## Overall status

The active development line is `codex/phase-9-target-resolver`. It builds on the accepted Phase 10
trash checkpoint `e5a6092` and Phase 9 search, then adds the target resolver, planner-first
capability loop, bounded filename disambiguation, and GUI v2 polish through code checkpoint
`da7e7d9`, plus the accepted resolver-workflow hardening in the current checkpoint. The branch is
published to GitHub and tracks `origin/codex/phase-9-target-resolver`. Manual application acceptance
is complete for Phase 10 trash, Phase 9 search, and the five resolver/planner workflows tested in
`ORSI_TEST`. The current gate is fresh-runtime packaging and packaged GUI smoke checks before any
release promotion. The version remains `v0.4.0-dev`.

## GUI status: v2 integrated with September 15 polish

- GUI v2 is implemented on `codex/phase-9-target-resolver` through `da7e7d9`.
- The v2 background and top instrumentation bar are in place, with left-side controls and persistent
  `O.R.S.I. v0.4.0-dev // Local // Context Window` status text.
- The chat transcript is centered over the dark background with quiet assistant text, rounded user
  bubbles, code blocks, and copy controls.
- The composer was rebuilt as the v2 bottom pill. The custom hover implementation from `75467d8`
  was reverted in `e0cf7a6`; `76167c8` keeps normal Qt send-button rendering while padding the hover
  state correctly.
- `228295d` keeps the send/stop hover radius consistent with the normal button radius after the
  restored hover-state tweak.
- `ab8ab75` adjusts the restored hover boundary with explicit hover padding and radius styling.
- `05576da` refines the hover padding to keep the normal button radius while widening the hover
  highlight boundary.
- `2fb1363` restores the send-button cropped asset and the normal 23px button radius for the final
  pushed 2026-09-13 GUI v2 state.
- `3ec7d0b` applies the 2026-09-15 GUI polish pass: bundled Saira font assets, Saira Regular
  typography, a smaller composer/input/send-button scale, clearer placeholder contrast, slimmer and
  slightly darker user bubbles, and the cleaned composer/send-button asset state.
- `da7e7d9` hardens that typography pass by reapplying Saira Regular when shared Qt app state is
  reset by other dialogs or tests.
- The transcript-under-input effect is now an invisible bottom lens rather than a visible panel. It
  captures the scrolling transcript content, repaints the matching background, and blends back only
  a high-quality Qt-blurred text layer with a feathered top edge aligned to the composer.
- The version remains `v0.4.0-dev`; GUI v2 is a development checkpoint, not a release-version bump.

## Runtime status

- General conversation works through local or cloud inference.
- Cloud provider compatibility was refined on 2026-09-16: `config/cloud.json` can now carry
  non-secret provider headers, optionally omit strict tool metadata for providers that reject it,
  and omit `tool_choice` when required. The cloud selector now names the configured provider instead
  of always saying `Cloud · Free`. API keys remain session-only or environment-sourced and are still
  rejected from config headers.
- `filesystem.stat`, `filesystem.list`, `filesystem.read_text`, and `filesystem.search` are enabled in the checked-in
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
- `filesystem.search` has a separate enabled development gate. It searches for literal text inside
  one explicitly requested directory tree, defaults to depth 3, 256 files, 16,384 bytes per file,
  and 25 returned matches, and hard-limits depth to 8, files to 1,024, file bytes to 65,536, and
  matches to 100. It skips symlink/reparse entries and non-UTF or inaccessible files, returns only
  bounded snippets, and treats snippets and filenames as untrusted data.
- `filesystem.find` has a separate enabled development gate for bounded exact-name lookup inside
  one requested directory. The deterministic target resolver supports known-folder aliases such as
  Desktop and Downloads only when the user supplies an exact file or folder name; it does not
  recurse, fuzzy-match, index, read file content, or search the whole host.
- The planner-first capability loop has been restored for natural-language filesystem requests.
  Resolved file/folder targets are retained for bounded follow-ups, including affirmative replies,
  listing a previously found folder, reading a previously named file, and fixing a previously read
  file.
- Bounded filename disambiguation is limited to the requested directory and exact filename/stem/
  extension variants. It is designed for cases such as a spoken or typed name missing its extension,
  while still refusing fuzzy, recursive, indexed, or host-wide guesses.
- Resolver-workflow hardening now deterministically recovers from real-model misses in the accepted
  `ORSI_TEST` suite: same-session `there` listing follow-ups no longer depend on the model asking
  for the right directory again; named Desktop-folder child creation resolves the parent before
  `filesystem.mkdir`; direct Desktop folder creation resolves Desktop before `filesystem.mkdir`; and
  extensionless file-read requests recover when the model asks for a full path by using the bounded
  same-folder `filesystem.find` / `filesystem.list` / `filesystem.read_text` path.
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
- `filesystem.trash` has a separate enabled development gate and mandatory approval. Exact trash,
  recycle, or plain delete requests include one target path and reject permanent-delete wording. The
  approval dialog shows the exact target and Recycle Bin destination; Cancel remains the default.
- File trashing is limited to 16 MiB and regular non-reparse files. The operation binds the target
  identity, target SHA-256 digest, and parent identity before approval, rechecks them after approval,
  then uses the Windows shell file-operation API with Recycle Bin semantics. Automated tests fake the
  dispatcher; the real shell operation was manually reported working on 2026-09-13.
- Interrupted or unverified writes require review before further operations, including across restart.
  A failed result save also blocks the live session. No automatic retry, rollback, or deletion occurs.
- Other filesystem mutation, shell/process execution, window control, clipboard access, network
  paths, device namespaces, background indexing, and unbounded host-wide search are not enabled.

## Verification

- Manual resolver/planner application acceptance was reported green by the user on 2026-09-16 for
  all five `ORSI_TEST` workflows: named Desktop folder listing, `there` follow-up listing, creating a
  child folder inside the named Desktop folder, creating a folder directly on Desktop, and reading the
  extensionless `atiflix css` file request.
- Cloud compatibility focused verification on 2026-09-16: cloud/protocol tests passed with 52
  passed; GUI tests passed with 22 passed; the wider cloud/protocol/UI/conversation/Phase 8 sweep
  passed with 94 passed using a writable temp root. Full-suite reruns were attempted but the sandbox
  temp locations available in this session were intentionally rejected by Phase 10 write-path
  protection as protected/unavailable targets; no cloud/protocol failures appeared in those runs.
- Manual cloud smoke reported by the user on 2026-09-16: the cloud model handled a deliberately
  vague request to organize files by extension, understood Hungarian, and planned/executed tool calls
  from Hungarian user instructions.
- GUI composer scale tweak on 2026-09-16: the bottom input/composer bar was scaled down by about
  15% while preserving the centered v2 layout, send/stop controls, Saira Regular typography, and
  invisible transcript blur lens. Focused UI verification passed with 22 tests.
- Cloud fallback behavior changed on 2026-09-16: after manual testing showed Cloud mode switching
  back to Local on every cloud-unavailable response, development `config/cloud.json` now sets
  `fallback_to_local` to `false`. Cloud-mode failures should remain visible as cloud errors and
  leave the selected mode on Cloud instead of silently answering through Local and changing the
  selector.
- Cloud-unavailable reporting was tightened on 2026-09-16: both agent/tool and chat-only runtime
  paths now preserve the controlled provider failure detail instead of replacing it with only the
  generic selected-provider message. Focused verification passed with 49 agent/cloud tests.
- Cloud provider direction recorded on 2026-09-16: the current backend is OpenAI-compatible provider
  support, not OpenRouter-specific support. The next cloud-side step is provider profiles for
  multiple OpenAI-compatible APIs before native non-OpenAI adapter families. No version bump: this
  remains `v0.4.0-dev` until a packaged/release milestone is explicitly approved.
- Post-acceptance deterministic verification: resolver suite 27 passed; acceptance gate 79 passed; full suite 535 passed, 17 skipped.
- Complete deterministic suite after Phase 9 search: 485 passed, 17 skipped on Windows on
  2026-09-13. The suite collected 502 tests; opt-in live gates remain skipped unless explicitly
  enabled.
- Complete deterministic suite after Phase 9.5 active-context resolver fix: 520 passed, 17 skipped
  on Windows on 2026-09-13. The suite collected 537 tests; opt-in live gates remain skipped unless
  explicitly enabled.
- Opt-in live gates run separately on 2026-09-13: the dedicated `filesystem.read_text` real-model
  call/no-call matrix passed, and the `filesystem.search` real-model call/no-call matrix passed.
- Previous integrated Phase 10 suite after trash: 459 passed, 14 skipped on Windows on 2026-09-13.
- The 161 Phase 10 cases cover actual native folder creation, exact approval, denial, expiry, cancellation,
  collisions, changed parents, protected/reparse paths, read/write isolation, unknown outcomes,
  result-save failure, restart recovery, exact text-write previews, create/replace behavior, target
  replacement after approval, exact copy previews, collision policy, source/destination changes after
  approval, exact move previews, source removal, exact trash previews, plain-delete aliasing to
  Recycle Bin, target changes after approval, permanent-delete wording rejection, hostile
  read-content isolation, and real Qt worker/dialog interactions.
- Folder approval-dialog screenshot inspected with actual Windows fonts; path and controls are readable.
- Historical Phase 9 suite after enablement: 298 passed, 14 skipped.
- Deterministic tests cover list-to-read actual content, direct-path reads, literal Markdown fences,
  untrusted-content isolation, strict decoding/bounds, permissions, cancellation, and disclosures.
- Search deterministic tests cover schema strictness, literal matching, stable ordering, depth/file/
  entry/match bounds, denied paths, missing and non-directory failures, cancellation, full-local host
  paths, prompt contract, cloud disclosure, ordinary no-call conversation, deterministic direct search
  routing, and hostile snippet isolation.
- Target-resolver deterministic tests cover strict exact-name lookup, type filtering, extension
  preservation, entry bounds, denied paths, cancellation, full-local host paths, prompt contract,
  cloud disclosure, Desktop/Downloads alias routing, ordinary no-call conversation, content-search
  separation, location-phrase trimming, named-folder listing, found-directory follow-ups,
  affirmative follow-ups, and no-match reporting without guessing.
- Planner-loop and filename-disambiguation checkpoints are committed at `54872cc`, `853480e`,
  `b39c7a5`, and `9ea55e2` on the active branch.
- GUI v2 checkpoints are committed from `6967485` through `2fb1363`; focused UI tests were rerun for
  the composer and send-hover fixes through `76167c8`. For the final stylesheet-only hover tweaks at
  `228295d`, `ab8ab75`, `05576da`, and the final asset/style restoration at `2fb1363`,
  `python -m compileall app/ui/main_window.py` passed; the available local Python 3.14 runtimes did
  not have `pytest`, so the focused UI suite was not rerun for those tweaks.
- GUI v2 polish checkpoints `3ec7d0b` and `da7e7d9` were verified on 2026-09-15 with
  `runtime\python\python.exe -m pytest -p no:cacheprovider tests\test_ui.py`: 22 passed. The full
  deterministic suite was rerun with a sandbox-accessible pytest temp directory:
  `runtime\python\python.exe -m pytest -p no:cacheprovider --basetemp=.codex-tmp-full-gui-polish-20260915`:
  528 passed, 17 skipped. Rendered previews were inspected during the session for composer scale,
  placeholder contrast, invisible transcript blur, blur feathering, smooth blur quality, and
  user-bubble density.
- Manual Phase 9 workflow acceptance: user confirmed the enabled app works on 2026-09-12.
- Manual Phase 10 text-write application acceptance: user reported it works on 2026-09-12.
- Manual Phase 10 copy application acceptance: user reported it works on 2026-09-12.
- Manual Phase 10 move application acceptance: user reported it works on 2026-09-12.
- Manual Phase 10 trash application acceptance: user reported it works on 2026-09-13.
- Manual Phase 9 search application acceptance: user reported it works on 2026-09-13.
- Manual Phase 9.5 resolver/planner application acceptance: user reported all five `ORSI_TEST`
  workflows green on 2026-09-16.
- Folder create/cancel manual acceptance if not already tested and real-model follow-up conversation
  after writes remain pending.
- Historical GUI baseline visual checks passed at 1920-pixel and 1280-pixel window widths.

## Known follow-up work

- In-progress inference cancellation is not yet immediate for every backend.
- Malformed conversation JSON still needs a preserve-and-recover path.
- Conversation state is persisted during the active run but is not replayed visually; each new
  application launch currently starts a fresh private session.
- Phase 9 search is manually accepted for Phase 11 planning. Fresh-runtime packaging and release
  promotion remain separate gates.
- Phase 9.5 target resolver, planner-loop follow-ups, bounded filename disambiguation, and the five
  accepted manual resolver workflows are implemented on `codex/phase-9-target-resolver`.
- Fresh-runtime packaging and real-model/UI acceptance remain before portable release promotion.
- Phase 10 is a development-only feature-branch checkpoint. Trash preview/approve/cancel workflows
  were manually accepted before the next roadmap decision. See `phase10-mkdir-threat-review.md`,
  `phase10-write-text-threat-review.md`, `phase10-copy-threat-review.md`,
  `phase10-move-threat-review.md`, and `phase10-trash-threat-review.md` for protection scope and
  recovery limitations, including nonstandard application/service locations.
- Phase 9 search is a development-only feature-branch checkpoint on top of the accepted local Phase
  10 line. It is manually app-accepted but not merged or release-promoted. See
  `phase9-search-threat-review.md` for protection scope.
- Phase 9.5 target resolver, planner-loop repair, bounded filename disambiguation, and GUI v2 are
  development-only checkpoints on `codex/phase-9-target-resolver`. The branch is published to GitHub
  with upstream tracking. Manual resolver/planner full-workflow app acceptance is complete; fresh-runtime
  packaging remains before merge or release promotion. See `phase9-target-resolver-threat-review.md`
  for protection scope.

## Checkpoint scope

- The active checkpoint branch is `codex/phase-9-target-resolver`. The Phase 10 folder-creation
  checkpoint is committed at `076007f`; text writing at `6a8fcbb`; copy at `9376a7e`; move at
  `e1595bc`; trash at `e5a6092`; Phase 9 search at `a08aa32`; target resolver at `456376d` with
  follow-up fixes through `4e339be`; planner-loop repair through `54872cc` and `853480e`; bounded
  filename disambiguation through `b39c7a5` and `9ea55e2`; GUI v2 through `da7e7d9`; accepted
  resolver-workflow hardening is recorded in the current checkpoint.
- The private Desktop `statusreport.md`, `roadmap.md`, and `versioning.md` remain outside Git but
  have been updated for the same checkpoint state.
