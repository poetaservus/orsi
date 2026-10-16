# Word composition empty-plan investigation, 16 October 2026

## Scope and evidence

The reported two-page consulting proposal stopped with
`office.word_compose (invalid_arguments)`, location `blocks`, and
`Word page breaks must separate content blocks.` The agent subsequently stopped
after repeating the identical call. The request is an acceptance case; its text
was not changed and the user's document was not edited during this investigation.

The active checkout was clean local `main` at `c50f731`. The GUI process (PID
6408, `app.launcher`) and Office server (PID 31192, `app.mcp.office_server`)
both used this checkout and started at 20:46, after the latest integration
commit at 20:44. A stale process was not supported by this evidence. Neither
process was restarted or terminated by this investigation.

In that revision, the sole source of the reported message is the block field
validator after it removes redundant page-break delimiters. It raises only when
no paragraph or table blocks remain. Thus the error establishes an empty body
plan; it does not establish that Microsoft Word failed to format the proposal.
The rejection precedes approval preparation and native Word dispatch. Repeating
the unchanged request then triggers the existing repeated-call stop.

An isolated import of the exact baseline contracts reproduces the failure with
both `blocks: [{}]` and `blocks: [{"kind": "page_break"}]`. Both shapes pass the
advertised JSON schema and the strict provider schema, but fail runtime
validation with the screenshot's exact message. A plan containing paragraphs
and an intervening break passes. The optional page-break discriminator admitted
an empty object; its strict provider representation was `{"kind": null}`.

Tests of missing optional paragraph/table discriminators show that the provider
adapter preserves their content. No content-loss defect was reproduced there.

The actual failed call was retained inside protected ORSI history, not exposed
by the screenshot or ordinary content-free diagnostics. The user no longer has
access to that chat. Consequently the investigation cannot determine whether
the particular call used empty objects or explicit page breaks, or why the
model omitted its body content. No private profile keys or process memory were
read. No live provider requests were made.

## Bounded correction

Branch `codex/word-compose-empty-plan` starts from clean local `main` `c50f731`.

- Make the page-break `kind` mandatory. Empty objects and null discriminators
  are no longer accepted by the live advertised/provider schemas.
- Describe composition as a complete body replacement, rather than an operation
  for appending page breaks to existing content.
- Reject an empty/break-only plan with paragraph/table absence, explicit break
  and empty-object counts, and instructions to supply the complete body. Point
  to the existing paragraph `page_break_before` field for pagination.
- Retain only fixed numeric structural counts in the failure details; no body,
  header/footer, path, unknown field names, or other input values are copied.
- Preserve pre-upgrade null-discriminator calls as historical evidence.
  Original provider bytes must still match the settled call. Live decoding does
  not gain that compatibility, and historical evidence cannot execute a write.
- Refresh the accepted contract manifest without increasing schema limits.

Explicit break-only arrays remain structurally expressible in JSON schema and
are refused by runtime validation. This change removes the confirmed empty-object
hole and improves recovery evidence; it is not a claim that all semantic Word
constraints are enforced by provider structured output.

Prompts, model profiles, routing, sampling, context policy, permissions, native
Word compilation, and the repeated-call limit are unchanged. The acceptance
prompt is unchanged. The running GUI will load this new code on its next start;
it was not running stale code when the reported failure occurred.

## Qualification and limits

**214 focused tests passed**, zero failed/errors/skipped, in 7.562 seconds of
recorded test-suite time (8.66 seconds wall time):

```
runtime/python/python.exe -m pytest \
  tests/test_office_word_compose_validation.py \
  tests/test_openai_replay.py tests/test_office_mcp_contracts.py \
  tests/test_office_word_authoring.py tests/test_openai_tools.py \
  --basetemp=.pytest-tmp-wp3 \
  -o cache_dir=state/word-empty-plan/pytest-cache -o faulthandler_timeout=30 \
  --junitxml=state/word-empty-plan/focused-final.xml -q
```

This normal Windows shell run passed the schema/strict decoder, valid body
roundtrip, old failed/successful-call replay and tampering, agent correction/
repeated-call guard, Office manifest, and document compilation checks. A preceding
213-test normal-shell run also passed, with a warning that its optional shared
pytest cache could not be written (`WinError 5`). The final run adds the old
successful-call case and uses a task-local cache; it has no warnings.

A preceding restricted-shell run completed 35 composition checks, then stopped
producing output while entering the SDK/history fixtures. It was interrupted
after roughly 100 seconds; it is not counted as a completed passing run. The
same checks passed in the normal Windows shell above. This environmental stall
is separate from the user's pre-dispatch argument rejection.

The full Office catalog remains within its existing limits: **19,938 wire bytes**
and **7,078 estimated reserve tokens**, limits 20,000/7,200. The accepted manifest
matches. These are offline estimates, not measured billed tokens.

No additional full-repository suite was run, respecting the user's previous
instruction to stop repeating it. The earlier complete suite's unresolved
Windows rename failure remains documented in `full-suite-repair.md`.

The live model's generation of the supplied two-page proposal has **not been
qualified**. Previous broad suites and native document tests used prepared or
scripted plans and did not prove that this acceptance prompt produces a valid
live model call. Do not describe this correction as a verified end-to-end fix.

Content-free baseline reproduction, post-change diagnostics, budget results and
test XML are retained under ignored `state/word-empty-plan/`. No user document
or credential was copied into those records. Commit this bounded change,
fast-forward local main, and remove only its merged feature branch. No remote
operation or other-worktree change is authorized.
