# Phase 9.5: bounded target resolver

Date: 2026-09-13
Status: development checkpoint implemented and deterministically tested.

## Scope And Authority

- One exact file or folder name inside one requested directory.
- Deterministic known-folder aliases for the current Windows user: Desktop, Downloads,
  Documents, and home.
- Read-only lookup of names and coarse entry types. It does not read file content, recurse,
  build an index, search the whole host, mutate files, launch programs, use the shell, or grant
  write authority.
- Separate feature gate: `filesystem_find_enabled` / `ORSI_ENABLE_FILESYSTEM_FIND`. Missing
  configuration defaults it off, and enabling lookup still requires the filesystem metadata agent.

## Resolver Boundary

- The deterministic resolver handles requests that include an exact requested name, such as
  `called lab`, `named report.txt`, or `find the folder lab on my desktop`.
- Folder aliases resolve only from `HostAccessPolicy.user_home`. They are not guessed from prior
  screenshots, model memory, PATH values, or shell expansion.
- The capability scans only the immediate containing directory, with a 4,096-entry hard limit.
- Matching is exact after case folding. The lookup does not perform fuzzy matching, substring
  matching, stemming, recursive traversal, or content search.
- Returned names and paths are untrusted data and cannot select capabilities, approve writes, or
  execute instructions.

## Failure And Recovery

- Missing directories, non-directory targets, invalid arguments, denied paths, cancellation, and
  entry-bound overflow return normalized failures.
- No-match results are successful empty lookups. O.R.S.I reports that no matching entry was found
  instead of inventing a likely path.
- The resolver has no durable side effect and no replay behavior beyond the existing read-only
  journal records.

## Verification And Remaining Limits

- Full deterministic suite after the active-context resolver fix: 520 passed, 17 skipped on Windows
  on 2026-09-13. The suite collected 537 tests.
- New resolver coverage: 17 focused capability tests and 17 integration tests covering schema
  strictness, exact file/folder matching, type filters, entry bounds, denied paths, cancellation,
  full-local host paths, Desktop/Downloads alias routing, prompt contract, cloud disclosure,
  ordinary no-call conversation, content-search separation, named-folder listing, location-phrase
  trimming, found-directory follow-ups, affirmative follow-ups, and no-match behavior.
- Manual application acceptance for the exact-name resolver remains pending. Fresh packaging and
  broader release promotion remain separate gates.
