# General shell access

O.R.S.I can now run general project commands through `shell.run`, in addition to
the existing build/test and browser inspection tools. PowerShell is the default;
cmd is available for batch files and Windows command syntax. Commands support
pipes, redirects, multiline PowerShell programs and installed tools such as Git,
Node and npm. This is a noninteractive command runner, with a fresh shell per
call. It does not provide a persistent terminal or stdin interaction.

Each call specifies an exact command, an existing absolute working directory,
shell and deadline. The command limit is 8,000 UTF-16 code units; cmd programs
must occupy one line, or invoke an existing batch file. The default deadline is
60 seconds, with a maximum of 300. The working directory must resolve inside the
configured read scope and below a drive root. It selects the starting folder;
commands still have the Windows account's file and network access. This is not
an OS sandbox, and O.R.S.I does not automatically elevate privileges.

## Approval and results

The existing execute permission gate asks for approval of each exact call. The
inline review displays the command, shell executable, working directory and
deadline. Approval binds the arguments, directory identity and shell file
identity. Changing a command, directory, interpreter or timeout requires a fresh
authorization. Directory timestamps may change as project commands generate
outputs. Denials, cancellation, call replay protection and unknown-outcome
handling retain their existing behavior. The existing Tool Approval setting is
preserved: when review is off, the runtime automatically authorizes each exact
call through the same permission gate; it does not grant a reusable shell session.

The system interpreter is selected directly rather than through a project-local
PATH lookup. PowerShell runs without profiles, with closed stdin and text UTF-8
output. Terminating PowerShell errors and failing native commands return nonzero
status. cmd keeps its own quoting rules so quoted batch paths, pipes and redirects
are not rewritten as CRT arguments. Environment inheritance uses the existing
allowlist, excluding provider keys and arbitrary host hooks. Account-accessible
files remain accessible to approved commands.

Results include merged stdout/stderr, exit code, elapsed time, whether the command
completed and succeeded, truncation and stop reason, and owned-process release.
Output is untrusted data. The raw output limit is 64 KiB; an overrun stops the
command. Additional truncation keeps JSON within the executor's result envelope
while preserving exit and cleanup metadata. Atomic Windows job ownership retains
the existing 16-process and 1-GiB limits. Normal exit, timeout, output overrun and
cancellation stop all owned descendants, while unrelated processes remain alive.
Temporary preview servers should continue to use `project.inspect`'s owned server.

A successful shell call proves only that command. It does not create a passing
build/test or UI receipt, or enumerate saved file revisions. Since general shell
commands can modify files outside their working directory, an executed or possibly
executed call conservatively invalidates earlier source and project verification
evidence. Run `project.verify` and `project.inspect` after the last general shell
command when those scoped checks are needed. Interrupted-task reports retain
shell results and avoid claiming that no files changed.

## Configuration and qualification

The capability is fail-closed in `AgentFeatureConfig` and enabled in the shipped
`config/agent.json` through `shell_run_enabled`. `ORSI_ENABLE_SHELL_RUN` overrides
the flag. The structured filesystem agent is a prerequisite. Both local and cloud
tool catalogs advertise the same capability; model profiles, sampling and context
policy are unchanged. Restart O.R.S.I to load the new catalog.

Focused qualification covers real PowerShell/cmd execution, Unicode, quotes,
pipelines, batch files, cwd, native/PowerShell errors, stdin and environment,
approval changes, denial, directory/executable replacement, output limits,
timeouts, cancellation, descendant cleanup, unrelated-process preservation,
inline review, conversation execution and durable recall. Existing command,
verification, approval preference, provider schema and catalog budget checks are
included. Git, npm and Node version commands also pass in Desktop/orsi_website
through both shells, retaining content-free outcomes only.
Qualification passed 206 distinct focused checks, with no skipped native checks.

Six existing `test_stable_tool_catalog` cases also fail on unchanged local main
`2c2e33b`: their scripted model supplies ordinary answer text during the newer
assessment-only completion check. The baseline reproduction is retained separately;
those fixtures and their acceptance prompts are unchanged. The full suite and live
API/model gates are unrun for this bounded shell change, per the request for only
necessary checks. Evidence is under ignored
`state/backups/general-shell-access-20261011/`.
