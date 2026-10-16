# Word composition schema and validation diagnostics

The reported stop occurred after repeated `office.word_compose` calls were
rejected by capability argument validation, before native Word dispatch. The
screenshot contains the entire exposed error but no submitted arguments or
field details. The exact field that triggered that particular run cannot be
reconstructed from it. Personal chat history remains encrypted; this change
does not access profile keys or unlock history.

Two independently reproducible contract defects made recovery unnecessarily
difficult: several composition constraints were checked only in model
validators, and the visible error discarded the validation details. Nested
paragraph/table/page-break alternatives also produced irrelevant failures from
other block types before the useful error.

## Change

Composition text, table cells and running matter now advertise their existing
control-character restriction as a schema pattern. Column widths and margins
advertise their existing numeric bounds. Table dimensions reflect the existing
256-cell limit. The tool description explains separate paragraphs, rectangular
tables, one width per column, printable-width totals and header/footer distances.
The existing 512-character running-matter bound is preserved.

The capability still refuses invalid calls before resource preparation, approval
or Word execution. Its visible failure now names up to three useful field paths
and constraints, for example `blocks.0.text` or `blocks.0.widths_mm.0`, and states
that no Word write was dispatched. It filters irrelevant union alternatives
according to the submitted block kind. Unknown field names and submitted text
are omitted from the visible message; constraint messages are allowlisted and
the message remains bounded at 500 characters. Structured details remain bounded.

The accepted Office manifest is regenerated. The catalog remains nine tools,
19,903 bytes and 7,067 offline reserve tokens, within the existing 20,000-byte /
7,200-token budget. The original acceptance prompt, model profiles, context
limits, core prompts, routing, sampling, approvals, snapshots, owned restoration
and identical-call stop limit retain their policies. Other Office actions retain
their validation diagnostics.

## Qualification

The final focused selection passed **219 tests** in **29.33 seconds**. Twenty
new cases exercise full three-page report arguments through the strict provider
schema, nullable default normalization, capability validation and transcript
replay; malformed content/geometry; sensitive-value suppression; correct union
branch diagnostics; corrected calls through the actual agent loop and explicit
approval; and unchanged stopping of identical rejected calls. These are scripted
provider cases, not real model generation.

The native Word gate passed in **84.35 seconds**. It created and saved an
isolated synthetic three-page report with real paragraphs, heading styles and
an editable table, then exercised stale/denied writes, owned restoration,
page rendering, page fields and reopen. All three page images were inspected.
The owned Word process, bridge worker and private export directory were released;
forced fixture termination was not required. The user's Desktop report was not
modified.

The unchanged read-after-mutation module passed all **20 tests** in **4.18
seconds** using a short repository-local temporary path. An initial run with a
longer fixture path reached the small scripted cloud model's context limit in
one existing case; it is retained separately, with no production context-limit
or fixture-assertion change. Initial new-test fixture errors (missing synthetic
connection cleanup and attempting an unapproved write) were corrected to use
explicit ASK approval. An initial sandboxed broad selection was interrupted;
the unrestricted focused selection above is the qualification result.

The unrestricted full suite recorded **4,233 passed, 53 failed, 99 skipped**,
**15 passing subtests** and two warnings in **1,374.33 seconds**. Fifty failing
test IDs exactly match the original baseline: 47 language/Hungarian checks,
one login-font fixture and two settings-dropdown checks. The additional failures
were two unchanged shell-session tests whose one-second startup/lifetime fixtures
did not produce their readiness file, and an unchanged reference-reader depth
test denied a directory rename with WinError 5. The prior Word qualification's
additional discovery-rename failure did not recur in this full run.

An unrestricted recheck of both additional failing modules recorded **89 passed,
2 failed, 1 skipped** in **15.84 seconds**. The shell lifetime/readiness-file
failure and reference-reader rename denial persisted; their causes remain
unresolved. The shell server-retention case passed recheck. These modules and
their implementations are outside this Word change and were not edited. The
full run and recheck are not claimed clean; no extra passing gate is inferred
from a skipped check.

Opt-in provider gates remain separate from deterministic checks and native Word
qualification. No real provider requests or API credentials were used.
Compilation, dependency consistency, accepted manifest/budget verification and
whitespace checks pass.

Evidence is retained in the isolated checkout's ignored
`state/word-compose-validation/`. Pre-change pending-file hashes, workflow backup,
refs/worktree inventory and complete-history recovery bundle are retained under
the active checkout's `state/backups/word-compose-validation-20261016/`.
