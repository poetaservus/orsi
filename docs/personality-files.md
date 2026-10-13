# Personality files

Settings → General → Personality selects the voice for the next response.
**Original** is the default calm voice; **Choom 2.0.0** is the supplied expressive
cyberpunk voice. Each unlocked profile remembers its own selection.
Definitions are shared by the installation; profiles store only the selected ID.

## Add a personality

1. Create a UTF-8 `.md` file in `app/conversation/personalities/` beside
   `original.md` and `choom.md`.
2. Give it a name and style instructions using the example below.
3. Restart O.R.S.I. and select it under Settings → General → Personality.

No Python edit, registration list, network service or model change is needed.
The settings description comes from the file's metadata. Files travel with
portable deployments and are included as Python package data.
Public ZIP exports continue to use committed source files.

For example, save this as `friendly.md`:

```markdown
---
name: Friendly
description: Warm explanations with practical examples.
version: 1.0.0
---

Speak warmly and explain unfamiliar ideas with practical examples.
Use gentle humor when appropriate. Follow the user's requested tone.
```

The filename without its extension is the saved ID. An optional `id:` field
can keep that ID stable across filename changes. IDs use lowercase letters,
digits and hyphens, start with a letter, and are at most 64 characters long.
Keep IDs stable when updating a personality's wording or version. `name` is
required; `description`, `version`, `id`, `type` and `for` are optional. If
supplied, `type` must be `personality`. Metadata is a flat YAML mapping with
unique keys; YAML metadata is excluded from the prompt.

Both `.md` and `.txt` files are supported, with a 32 KiB UTF-8 file limit and
a non-empty body. Invalid files are skipped with a content-free warning.
Duplicate IDs cannot displace the bundled definitions. Definitions are loaded
once per application process, so edits require a restart and cannot change a
voice midway through a response. Removing a selected definition preserves the
saved preference and uses the existing Original fallback; restore the file
and restart to recover it. Keep the bundled `original.md` default installed.

## Core and style boundary

`app/conversation/prompt.py` owns operational instructions, security and privacy
boundaries, truthfulness, tool schemas/usage, requested-output contracts and
approval rules. Its chat, conversation and agent prompt builders contain no
default personality. The existing reply-language policy remains independent.

`with_personality` composes the applicable core with exactly one selected file
body. It rejects an already composed prompt instead of appending a second
voice. Historical replies are context, not a personality selection. Existing
history, provider replay, attachments, skills, model profiles and sampling are
preserved. Style text cannot grant tool authority or override runtime checks.

Cloud and local chat/agent requests, tool continuations, reviews and fallback
retain that assembled system message. Image generation uses the same core/style
composer. Internal skill/presentation selectors retain their strict JSON-only
protocols without personality text. Machine-readable protocols and requested
deliverable formats take precedence over conversational styling.
The complete selected body counts toward context admission. Large personalities
and tool catalogs can exceed a small model's limits; the existing admission
check rejects that request rather than truncating the voice or raising limits.

The supplied Choom v2 file is copied unchanged, including its explicit deference
to core operational boundaries. Its safety reminders are supplementary; the
core does not depend on any personality file for those rules. Its stable ID is
`choom`; legacy `choom-v1.0.0` selections resolve to it without rewriting saved
private state. The UI reads the current name, version and description generically.

Imported source SHA-256:
`ef9baeb4130b4670e0266b420d4f043e33a2e5346ca819e076f0014101ea1abf`.

## Verification

The regression checks capture Original → Choom → Original requests through both
local adapters, both cloud adapters, cloud tool continuations/completion reviews,
cloud-to-local fallback and image generation. They check one active style,
preserved history, unchanged tool catalogs/permissions and released SDK workers.
File-only additions are tested through discovery, General settings and portable
packaging; malformed metadata, duplicate IDs and oversized files are covered.

The full native suite passed 3,715 checks and 15 subtests, with 61 optional/host
skips. Two pre-existing Windows timestamp fixtures were made deterministic
without changing production reader or vision verification behavior. Earlier
failures and their baseline reproductions remain in the Git workflow record.

Paid live API and real-model style-quality gates are separate from these
deterministic checks and have not been run for this change. Request checks prove
instruction isolation; they do not guarantee a model will never echo an earlier
conversation's tone. Test results are recorded in the Git workflow entry.
