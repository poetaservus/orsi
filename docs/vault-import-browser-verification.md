# Clear file, folder and previous-installation imports

Bounded follow-up from local main `0181919`, on `codex/vault-import-browser`.

The old migration dialog's two unlabeled paths represented a source application
and a personal skills folder. They did not provide general host-document imports.
The Data page now starts with Import files and Import folder, explains that copies
go into the current vault, and states that originals remain unchanged. Files use
the native multiple-selection browser. Folder selection includes subfolders and
retains their relative paths. Both use the existing verified encrypted import
and receipt mechanisms; unique destinations preserve existing copies and files
with the same name. Empty folder selection reports no importable files.

The previous-installation action is separate and clearly named. Its source path
has a visible label and Browse button, starts empty, and explains what it imports.
The labeled skills folder appears only when personal skills are selected. The
Import selected data action requires a category and the relevant source selection.
No matching legacy data is reported explicitly rather than creating an empty receipt.

## Focused verification

**19 native Windows pytest cases passed**, without failures or skips in the final
report `state/vault-import-browser-final.xml`. Coverage includes local and portable
profiles, nested arbitrary folder copies, same-named selected files, source-change
rejection before publication, missing/empty/shared sources, cancellation, actual
UI action-to-vault integration, refreshed records, visible labels, both legacy
folder browsers, conditional skills controls, previous migration/conflict/failure
behavior and stable Settings geometry across window modes.

The first run's two new UI checks invoked hidden Data actions while the synthetic
window was still on Storage. Their setup now opens Data before testing preservation
of the selected tab. The final focused group passed; no product logic was changed
to accommodate that setup error.

A synthetic portable-profile preview checked normal 1280 × 800 and minimum
760 × 600 layouts without horizontal clipping. Both Data captures and the
previous-installation dialog were visually inspected. Captures are under ignored
`state/vault-import-browser-preview/aeaadb7748ce460c91f85f28b7eea62c/`.

Syntax and whitespace checks passed. Ten configuration/artwork fingerprints and
other worktree tips were preserved. Recovery evidence is under ignored
`state/backups/vault-import-browser-20261010/`; prior main is retained at
`archive/2026-10-10/main-before-vault-import-browser`.

No full 2000+ suite, live provider/model calls, actual user-vault access or user
process termination. Physical SSD, minimum-machine performance and independent
security qualification remain deferred.
