# Interactive question composer

O.R.S.I. can hand back an interview or clarification as a mixed native form in
the composer. Short single-choice lists use radio buttons; longer lists and
explicit dropdown questions use a dropdown; multiple-choice lists use
checkboxes; open questions use multiline text. Additional information is
optional. Required choices start empty. The composer grows upward, with a
scrolling body and fixed header/footer; chat clearance follows its height.

Answer in chat and Back to questions retain selections and the ordinary draft.
Ctrl+Enter submits valid answers; Enter in a text field adds a newline. Send
uses the established conversation worker, model selection, admission and
history path. A form submission preserves unrelated unsent text, attachments
and skill selection. Pre-admission failure retains answers for retry. After
durable admission the answer is an ordinary user turn; later inference failure
does not silently submit it twice. Operational approval remains a separate
panel and decision, with existing runtime checks.

## Shared presentation contract

The operational core briefly describes a final `orsi_questions` JSON fence.
The assistant asks readable questions before that fence, providing a fallback
when the model doesn't support the format or produces invalid metadata. There
are no new tools, provider-specific function schemas or additional model calls.
Local Python/native adapters, compatible cloud APIs and OpenAI Responses use
their existing text channels. Personality and language instructions keep their
existing precedence. Repeated operational wording in the compact native prompt
was condensed so this feature does not increase its existing prompt cost.

```orsi_questions
{"version":1,"questions":[{"id":"style","title":"Which style?","kind":"single","required":true,"options":[{"id":"minimal","label":"Minimal"},{"id":"colorful","label":"Colorful"}],"allow_other":true}]}
```

Supported kinds are `text`, `single`, `multi` and `dropdown`. Choice options have
stable IDs and readable labels. `required` defaults to true, `allow_other` to
false and `options` to an empty list. Text questions have no options/custom
choice. Limits are 12 questions, 50 options per question, 32 KiB of metadata,
1,000 characters per title and 300 per option label. IDs must be unique in
their scope; `__other__` is reserved. Unknown fields, duplicate JSON keys,
invalid shapes and incomplete output cannot activate controls. Quoted/nested
code fences are not interpreted as this channel. Stream previews suppress
the control fence, including its partially received delimiter.

Validation and readable answer formatting live in
`app/conversation/questions.py`; native controls live in `app/ui/questions.py`.
The service projects only the settled assistant response, then persists optional
`ChatMessage.question_batch` metadata alongside the readable message. Existing
histories without it still load. Provider replay is retained unchanged; its
readable question projection isn't duplicated in subsequent Responses history.
No metadata is interpreted from user messages or tool output.

The UI binds a pending form to its conversation and assistant turn. A latest
unanswered form restores when that active conversation is loaded. Submitted or
superseded forms, earlier messages and other sessions cannot become active;
New session/profile clearing removes the view. Unsent partial answers are kept
in memory while switching composer modes, not separately saved to disk. Existing
plain/encrypted history storage remains the storage boundary.

## Essential verification

The user requested essential checks only. Native scripted verification covers
mixed controls, validation/custom answers, optional skips, keyboard submission,
small-window scrolling, drafts/attachments, retry, answer-in-chat, pending-form
restoration, stale-session protection, approval separation, incomplete/streaming
output, local/cloud reviewed handoffs with Original and Choom, and real adapter
request serialization over synthetic transports. Existing approval, streaming,
conversation/attachment, personality/coding-policy and default-context checks
are included. Synthetic Qt rendering was visually inspected. Paid/live API,
real-model format reliability and the full suite are separately unrun.

The first new test collection exposed unescaped JSON braces in the existing
prompt template; guidance now describes the JSON fields without literal braces.
An initial streaming assertion incorrectly compared preserved whitespace before
the delimiter; it now checks the visible text. Initial essential runs also
exposed two tight default-context cases that fail on the starting main prompt
as well. A content-free in-memory comparison is retained under ignored
`state/question-context-baseline/summary.json`. Repeated compact-prompt rules
already present in the immutable core were condensed, preserving authority,
schemas, model limits, sampling, routing and unchanged acceptance requests.
The default-context checks now pass. Earlier failing XML runs remain separate
verification evidence; the final results are recorded in `docs/git-workflow.md`.
