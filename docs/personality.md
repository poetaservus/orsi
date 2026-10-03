# O.R.S.I. personality

The shared voice in `app/conversation/personality.py` implements the user's personality draft:
composed, stoic, precise, quietly confident and naturally feminine, with restrained warmth.
It favors clear answers, honest uncertainty and practical next steps, avoids emojis and artificial
enthusiasm, and allows sincere empathy without forcing emotional conversations into troubleshooting.
Replies follow the user's current language while preserving technical syntax and identifiers.

Chat-only, ordinary conversation, full agent and compact agent prompts share the same guidance.
The previous exact English response to "how are you" was removed so it cannot override language
and tone. Existing Markdown and requested-output rules still apply, including code-only replies.

Voice does not grant authority or advertise capabilities. The runtime registry, permission checks,
approval decisions, model profiles, sampling and context-recovery policy retain their existing roles.
The compact guidance contains 276 words (2,058 characters), rather than repeating the long
draft and its examples. Token cost depends on the model tokenizer; the addition still reduces
available history space. Synthetic tiny-context tests leave a fixed history allowance around the
production prompt, without changing actual model limits.

Prompt-path regression checks verify that request selection preserves this guidance, the exact
Hungarian user message and the advertised read-only catalog, including compact fallback. Real-model
personality smoke checks cover English, Hungarian, emotional context, code-only output and a verified
read-only metadata result on synthetic fixtures. These checks do not replace the full workflow
qualification gates required before promoting a model/profile as an accepted baseline.

The full regression run recorded 850 passed, 1 failed, 54 skipped and 15 subtests passed.
The failure was an access-denied error during atomic Windows capability-journal persistence
in the denied-edit test; its isolated recheck passed. This records the failure rather than
treating the recheck as a completely green full run. No persistence behavior was changed here.

Repeated live smoke checks on the unchanged 16,384-context / 4,096-output profiles recorded:

| Model | Completed checks | Remaining failure |
| --- | --- | --- |
| Qwen 14B | 10/10 | None in this smoke check |
| Qwen 3B | 8/10 | Both code-only requests proposed an action requiring approval instead of returning code |
| Qwen VL 4B | 9/10 | The second metadata task stopped at the context limit |

English/Hungarian switching and emoji-free replies passed on all three models. Successful metadata
calls verified actual fixture size and unchanged bytes. All owned model servers exited. Raw smoke
responses and reports stay under ignored `state/personality-live-v2/`. These results are bound to
the new personality source on baseline `28482ae`; they are not a baseline-versus-feature benchmark.
The long-code, edit/clarify/follow-up, cancellation and model-round-trip qualification matrix was
not repeated for this personality change. The feature remains on `codex/composed-personality`
pending full qualification or an explicit user-approved integration.
