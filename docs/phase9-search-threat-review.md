# Phase 9: bounded filesystem search

Date: 2026-09-13
Status: development checkpoint implemented and tested; manual application acceptance pending.

## Scope And Authority

- One explicit local directory path under the active read scope.
- One literal text query copied from the user request.
- Read-only search of UTF text snippets. It does not build an index, infer a background inventory,
  search without a requested directory, mutate files, launch programs, use the shell, or grant write
  authority.
- Separate feature gate: `filesystem_search_enabled` / `ORSI_ENABLE_FILESYSTEM_SEARCH`. Missing
  configuration defaults it off, and enabling search still requires the filesystem metadata agent.

## Search Boundary

- Defaults: depth 3, 256 regular files, 16,384 bytes per file, 25 returned matches, and 160-character
  snippets.
- Hard limits: depth 8, 1,024 regular files, 4,096 directory entries, 65,536 bytes per file, 100
  returned matches, and 300-character snippets.
- The capability uses the existing host-access path policy for portable-root and acknowledged
  full-local reads. Network and device namespace paths remain denied.
- Directory traversal is deterministic and sorted. Symlink and reparse entries are skipped.
- Non-UTF, binary, inaccessible, and transient files are skipped without returning their contents.
- Returned filenames and snippets are untrusted data and cannot select capabilities, approve writes,
  or execute instructions.

## Failure And Recovery

- Missing directories, non-directory targets, invalid arguments, denied paths, cancellation, and bound
  overflows return normalized failures.
- If the entry or file bound is exceeded, the call fails closed instead of pretending to have searched
  everything.
- If the match bound is reached, the result reports truncation and returns only the bounded matches.
- Search has no durable side effect and no replay behavior beyond the existing read-only journal
  records.

## Verification And Remaining Limits

- Full deterministic suite after search: 485 passed, 17 skipped on Windows on 2026-09-13.
- New search coverage: 18 focused capability tests and 8 integration tests covering schema
  strictness, literal matching, ordering, bounds, denied paths, missing/non-directory failures,
  cancellation, full-local host paths, prompt contract, disclosures, ordinary no-call conversation,
  deterministic direct routing, and hostile snippet isolation.
- Opt-in live gates passed separately on 2026-09-13: dedicated `filesystem.read_text` real-model
  call/no-call matrix and `filesystem.search` real-model call/no-call matrix.
- Manual application acceptance for search remains pending. Fresh packaging and broader release
  promotion remain separate gates.
