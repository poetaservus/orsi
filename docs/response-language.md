# Response language, 13 October 2026

Settings → General → Response Language replaces the disabled placeholder with
Auto and 45 named language choices, including native names and both Norwegian
written standards. Auto is the default for new and existing profiles and can
follow languages outside the catalog. A fixed selection supplies the preferred
reply language even when the request is in another language. Explicit user
instructions for an answer/artifact language take precedence for that output.
Mixed input follows the dominant appropriate language. Short, ambiguous,
code-only and image-only requests inherit the most recent clear user language,
with English as the final fallback. Quoted/source/attached text does not select
the reply language.

## Storage and lifecycle

`state/response_language_v1.json` contains only schema version 1 and a stable
`language_code`. It uses the same profile-bound JsonStore and encrypted-storage
authority as other preferences. Legacy unprofiled use stays inside ignored
installation state. Reading a missing preference never writes the Auto default.
New chats, restarts and portable profile relocation preserve the choice.
Switching profiles does not copy preferences. Profile lock clears and revokes
both settings authority and the visible control.

The picker is disabled during generation, settings work and shutdown. The service
also requires the conversation's run lock for a change, so a tool sequence retains
one preference throughout. Failed saves leave the prior effective selection.
Unreadable/unsupported saved records remain intact; Auto is active and the picker
explains the preserved preference. No existing user settings are migrated.

## Response and protocol separation

One language-policy section is composed after the selected personality and before
optional skill guidance, for chat, conversational agent, compact agent, tool
continuations and image requests. Original/Choom definitions remain unchanged.
The normal context calculation counts the full additional instruction; selecting
a language invalidates the old usage estimate, without expanding model limits.

Tool and skill names, schemas, JSON keys/enums, IDs, paths, commands, code and
literal source excerpts remain exact. Human-readable generated content may use
the requested artifact language. Language preference does not enable tools,
automatic skills, new permissions or different approval behavior. Internal skill
selectors and completion reviews keep their strict original JSON protocols.
Accepted model profiles, sampling and context policies are unchanged.

Small runtime-written chat notices have local translations for all 45 choices:
ordinary work/completion phases, skill activation, verbatim file headings,
empty/truncated files and generated-image captions. Interface labels, detailed
operation/permission/approval notices and runtime diagnostic errors retain their
existing interface wording. A generic translated working label never conceals
that approval is needed. This preference is separate from the GUI Language
placeholder.

## Multilingual recovery and image routing

Filename disambiguation now depends on the current failed native lookup/read and
its existing scope/permission checks, rather than English request verbs. Loose
filename comparison retains Unicode letters/numbers. Actual paths are never
translated or rewritten.

Pinned langid 1.1.6 provides bounded, offline statistical hints for runtime
presentation, ignoring quoted/code/path text. No language-detection service or
translation request is used. Low-confidence or very short input inherits earlier
clear user language for notices. The model still resolves Auto semantically for
its own replies, independent of these hints. The detector's pre-trained model is
loaded lazily; no message text or classification cache is saved.

For confidently identified non-English requests on an image-capable backend, one
bounded tool-free semantic selection distinguishes explicit visual creation,
editing and analysis from file/code work or ordinary conversation. It uses the
existing strict selection protocol, selected inference model, cancellation and
context admission; malformed/uncertain results fall back to the normal agent.
Quoted instructions and previous tasks grant no creation authority. Only the
latest visible visual task can provide an implicit source. Submitted attachments
are verified before this auxiliary request, and resolved sources are admitted
through the normal path before execution. Pure UI preview hints remain local;
the background worker makes the authoritative routing decision.

If a non-English file task has a successful read but the final answer omits its
contents, at most one additional tool-free selection checks whether the current
request actually requires verbatim display. Summary/analysis/supporting reads
retain their reports. Literal bytes, completion metadata and image references
are preserved. Internal selection JSON never streams to the chat. Auxiliary
decisions are not activated instruction skills and do not alter skill selection.
Diagnostics contain only result categories, counts and token estimates.

These auxiliary choices add model requests only on the described paths. Neither
a successful synthetic test nor a configured language guarantees that every
local/cloud model has equal proficiency in that language. Short ambiguous image
requests may require a clearer request or the existing `/image` command.

## Verification

The original focused regression passed 217 checks. Expanded language, native and
fallback tool, skill selection, context and encrypted portability coverage passed
311 checks. Exact prompt expectations and synthetic context headroom now count
the deliberate language-policy addition; existing acceptance prompts and model
limits remain unchanged. An initial restricted-shell run could not acquire
Windows profile leases and is not treated as a product failure. An early full run
was interrupted during review to add the pre-selector attachment-admission guard.

The final affected run passed **387 checks** in 55.74 seconds, including the
pre-selector attachment-admission guard. The first completed full run passed
3,680 checks and 15 subtests, skipped 61 and recorded five failures in 817.25
seconds. Four synthetic 8,192-token read/edit scenarios reached their context
boundary after the additional 340 estimated language-policy tokens. Their
fixtures now preserve the original task/result headroom while counting that
instruction; assertions, acceptance prompts and production limits are unchanged.
The fifth assertion expected the composer's old y=4 position. Independent
rendering from unmodified local main `410d45d` confirmed y=0 before and after
display, matching its already integrated composer alignment. Only the outdated
assertion was updated; no composer implementation changed.

The recovery/UI/new multilingual source-scope recheck passed **170 checks and
five subtests** in 16.19 seconds. The final full native regression passed
**3,689 checks and 15 subtests**, with **61 optional skips**, no failures/errors,
in **575.43 seconds**. Reports use `state/response-language-final-focused.xml`,
`state/response-language-regression-recheck.xml` and
`state/response-language-verified-full.xml`, with matching logs. Reports,
synthetic UI captures and temporary files remain under ignored repository-local
`state/`. General settings renders at 760×600 and 1280×800 were visually reviewed.
Compilation, whitespace and installed-dependency checks pass.
Live API/model language-quality gates are separate and skipped; no
credentials or personal-profile contents were used for verification.

## Git integration

The change starts on `codex/response-language` from local main `410d45d`, then
fast-forwards to the existing committed personality tip `099b4b0` to preserve the
active launcher's functionality. The personality branch remains a recovery tip;
this feature's changes are isolated in its own commit. Content-free pre-integration
refs/worktrees are retained under `state/backups/response-language-20261013/`.
Prior main is preserved at `archive/2026-10-13/main-before-response-language`.
After the passing full qualification, commit, fast-forward local main and remove
only the merged response-language branch. Other worktrees and remote refs are
outside this task.
