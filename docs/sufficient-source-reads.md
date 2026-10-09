# Sufficient source reads, 9 October 2026

Phase 2 of `Desktop/routingfix.md` starts from verified local main `60735e1` on
`codex/sufficient-source-reads`. The isolated checkout preserves the active
settings-panel edits. The reported Pythagoras program is not copied or modified;
qualification uses synthetic source with the same 23,631-byte, 453-line dimensions.

## Read contract

`filesystem.read_text` retains its 16,384-byte / 200-line defaults and existing
65,536-byte / 1,000-line ceilings. Its catalog description and truncated results
now direct a read at those supported larger bounds when the requested target is
absent. Repeating the same truncated prefix cannot reveal that target. No range
reads, pagination, model/context increases or new execution tools are introduced.

Results add `source_complete` and `read_hint`. Complete text has a true flag and
no hint. An excerpt has a false flag and either a concrete larger-read instruction
or a supported-limit explanation asking for smaller source containing the target.
Only exact text actually returned supports a patch; missing source is not permission
to reconstruct a method or replace a file speculatively.

The existing SHA-256 contract remains intact: the digest hashes complete bytes
actually read, never an excerpt. It is absent when the byte read is truncated.
A line-limited read can retain a real complete-byte revision digest while its
returned text remains incomplete. That digest does not establish unseen source.
UTF decoding, original line endings, path validation, exact patch matching,
approval previews, identity checks and cancellation boundaries remain intact.

Existing context projections now mark shortened source incomplete and identify
the context limitation. This only corrects provenance labels; projection policy,
context admission and durable results are unchanged. The existing executor may
also replace an oversized serialized result with `_orsi_output_limited` and a
marked JSON preview. That preview is incomplete evidence, and its output digest
is not a file revision. The read hint precedes source text in this bounded preview.

Routing, system prompts, installed skills, sampling, accepted profiles and loop
budgets retain their existing behavior. Phases 3–6 remain separate work.

## Verification

Focused unrestricted Windows checks passed **178 tests**, with two existing host
symbolic-link skips, in **44.87 seconds**. Twenty-seven new regressions cover
byte/line truncation, unchanged repeated prefixes, a larger read revealing the
method at line 330, UTF-8/LF/CRLF fidelity, actual returned digests, supported
ceilings, truthful context projection, native approvals and safe stale/missing
patch rejection. Deterministic local/cloud adapter tests exercise the runtime
boundaries with a roomy test adapter; they do not qualify a real local model's
context capacity. Existing acceptance prompts and guard assertions are unchanged.

The first focused attempt exposed two test-harness defects: oversized automatic
parameter labels exceeded Windows environment limits, and the scripted adapter's
conservative context accounting stopped before the edit. Explicit fixture labels
and a test-only context allowance corrected them; production settings were unchanged.
Its 12 failures/two setup errors remain in ignored `state/phase2-focused.xml`.

Final full unrestricted Windows regression passed **2,591 tests and 15 subtests**,
with **58 optional/host skips**, no failures/errors, in **351.16 seconds**. The
report is ignored `state/phase2-full.xml`; the local-model, lifecycle, optional
provider and symbolic-link skips are recorded separately from passed checks.

Real default-cloud qualification passed all four below-line-200 fix cases, with
and without the unchanged installed `python-coder` skill. Natural requests used
one complete read and one exact edit; forced initial default reads recovered with
one larger read before the edit. Skill cases added one reference call. Each case
saved precisely the requested bytes, made one approved edit, generated no images,
had no failed tool calls and released its transport. Reports are content-free
numeric/fixed-category summaries under ignored `state/phase2-cloud-1/`.

The first oversized-file verifier incorrectly assumed every successful read kept
its original output shape and raised `KeyError` on the executor's marked preview.
The corrected verifier's unchanged oversized prompt passed separately under
`state/phase2-cloud-limit/`: a 79,255-byte / 1,102-line file with an unseen target
stopped after two reads, reported the limitation and retained every original byte.
No mutation or image generation occurred. The first aggregate report retains its
verifier failure; it is not labeled a wholly passing gate.

The unchanged Phase 1 cloud gate also passed all four existing-fix/requested-copy
cases with and without the Python skill on this revision. Copied originals stayed
intact, screenshots retained their coding route, a genuine historical image was
generated, no coding turn generated images, and all transports were released.
The separate report is ignored `state/phase2-routing-compatibility/`.

Compilation, dependency consistency and whitespace checks passed. Python execution
and GUI behavior are outside ORSI's available tools; real local-model and other
opt-in live gates remain separate from these passed deterministic/cloud checks.

## Integration

Pre-integration refs, worktree maps and a verified complete-history bundle are
preserved under ignored `state/backups/sufficient-source-reads-20261009/` in the
isolated checkout. Preserved settings/configuration snapshots contain paths,
sizes and hashes only. Preserve prior main at
`archive/2026-10-09/main-before-sufficient-source-reads`, commit after verification,
fast-forward local main and the requested active checkout without switching its
settings branch, and remove only the merged Phase 2 feature branch. Other worktrees
and remote refs remain outside this operation. Restart ORSI to load the change.
