# Word complete-body composition investigation

Branch `codex/word-compose-complete-body` starts from clean local main
`b79137d`. No local model is used. The user identified the configured cloud
model as GPT-6 Luna and authorized the existing credential for live acceptance.
Credentials are read in memory; no credential or private chat is retained.

## Demonstrated boundaries and defects

The latest reported refusal describes two explicit page-break blocks and zero
paragraphs/tables at capability validation. It occurs before approval or Word
dispatch. That particular provider response is unavailable; its raw generation
cannot be reconstructed. Neither stale processes nor a faulty user prompt is
an explanation established by this investigation.

The exact two-break shape passes both the previous advertised JSON schema and
its strict Responses projection, then fails runtime validation with the reported
message. The schema offers a content-free `WordPageBreak` union alternative in
an operation that replaces the whole body. Making its discriminator mandatory
in b79137d prevented `{}` but retained this contract mismatch.

Fresh live evidence distinguishes this from content loss. With the b79137d
advertisement, GPT-6 Luna generated 14 paragraphs and three tables (4,282 body
characters). Raw provider, decoded and validation-input shapes match exactly.
Validation rejected that full plan twice; the baseline did **not** reproduce
the historical break-only generation. Its first diagnostic run lacked the new
safe constraint-feedback log, so its particular field rejection is unresolved.
It is not counted as successful acceptance.

With the initial corrected advertisement, live generation produced complete paragraph
and pricing-table plans. Raw provider, decoder, typed validator, serialized
approval, the actual plan bound by the Office worker, and dispatch retain the
same content lengths and block counts. No content-dropping transform was found.
This establishes preservation in these fresh runs; it does not attribute the
unavailable historical response to a particular model decision.

Two early corrected-contract live runs reached native dispatch and returned
`outcome_unknown`. The second retained the fixed stage `word_document_write`
and HRESULT -2147352567. Independent readback found the fixture still blank.
No uncertain mutation was retried.

Investigation found another concrete serialization defect: the public alignment
value `justify` was written as `<w:jc w:val="justify">`. WordprocessingML calls
justified alignment `both`, as documented by
[Microsoft's JustificationValues enumeration](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.justificationvalues?view=openxml-3.0.1).
A real Word regression reproduces the uncertain write with an otherwise valid
justified plan. Mapping only this enum to `both` makes the same native case pass.
Left, center and right retain their values. An RPC-unavailable diagnostic during
the deliberately failing native test's teardown is recorded separately from the
reproduced invalid-XML product defect.

After that correction, the next live plan writes its complete body/table and
renders as two native pages, but readback refuses its spacing at the former
`LineSpacingRule == 5` assertion. Word canonically exposes single/1.5/double
spacing as rules 0/1/2, with font-dependent point heights, rather than custom
multiple rule 5. Verification now compares the requested ratio for those exact
standard rules and retains the numeric multiple check for rule 5. Other rules
and wrong ratios still fail. Focused native cases cover all three standard
ratios and custom spacing, alongside explicit mismatch refusals.

The subsequent real model run successfully composed the complete body twice,
then stopped at the unchanged identical-call limit with a one-page document.
Both calls retained 21 paragraphs, the pricing table and 3,627 body characters;
the optional page-break flag was never set. This directly demonstrates that
describing the optional flag was insufficient for this use case. The final live
contract therefore requires **pages containing complete content**, rather than
asking the model to infer page boundaries from optional paragraph flags.

## Bounded correction

- Require `pages`, each with a nonempty list of paragraph/table blocks. Describe
  a two-page document as exactly two complete page objects, including its pricing
  table. Neither a pagination-only patch nor a content-free page is advertised.
- Normalize page groups into the existing complete native block plan **before
  approval**. The first paragraph of each later page gets `page_break_before`;
  a table-first page uses the existing native break between complete content
  blocks. Do not mutate the raw provider call. Reject competing `blocks` and
  `pages`, explicit break flags inside page groups, and combined bound violations.
  Render `first:last` over existing pages; actual overflow still requires review.
- Keep typed standalone breaks for older native calls and recovery. Restore
  their schema only when validating settled history, including old nullable
  discriminators. Original provider bytes must still match the settled call;
  tampering fails, and history grants no live execution authority.
- Record fixed, bounded structural summaries: known block kinds/counts, per-block
  and total content lengths, table dimensions, running-matter lengths, paragraph
  pagination and a justified-block count. No input text, unknown keys/values,
  paths, IDs, hashes, credentials or raw exceptions enter these logs. The actual
  complete guard-bound plan returns only this summary over private control.
- Retain allowlisted validation feedback so a subsequent retry can be compared
  with the original failure. Do not increase retry limits or accept a break-only
  plan. The exact two-break rejection/corrected retry and identical-call stop
  have focused agent-loop regressions.
- Serialize justified paragraphs as the valid native XML enum `both`.
- Verify standard line-spacing ratios using Word's canonical rules, rather
  than incorrectly classifying equivalent standard spacing as an uncertain write.

Native editable paragraphs, built-in heading styles, native tables, headers and
footers, PAGE/NUMPAGES fields, full-plan approval identity and guarded recovery
remain in place. No placeholder body, text boxes, model/profile/sampling changes,
core-prompt changes, routing changes or context-policy changes are introduced.

The accepted Office manifest is refreshed. Its full catalog remains below the
existing ceilings: 19,945 wire bytes and 7,081 offline reserve tokens, against
20,000/7,200. These are offline estimates, not billed tokens.

## Acceptance method

`tools/verify_word_proposal.py` uses the configured GPT-6 Luna profile, production
Responses decoder, HybridInferenceEngine, ConversationService, agent/executor,
Office stdio connection, exact approval and native Word readback. It never
seeds a model response or injects/transforms a composition plan. Baseline mode
loads the exact previous Word advertisement from tracked b79137d in memory.
Model settings and the request remain the same between baseline and correction.

The old chat is unavailable and no original proposal acceptance prompt was
found in the available repository/helpers. The user's current reproduction
request is frozen in `tests/fixtures/word_proposal_prompt.txt`; only its fixture
document path is substituted. This is not claimed to recover the old chat.

Each run edits a uniquely named copy of Desktop/report.docx in the task artifact
directory outside the application write-protected root. The original is checked
unchanged. Writes are approved only to that fixture through production ASK and
approval binding; arbitrary writes/execution are denied. Conversation and tool
text stay in memory. Disk diagnostics retain structural summaries only; the
generated DOCX and page images are intended deliverables, not diagnostic logs.

## Qualification

The final deterministic selection passes **273 tests**, with zero failures,
errors or skips, in **47.444 seconds**. The final explicit-page native selection
passes **five real Word cases**, with zero failures/errors/skips, in **79.003
seconds**, covering complete-page normalization before approval, editable table
content, two-page rendering, left/justified alignment and standard/custom spacing.
The preceding native alignment/spacing selection
passes **39 tests**, including **five real Word cases**, in **82.626 seconds**.
The earlier **252-check** selection also passed the existing native full-report
gate: complete snapshot/approval, denied/stale writes, editable text/table,
three-page rendering, owned recovery, save/reopen and owned-process release.
These synthetic native plans are not evidence of live model generation.

**Live acceptance passes on GPT-6 Luna.** The final clean run completes in
13 model requests, with two successful model-generated complete compositions,
normal layout/render reads and an approved successful save. Each generated
call contains 15 paragraphs, a 5-by-2 editable EUR table and 3,589 body characters
in two explicit page objects. The native plan gains one paragraph page start;
all body kinds/counts and content lengths survive decoding, normalization,
approval and dispatch. Raw diagnostics now distinguish supplied flags (zero)
from the native flag applied by page-group normalization (one).

The saved proposal is **exactly two rendered A4 pages**, both visually inspected.
It contains the requested title/fictional parties, overview, three workstreams,
deliverables, four phases over eight weeks, editable EUR pricing with correct
totals/payment arithmetic, measurable success criteria and next steps. It has
native headings and tables, consistent running identification, PAGE/NUMPAGES
fields and no text boxes/shapes. All automated content/geometry/price checks
pass. Owned Word and bridge processes are released. The original report.docx
remains unchanged. The full repository suite was not run.

A prior explicit-page run also completed through the normal model path and
saved a two-page proposal (24 paragraphs, one 7-by-2 table, 4,641 characters).
Its independent post-save check initially reused a test-only context restricted
to the repository, which denied reads of the external artifact fixture. That
harness error was fixed by retaining the fixture's real host read policy.
Independent reopen/render inspection confirmed the saved artifact, its native
structure and pricing; both pages were visually inspected. The final clean
repeat above passes the corrected harness without that exception.

This verifies the supplied live use case and the corrected contract. The exact
raw model response from the unavailable historical failed chat remains unknown;
the baseline fresh run did not reproduce that particular break-only response.
Do not describe this evidence as recovery of that chat or a guarantee for every
future document/model response.

Initial restricted focused execution stalled in existing process/handle fixtures
and was interrupted; it is an environment limitation, not a passing run or a
Word product failure. The normal Windows shell completed the focused selection.
Initial new historical-replay fixtures used an incomplete context and an
incorrect provider wire name; those test fixtures were corrected, without
relaxing production replay checks.

Deterministic/native evidence is under ignored `state/word-complete-body/`.
Live structural diagnostics and isolated artifacts are under this task's
visualization directory, in `word-proposal-*` run folders. Failed attempts remain
separate from passing verification. No remote publication or other-worktree
operation is authorized by this task.
