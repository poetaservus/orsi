# Scoped coding guidance, 9 October 2026

Phase 3 aligns the full and compact coding prompts with the supported file tools.
The compact prompt no longer stops after one successful edit while requested work
remains. Both prompts permit the finite changes needed for the latest explicit
task, limit discovery to its scope, then stop and report settled results.

The only product change is `app/conversation/prompt.py`. Exact existing-file edits
use current source before each mutation, including supported larger reads when the
target is truncated. Deliberate complete generation/replacement requires task
authorization and the existing runtime approval. Requested versioned copies use
explicit destinations, preserve originals, and identify the changed versions.
Failed exact matching does not authorize overwriting originals or unsolicited copies.

Verification guidance distinguishes inspected source and saved bytes from Python
execution, imports, GUI behavior and test results. The final answer identifies
changed files, completed/remaining work, performed checks and unrun checks. The
file-change guidance is conditional on advertised edit, write or copy capabilities;
read-only catalogs do not gain file-change authority.

## Boundaries and prerequisite

Routing, source-read contracts/limits, execution permissions, approvals, tool
catalogs, model selection/sampling, context policies, loop/correction budgets and
installed skills are unchanged. Both normal local/cloud request paths retain the
complete enabled catalog. For the 12-tool catalog, the full core is 17,710 UTF-8
bytes and compact core 5,665 bytes; the compact core stays below half the full core.

The initial guidance branch started from independently verified main `8462cdb`.
Its first full deterministic run passed 2,616 tests and 15 subtests, with 58
optional/host skips, in 340.44 seconds. However, all four initial cloud acceptance
cases failed report qualification: requested saved bytes were correct and the
models' reports disclosed unrun checks, but ORSI replaced those reports with the
last supporting file read. That failed gate remains in ignored `state/phase3-cloud/`.

The guidance tip `9e0b902` was preserved at
`archive/2026-10-09/guidance-before-report-fix`. The separate reporting prerequisite
was implemented from main with these guidance changes absent, independently
qualified, and integrated as `32dc9a9`; see [its record](file-task-reports.md).
The guidance branch was then rebased onto that verified baseline. Its original
three-file implementation and acceptance prompts remained byte-equivalent after
line-ending normalization. No prompt or acceptance assertion was adjusted to repair
the failed report publication.

## Verification

Twenty-five new checks cover both prompt forms and read scopes, copy/replacement
authority, honest verification, read-only catalogs, actual local/cloud outgoing
requests and content-free acceptance report classification. Existing acceptance
prompts and runtime guard assertions remain unchanged.

Final focused native checks passed **158 tests**, with one host symbolic-link skip,
no failures/errors, in **32.30 seconds**. They cover the guidance and report
regressions, actual service requests, conversation/turn handling, approved native
edits and skill reference loading. Final full unrestricted Windows regression
passed **2,638 tests and 15 subtests**, with **58 optional/host skips**, no
failures/errors, in **341.98 seconds**. Reports are ignored
`state/phase3-focused-final.xml` and `state/phase3-full-final.xml`.
The skipped local-model, provider, UI/lifecycle and host symbolic-link gates are
recorded separately from these passed checks and the completed cloud gate.

The opt-in cloud gate uses synthetic source and screenshots in four isolated
workflows: two requested existing-file fixes or two explicitly requested copies,
each with and without the unchanged installed Python skill. Its 453-line,
23,631-byte main fixture exercises a target at line 330, alongside a second
helper file. It checks exact saved bytes, grounded edits, original preservation,
finite approved mutations, named changed versions and honest unrun-check reports.
Read access and mutation approvals stay within those fixtures; execution is denied.

All four frozen cloud cases passed on the default `gpt-6-luna` backend. Existing
fixes made two approved exact edits each; copy tasks made four approved mutations
each and preserved both originals. Total settled calls were 7/10 without the
skill and 8/13 with it. Each case delivered both requested exact saved files,
identified the changed versions, disclosed unrun Python/GUI checks, used the
complete 12-tool catalog, generated no images, and had no tool failures or semantic
corrections. Every transport was released. The installed skill retained SHA-256
`ab4643c14f92c4c176a11f3f6f6bb8767b9c16515f168b60422970a4e6aa23b2`.
An independent persistence audit confirmed all four user-visible answers equal
their corresponding raw model completion reports.

The final cloud summary is ignored `state/phase3-cloud-final/summary.json`.
Numeric/fixed-category summaries remain under ignored `state/`; baseline preservation records contain
paths, sizes and hashes, without keys, conversations, source or patch contents.
Compilation, dependencies and whitespace are checked separately. Python/GUI
execution by ORSI and real local-model qualification remain unrun live gates.

## Integration

Pre-integration refs/worktree maps, a verified complete-history bundle containing
the original unmerged guidance tip, and settings/configuration preservation hashes
are saved under ignored `state/backups/scoped-coding-guidance-final-20261009/`.
Preserve prior main at `archive/2026-10-09/main-before-scoped-coding-guidance`, commit
after verification, fast-forward local main and the requested active checkout
without switching its settings branch, and remove only the merged guidance branch.
Other worktrees, remote refs, user settings edits and the archived earlier tip stay
intact. Restart ORSI to load the changes. Phases 4–6 remain separate work.
