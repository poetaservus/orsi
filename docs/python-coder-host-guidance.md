# Python Coder host guidance, 9 October 2026

Phase 5 starts from verified local main `9c5a061` on
`codex/python-coder-host-guidance`. The only product change is guidance in the
`python-coder` package, updated from 1.0.0 to 1.0.1. Routing, core prompts, tool
contracts/permissions, runtime limits, model settings and context policy are unchanged.

## Guidance and preservation

The entry point now states ORSI's actual verification boundary: file tools and an
allowlisted Blender launcher are available, while Python, arbitrary shell, imports,
tests and GUI execution are not. Installing Python on the computer does not expose
an interpreter to the agent. The launcher must not substitute for an execution tool.
Source inspection and saved-byte verification are reported separately from unrun
checks. Missing execution alone does not justify speculative follow-up edits.
Hosts with an advertised execution capability can perform permitted checks normally.

The testing, application-delivery and final-review references use the same boundary.
The original task routes, twelve-reference inventory, progressive loading, core
instruction priority, name, description and license are preserved. The picker still
clears message selection after sending; deliberate session selection remains a
separate API behavior. This update changes neither skill activation nor persistence.

Before modification, the entire installed 1.0.0 package was copied and verified under
ignored `state/backups/python-coder-host-guidance-20261009/installed-python-coder-1.0.0/`.
Its metadata, file hashes and original installed path are retained separately. The
prior entry SHA-256 is
`ab4643c14f92c4c176a11f3f6f6bb8767b9c16515f168b60422970a4e6aa23b2`.
A verified Git history bundle, ref/worktree maps and content-free settings/configuration
hashes are retained in the same backup directory. Other installed skills must remain
byte-identical during the native installer update.

## Qualification

The unchanged Phase 3 synthetic two-file fix/copy requests are used before and after
the skill update, both without the skill and with message-scoped selection. The same
453-line source, screenshot, permissions, cloud model and exact-byte expectations
apply. Gates assess delivered behavior, mutations, errors, report truthfulness and
calls; a completed turn alone is insufficient. They verify source and saved files,
not Python or GUI execution through ORSI.

Before the update, all four cloud cases passed. Existing-file cases made exactly two
approved edits; copy cases made four approved mutations and preserved both originals.
There were no failed calls, semantic corrections or generated images, and every report
disclosed unavailable execution. All transports were released. Results are ignored
`state/phase5-cloud-before/summary.json`.

Six actual-package native cases exercise progressive reference excerpts, unchanged
core authority/catalog/permissions/limits, local/cloud scripted modes, message expiry,
session retention, and the real UI picker/worker handoff. The first new harness had
six setup errors from missing synthetic host acknowledgement; subsequent checks exposed
incorrect assumptions about the conversation prompt and a complete default reference
read. These were corrected in the new harness; production policies and old acceptance
assertions were untouched. Prior reports remain separately under ignored state.

Focused native qualification passed **262 tests**, with no skips, failures or
errors, in **45.07 seconds** (`state/phase5-focused-final.xml`). This includes actual
package installation and all twelve reference round trips, executable reference
examples, picker/scope behavior, native reader ownership and the existing routing
regressions (including intentional visual requests and cancellation).

All four candidate cloud cases also passed on unchanged default `gpt-6-luna` with
exact saved bytes, expected mutations/approvals, no errors/corrections/images, honest
unrun-check reports and released transports. The candidate was installed in isolated
storage using the native installer and passed to the unchanged gate by an ignored
registry wrapper (`state/phase5_cloud_candidate.py`); its prompts, fixture bytes,
assertions and application code were unchanged. The global installation is verified
byte-for-byte against that qualified candidate.

| Case | Calls before / after | Model requests before / after |
| --- | --- | --- |
| Existing fixes, no skill | 6 / 6 | 4 / 4 |
| Requested copies, no skill | 10 / 10 | 9 / 6 |
| Existing fixes, skill | 8 / 8 | 7 / 7 |
| Requested copies, skill | 11 / 12 | 7 / 9 |

There was no speculative mutation or execution workaround. The skill-bearing
existing-file case had one redundant unchanged-source read both before and after;
copy cases had none. The updated copy case used two metadata checks instead of the
prior single reference read. This limited sample supports truthful, bounded delivery,
not a claim of improved call efficiency or a causal model-quality ranking. All eight
persisted final reports exactly retained the models' answers. Content-free summaries
are ignored `state/phase5-cloud-before/summary.json`,
`state/phase5-cloud-after/summary.json` and `state/phase5-cloud-comparison.json`.

The skill-creator validator, Python compilation, dependency consistency, link/example
checks and whitespace checks passed. A verified thirteen-file portable archive is
ignored `state/artifacts/python-coder-host-1.0.1.zip`; the older archive is retained.
The candidate entry digest is
`400ef269e7928a7f2c353a0126480fdffbdc20e7c4e5be97a7e22d67126a0820`.
Its entry is 8,612 bytes, twelve references total 56,589 bytes, and the largest
reference is 9,393 bytes in this checkout, all within unchanged host bounds.
Nine untouched authored package files remain equivalent to the installed prior
package after line-ending normalization.

The full unrestricted native suite passed **2,672 tests and 15 subtests**, with
**58 optional/host skips**, no failures/errors, in **378.60 seconds**. Its report is
ignored `state/phase5-full.xml`. The installed global package was then updated through
the existing native installer, with rollback to the preserved prior package available
on install failure. All thirteen installed authored files match the cloud-qualified
candidate byte-for-byte, all twelve references round-trip through the bounded reader,
and all twelve other installed skill files are unchanged. The verified installation
receipt is ignored
`state/backups/python-coder-host-guidance-20261009/installed-skill-after.json`.

Real local-model qualification and Python/GUI execution through ORSI remain unrun,
separate from passed deterministic and cloud source/byte checks. No execution
capability, provider selection, sampling or context window was added or changed.

## Integration and use

Preserve prior main at `archive/2026-10-09/main-before-python-coder-host-guidance`,
commit only the bounded verified change, fast-forward local main and the active
checkout without switching its settings branch, and remove only the merged feature
branch. Other worktrees, historical tips, remote refs and user settings edits are
preserved. Restart ORSI to refresh its installed skill catalog; attach `python-coder`
again for a later message when desired. Phase 6 remains separate.
