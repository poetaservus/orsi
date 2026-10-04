# Message skill picker

This change was developed and verified on `codex/message-skill-picker`, based
on local `main` `9afeaf5`, to protect the working application during review.
On 4 October 2026, the user explicitly approved merging and pushing the picker,
styling and Settings installer. See [the integration record](git-workflow.md).

## Using the composer

1. Type `/skill` in the message input. The installed catalog appears above it.
2. Optionally type a space and search by name or description. Choose with the
   mouse, or use Up/Down followed by Enter or Tab.
3. The command becomes a removable blue chip inside the composer. Type the
   prompt and send it normally. Choosing a skill alone sends no message.
4. Click the chip, or press Backspace at the start of the input, to remove it.

Escape closes the selector. Shift+Enter still inserts a newline. A new session
clears both the draft and its chip. Choosing another skill replaces the chip.
The list displays names only; hover a name to read its description. The popup
shares the code blocks' background, border, rounded corners, header and scrollbar
styling, with a compact layout and neutral selection highlight.
Clicking Send while choosing attaches the highlighted skill and returns focus
to the input; it does not submit the command or run a model request.
Filtering and choosing read only cached names/descriptions; they perform no
filesystem reads, inference or activation. The Settings-only follow-up now supports
[installation with an immediate catalog refresh](skill-settings.md). CLI installation
still requires restarting O.R.S.I. to refresh the application's startup catalog.

The attachment applies to the outgoing message, including its tool continuations
and approval waits. It is consumed on Send and released when the turn ends, even
on cancellation, provider failure or context rejection. An unavailable attachment
fails before inference; it is never silently replaced with another skill. The
chip is separate from the plain prompt, preserving pasted text and Unicode.

Subsequent messages resume the existing automatic selection behavior. Automatic
selection can independently choose the same skill for another relevant request.
If an older caller has explicitly activated a session skill, a message attachment
temporarily overrides it and restores that earlier selection afterward. The
existing session activation API and local slash-command path remain available.

## Implementation boundary

`app/ui/skill_picker.py` owns the popup and composer chip. The original plain
`QTextEdit`, composer geometry and conversation worker lifecycle remain in use.
`ConversationWorker` passes the optional exact skill name to
`ConversationService.run(..., skill_name=...)`; ordinary messages use their
previous call signature. The conversation service uses its existing turn lock,
catalog validation, activation and context-admission path, then restores prior
selection in `finally` before releasing the lock.

Names are retained as exact identifiers. Display labels are bounded, normalized
and elided; tooltips escape metadata instead of rendering its HTML. No body or
source path is displayed. Model profiles, sampling, prompts, context policy,
routing, tool schemas and authorization are unchanged. This adds no plugin,
capability manager, provider adapter or executable skill support.

## Verification

Final focused verification passed 204 tests and five subtests, using native
Windows handle access and repository-local temporary directories. Coverage
includes real keyboard/mouse composition, search, empty catalogs, removal,
replacement, Unicode, large multiline drafts, bounded metadata, legacy plain
messages, worker failure, missing attachments, terminal cleanup, unchanged tool
definitions and exact write approvals.

A restricted-shell run failed secure skill discovery, including the unchanged
activation/selection/diagnostic tests. The unrestricted native run passed all
204 focused tests; no loader or security change was made to bypass the sandbox.
Final mouse verification uses an actual press/release on Send, including its
focus change, rather than only programmatically emitting the click signal.

The final full regression passed **1,436 tests and 15 subtests**, with **58
existing skips**, in 168.77 seconds. The skips comprise seven host-dependent
symbolic-link checks and 51 opt-in live-model, cloud or UI gates. Those gates
were not run by the suite and are not counted as passes; the separate two-turn
14B audit above is narrower than the skipped qualification matrix. The suite
adds 26 checks to the unchanged main baseline of 1,410. Dependency consistency
and authored-file whitespace checks passed.

The separate native Qwen3 14B audit exercised the actual composer and worker,
using the existing fixed brand-font prompt and unrelated greeting. The font
answer passed; the two physical requests contained respectively one and zero
active skill sections, with the same twelve tools. Both completed normally. The
chip cleared, controls recovered, and the owned server exited. Effective limits
were 16,384 context tokens and 4,096 output tokens; the accepted model profile was
byte-for-byte unchanged. Automatic selection was disabled only in this isolated
fixture so that explicit attachment expiry could be measured independently.
Production automatic routing is unchanged.

The isolated audit uses synthetic state and a pinned open-source brand skill.
Its content-free summary and visually reviewed Qt screenshots are ignored local
artifacts under `state/test-artifacts/skill-picker/native-ui/`; they are not user
conversation data or a general model qualification gate. It can be reproduced
with `runtime/python/python.exe -B -m tests.skill_picker_live_validation`.

Focused reproduction:

```text
runtime/python/python.exe -B -m pytest tests/test_message_skill.py tests/test_skill_picker_ui.py tests/test_ui.py tests/test_completion_state.py tests/test_skill_activation.py tests/test_skill_selection.py tests/test_skill_diagnostics.py tests/test_default_14b_context.py -p no:cacheprovider --basetemp=.pytest-tmp-skill-picker-final-native --junitxml=state/test-artifacts/skill-picker/final-native-focused.xml
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp=.pytest-tmp-message-skill-final-full --junitxml=state/test-artifacts/skill-picker/final-full.xml
```

## Picker appearance refinement, 4 October 2026

The follow-up stays on the same unmerged feature branch. Rows display only skill
names, with the existing escaped descriptions available on hover. Description
search and exact selection identifiers are preserved. The popup shares the
existing code-block stylesheet declarations for its frame, header, title and
scrollbar; the code blocks' style values are unchanged. Row sizing accounts for
the popup border so short catalogs show completely without a scrollbar.

The relevant UI, completion and message-scope checks passed 92 tests and five
subtests in 9.08 seconds. Existing picker checks now verify names-only rows,
description tooltips and a fully visible two-skill catalog. A separate Qt preview
used the installed brand-guidelines and frontend-design metadata, verified that
the frontend hover tooltip appears, and captured the picker alongside a code
block for visual review. The ignored screenshots are under
`state/test-artifacts/skill-picker/style-preview/`. No inference was needed for
this presentation change; earlier live evidence is unchanged.

The follow-up full suite passed 1,436 tests and 15 subtests, with the same 58
existing skips, in 184.54 seconds. Skipped gates remain separate from passed
checks. Native Windows handle access and repository-local temporary directories
were used. Authored-file whitespace checks passed; application behavior and
model configuration are unchanged by this refinement.

```text
runtime/python/python.exe -B -m pytest tests/test_skill_picker_ui.py tests/test_ui.py tests/test_completion_state.py tests/test_message_skill.py -p no:cacheprovider --basetemp=.pytest-tmp-skill-picker-style-final-focused --junitxml=state/test-artifacts/skill-picker/style-final-focused.xml
runtime/python/python.exe -B -m pytest -p no:cacheprovider --basetemp=.pytest-tmp-skill-picker-style-full --junitxml=state/test-artifacts/skill-picker/style-full.xml
```
