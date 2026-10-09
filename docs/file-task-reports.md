# Preserve file-task reports, 9 October 2026

This independently bounded prerequisite was found while qualifying Phase 3 coding
guidance. Four synthetic two-file fix/copy workflows saved the requested bytes,
and the models disclosed unrun execution checks. However, ORSI replaced every final
report with the last read of helpers.py. The direct-read answer renderer mistook
the request's supporting "read ... verify it" instruction for a request to display
the file. Completion, original/copy identity and verification information disappeared.

The guidance work was preserved on its unmerged branch and at
`archive/2026-10-09/guidance-before-report-fix`. This reporting change starts separately
from verified local main `8462cdb` on `codex/preserve-file-task-reports`, with the
Phase 3 prompt changes absent. Its only product change is in
`app/conversation/result_grounding.py`.

## Behavior

A settled file mutation or failed mutation attempt identifies a file-change task
for answer presentation. Its supporting text reads no longer replace the model's
completion/failure report. This does not infer mutation success or create a new report;
the original result-based answer remains intact. The evidence is limited to the
current turn, so earlier writes do not disable later direct reads.

If the user explicitly requests display of saved content, the renderer still supplies
the actual returned text, appending it to the report instead of discarding the report.
Already included source is not duplicated. Ordinary direct content reads retain their
existing exact-text rendering, syntax fences, truncation notices and false-restriction
correction. Source content remains untrusted data.

Prompts, tool contracts, routing, approvals, model/context/sampling policies, loop
budgets, cancellation and journal ownership are outside this change. User files,
installed skills, preferences and accepted configurations are preserved.

## Verification

The final pre-fix deterministic reproduction recorded **13 expected failures and
four passes** in **1.85 seconds**. It includes a native edit/read/report workflow;
the final answer lost the report even though the requested bytes were saved.
All these regression expectations remain intact. Explicit-display forms and
change/check summaries bring the new regression group to 22 cases.

Final focused unrestricted Windows checks passed **89 tests and five subtests**,
with no failures/errors or skips, in **13.50 seconds**. They cover successful and
failed file-operation reports, retained explicit content displays, ordinary reads,
native result persistence, UI rendering and existing settled-turn behavior. The
first focused attempt exposed a missing saved-text display case, corrected without
changing its expected behavior; its one failure remains in the initial report.

The first full unrestricted regression passed **2,610 tests and 15 subtests**, with
**58 optional/host skips**, in **339.65 seconds**. The subsequent explicit-display
narrowing and three summary regressions require the final full run recorded below.
That run recorded 2,612 passes, 58 skips, and one existing Git-installer cleanup
failure with a related teardown error in 337.57 seconds. The complete 60-test
installer group then passed unchanged in an unrestricted recheck. No installer
code or expectation was changed; the failure record is retained separately.
Final complete unrestricted regression passed **2,613 tests and 15 subtests**,
with **58 optional/host skips**, no failures/errors, in **350.04 seconds**.
The unchanged installer recheck passed 60 tests in 16.92 seconds. Final reports
are ignored `state/file-task-reports-full-recheck.xml` and
`state/file-task-reports-git-recheck.xml`; optional live gates remain skipped.

The unchanged original cloud fix/copy gate passed all four cases, with and without
the unchanged Python skill, using the original main prompts. All four published
answers equal the models' final reports. Existing fixes and requested copies retained
their exact saved bytes, originals stayed intact where requested, coding screenshots
generated no images, and a genuine historical image was generated. Every transport
was released. The content-free summary is ignored `state/file-task-reports-cloud/`.

Reports and the frozen pre-fix reproduction are under ignored `state/`. Compilation,
dependencies and whitespace checks passed. Python/GUI execution and other optional
live gates remain separate from passed deterministic/cloud checks.

## Integration

Pre-integration refs/worktree maps, a verified complete-history bundle containing the
unmerged guidance tip, and content-free settings/configuration hashes are preserved
under ignored `state/backups/file-task-reports-20261009/`. Preserve prior main at
`archive/2026-10-09/main-before-file-task-reports`, commit after verification, fast-forward
local main and the requested active checkout without switching its settings branch,
and remove only the merged reporting branch. Other worktrees and remote refs remain
unchanged. Resume the preserved Phase 3 guidance only after this independent checkpoint.
