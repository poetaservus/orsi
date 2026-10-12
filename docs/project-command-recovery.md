# Windows project command recovery

The reported turn stopped at the semantic-correction limit after rejecting
`project.verify` arguments, without recording a successful edit. On unchanged
main `053fbb6`, the installed absolute `npm.cmd` path and the bare `npm` and
`npm.cmd` commands all reproduce the executable validation failure. The exact
commands submitted in the reported turn were not available from the screenshot.

`codex/project-command-recovery` makes the project build and preview tools accept
installed Windows npm launchers. They resolve npm to its actual `node.exe` and
`npm-cli.js`, passing each argument separately. They do not execute the batch
wrapper. Approval displays the resolved command and binds the launcher, Node,
CLI file identities and arguments; changed installation files or PATH resolution
invalidate the approval. Other executables keep their existing absolute-path
requirements. Unsupported commands receive concrete npm or advertised
`shell.run` recovery guidance.

The correction and repeated-call limits remain unchanged, as do model profiles,
sampling, routing, context policy and application prompts. No website source or
user settings were changed. Restart the running application to load the updated
capabilities and tool descriptions.

## Necessary qualification

- The initial 17 new checks passed, including real installed npm execution and a
  temporary browser preview whose owned processes were released.
- The final affected regression group passed all 140 checks, with no failures,
  errors or skips, in 39.713 seconds. It covers command recovery, project
  verification, verification workflow, edit-aware rechecks, provider tool
  serialization and shell sessions. The initial 17 checks are included in 140.
- The unchanged request `can you re-enable the animation in app.tsx` completed
  against a synthetic project with a scripted model, after one rejected shell
  command, an approved edit and a real npm build. This verifies the runtime
  recovery path, rather than live model behavior.
- Approval denial and installation/PATH tampering prevented execution. A real
  npm preview was inspected in Chromium and its server process was released.
- Python compilation and whitespace checks passed.

Reports use repository-local temporary/cache directories and are saved at
`state/project-command-initial.xml` and `state/project-command-focused.xml`.
Windows process qualification used an unrestricted shell. Full-suite and live
model/provider gates were not run, following the request for necessary tests
only; they are not counted as passed.

Content-free refs/worktree records are preserved under
`state/backups/project-command-recovery-20261012/`. Prior main is preserved at
`archive/2026-10-12/main-before-project-command-recovery`. Integrate the verified
commit by fast-forwarding local main and remove only its merged feature branch.
Other worktrees, historical/unmerged tips and remote refs remain untouched.
