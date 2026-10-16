# Office read recovery, 17 October 2026

The reported technical-document run applied two Word edits and then stopped at
the identical-call guard. Its generic `office.read` error does not identify the
failed target or underlying exception. That historical cause remains unknown.

Investigation reproduced a separate concrete defect: identical Office reads
were counted across the whole turn, including across verified document edits.
The filesystem progress trackers already renew reads after settled changes;
Office reads had no equivalent. The error bridge also collapsed unexpected
read exceptions into `invalid_arguments`, and profile logging discarded the
structural diagnostics emitted by the composition pipeline.

## Bounded correction

- Renew successful initial Office reads only after a matching session's settled,
  operation-bound `applied` edit receipt with a positive affected count. Saves,
  unchanged edits, failures, denied writes, other sessions and cursor replays do
  not renew attempts. Unsupported failed reads earn no renewed allowance.
- Compare complete composition readback with the prior owned snapshot. A
  semantically identical composition reports `unchanged`, so it cannot create
  artificial progress. Native verification and exact approval remain required.
- Categorize read failures by fixed target kind, stage and reason, plus bounded
  read limits, numeric coordinates and optional numeric HRESULT. Unexpected
  execution/result failures are `invalid_output`; unsupported targets remain
  correctable `invalid_arguments`. Render/conflict feedback retains its behavior.
- Include authoring/layout/render targets in recovery feedback and identify the
  blocked read category when the unchanged repetition guard stops execution.
- Persist explicitly allowlisted read and composition structure in the bounded
  profile diagnostic store. Never format or persist raw logging messages,
  exception text, paths, session identifiers, document text or credentials.

No advertised schema, acceptance prompt, model profile, sampling, routing,
approval binding, recovery authority or retry limit changes. No document edits.

## Essential verification only

95 focused checks passed in the unrestricted Windows shell:

- 91 checks in `test_office_read_recovery.py`, `test_office_read_diagnostics.py`,
  `test_office_mcp_word.py`, `test_office_word_actions.py`, and the existing
  identical-call/duplicate-batch runtime guard tests.
- Two additional real-bridge read-feedback/correction versus identical-invalid
  retry checks, added after that selection passed.
- Two profile-storage variants of the new diagnostic persistence/privacy check.

All runs used repository-local `--basetemp` directories. The owned production
SDK/stdio/STA/permission/executor path verified read/edit/read/edit/read,
unchanged read stops, native HRESULT and unsupported-target feedback, corrected
reads, recovery, and worker release. These use synthetic Word state and scripted
model responses: they do not establish live model generation or native Word
rendering of the user's technical-document request. Those live gates were not
run. No full repository suite was run; no environment failures occurred in this
selection. `git diff --check` passed.

Recovery refs/worktree inventories and a verified complete-history bundle are
under ignored `state/backups/office-read-recovery-20261017/`. Preserve prior main
at `archive/2026-10-17/main-before-office-read-recovery`, commit this bounded
change, fast-forward local main, and remove only its merged feature branch.
Other worktrees, historical tips, remote refs and private settings are preserved.
