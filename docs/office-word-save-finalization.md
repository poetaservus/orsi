# Word save finalization, 18 October 2026

Bounded branch `codex/word-save-finalization` starts from clean local main
`fdba4a1`. The user authorizes a Word-only fix and essential tests only.

## Evidence and scope

The reported screenshot records four applied Word edits followed by an
`office.save` INVALID_ARGUMENTS rejection and a semantic-correction stop.
It does not contain the rejected arguments or establish a successful final
save. The exact historical argument failure remains unknown; encrypted user
history was not decrypted and the user's document was not opened or changed.

There is a reproducible contract mismatch: the shared save schema advertises a
boolean overwrite choice, but overwrite=true without a destination fails host
validation. Word also refuses replacing an existing Save As destination, even
with overwrite=true. Saving the attached existing file instead requires no
explicit destination. Excel's existing Save As/overwrite contract is different.

## Bounded correction

The trusted Office selection now retains its application kind and clears it on
connection invalidation. For a selected Word document, including a mixed-app
installation, the model receives a narrower save definition with overwrite=false
as the only explicit choice. Word-only exposure receives it before attachment
as well. Guidance distinguishes path=null for saving in place from a new
absolute .docx destination for Save As. Unknown/mixed unselected exposure and
selected Excel retain their original definitions.

The accepted MCP server schema and host arguments remain unchanged for historical
compatibility. Identity checks, exact approval, Save As conflicts and uncertain
write handling remain authoritative. No arguments are silently repaired, no
edit is replayed, and no automatic save or completion inference is introduced.
Word validation errors now explain the failed field/rule and the correct save
shape, without echoing supplied values or unknown field names. Shared retry
limits, core prompts, acceptance prompts, profiles and routing are unchanged.

Historical Word save attempts retain their broader schema only during Responses
history projection. Both neutral history and original provider evidence remain
replayable, without allowing overwrite=true in new Word provider calls. Original
native evidence remains byte-for-byte; replay never executes a save.

Budget verification includes the actual selected-Word projection in both mixed
and Word-only catalogs. The largest is 22,420 bytes / 7,954 reserve tokens,
within the unchanged 22,500 / 8,100 ceilings. The accepted manifest is unchanged.

## Essential verification

Final focused selection: **191 passed, zero failures/errors/skips**, in 16.283
seconds, with normal Windows process permissions and repository-local basetemp.
It covers Word save choices and strict provider decoding, Excel invariance,
historical replay, Office contracts, Word preservation/unknown outcomes, read
renewal and Responses tool boundaries. Two owned SDK/stdio/runtime regressions
perform four approved synthetic Word edits, then save and finish: directly,
and after correcting a rejected save. Both retain four edits and exactly one
dispatched save, and release owned bridge workers/scratch. No shared correction
limit is changed. Compilation, whitespace and manifest/budget checks pass.

The initial restricted-shell bridge attempt stalled at worker startup/shutdown;
the normal-permission rerun passed those boundaries. Initial new fixture failures
used a protected application path, then omitted creation of its isolated
application directory. Those fixture setup errors were corrected without changing
production write policy. History tests initially exposed rejection of older save
calls by the narrower schema; the history-only compatibility correction resolves
both neutral and native-evidence cases.

No full suite, paid model request, real Word COM gate or editorial acceptance run
was performed. Synthetic bridge tests are not relabeled native Word or live model
qualification. This fixes the demonstrated contract ambiguity; it does not prove
that the unavailable historical arguments used that specific invalid choice, or
that unrelated provider-final-response failures are resolved.

Pre-change refs/worktrees and a verified complete-history bundle are retained in
ignored `state/backups/word-save-finalization-20261018/`. Final test evidence is
`state/word-save-essential.xml`; budget evidence is `state/word-save-contract.json`.
Preserve prior main under `archive/2026-10-18/main-before-word-save-finalization`,
commit, fast-forward local main and remove only the merged feature branch per
AGENTS.md. No remote operation, other-worktree change or user-setting change.
