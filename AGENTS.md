# Working baseline

- `Desktop/orsi_test` is the active checkout. `main` is the verified integration branch.
- Start a bounded change on one `codex/` branch from local `main`. Keep unrelated work out of it.
- Preserve uncommitted user settings before replacing or migrating them. Runtime selection belongs
  under ignored `state/`; accepted model profiles are versioned configuration.
- Do not change prompts, routing, tool behaviour, model sampling and context policy together to
  make a failing acceptance test pass. Keep acceptance prompts unchanged.
- Run the relevant tests, then the existing suite with a repository-local `--basetemp`.
  Windows handle checks may require an unrestricted shell. Do not treat sandbox failures as
  product failures. Record skipped live gates separately from passed deterministic checks.
- For model-profile changes, verify a real switch away and back, actual effective limits, and
  released owned processes. Preserve content-free diagnostics; never record keys or conversation
  and file contents in baseline snapshots.
- After verification, commit the bounded change, fast-forward local `main`, and remove its merged
  feature branch. Preserve historical/unmerged tips before cleanup. Do not alter another active
  worktree or publish/delete remote branches without authorization for that operation.

See `docs/git-workflow.md` for the recovery and branch layout.
