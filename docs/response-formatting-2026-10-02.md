# Light response formatting candidate

Assistant prose now renders Markdown emphasis, headings, lists and inline code using Qt's document
parser. Short shared style guidance applies to chat-only, ordinary-agent and capability-agent
responses. Ordinary user prompts, routing, permissions, sampling and model profiles are unchanged.
Explicit output formats take priority in the guidance. Model compliance remains a qualification
question, not a renderer guarantee.

Fenced code continues through the existing literal code-box path, including incomplete fences and
completion notices. Full-message copying preserves the original Markdown; code copying preserves
the code bytes. User messages and ordinary error messages remain literal. The text renderer disables
embedded HTML and resource loading, replacing Markdown image objects with a text placeholder.
Rendered paragraph/list/heading height is measured at the actual available width.

The user's typography refinement lowers strong emphasis and heading weight from bold (700) to
medium (500). Prose line height is 128%, with extra paragraph/heading margins and light spacing
between list items. This is a presentation change; response text, prompts, code boxes and inference
are unchanged. The existing UI/completion checks passed: 64 tests and 5 subtests.
The typography full regression passed 830 tests and 5 subtests, with 54 skipped live tests.
Its log is `state/response-typography-regression.log`; this does not replace the earlier failed
formatting reports or the missing full live qualification matrix.

Verification on `codex/response-formatting`, based on main `030f83d`:

- Final focused run: 75 passed, 5 subtests passed. Actual Qt selection, narrow/wide window layout,
  original message/code copying and incomplete responses are checked. The isolated history-write
  failure from the final full run passed its focused recheck.
- Visual preview: `state/response-formatting-preview.png` (synthetic illustrative response).
- First full regression: 829 passed, 1 failed, 54 skipped, 5 subtests passed. Failure:
  `test_each_folder_requires_new_approval`, Windows atomic journal replacement. Focused retry passed.
- Final full regression: 829 passed, 1 failed, 54 skipped, 5 subtests passed. Failure:
  `test_clarification_accepts_only_the_next_explicit_path`, Windows atomic conversation replacement.
  The failed full reports remain failed; successful retries do not erase them.
- Local live checks used real servers and synthetic isolated sessions, with two repetitions of
  exact ordinary `chat-0`, the unchanged pancake-recipe prompt and a small code-only request per
  profile. The accepted 14B and experimental 4B passed 6/6 checks each. The 3B passed both recipe
  checks, but failed both exact ordinary replies and both code-only checks. All owned servers exited;
  actual context/output budgets remained 16,384/4,096 with unchanged sampling.
- A 3B comparison loaded the exact prompt constants/template from unchanged main `030f83d` into
  the isolated test process and repeated the same requests. Both exact ordinary replies and both
  code-only checks also failed there; recipe turns attempted unnecessary filesystem calls. This
  limited comparison does not establish broader model reliability or qualify a baseline.

Live reports/logs and synthetic responses are retained separately under ignored
`state/response-formatting-live*` and `state/response-formatting-baseline-3b*`. Full regression logs
are `state/response-formatting-regression.log` and `state/response-formatting-regression-final.log`.
The required complete long-code/edit/clarify/cancellation/model-round-trip qualification matrix
was not rerun for this candidate. No main, working-baseline or release promotion is justified by
these checks, and the working main revision is preserved.
