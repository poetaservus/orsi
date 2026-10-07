# Image and file input: phase 1 foundation

## Scope

This phase provides immutable attachment snapshots, durable message references,
worker/service plumbing, and explicit inference interfaces. Production image and
document adapters are not enabled yet. At phase 1 integration, the composer + button
remained a placeholder; [phase 2](attachments-phase2.md) now implements draft preparation.
No model requests, uploads, extraction, OCR or vision qualification were performed
for this phase. Existing plain text conversations and explicit skill selection
retain their behavior.

The remaining implementation order is:

1. **Complete:** shared storage and message format.
2. **Complete:** composer selection, previews, removal, drop/paste and document processing.
3. **Complete:** local document input and vision input with a matching projector.
4. **Complete:** native cloud inputs and provider/model capacity admission.
5. **Implemented:** [attachment-aware context, recovery and lifecycle qualification](attachments-phase5.md).
   The phase 5 record distinguishes passing source/lifecycle gates from the existing 14B tool-call limitation.

## Storage contract

`AttachmentStore` creates a snapshot from a selected regular file or captured
clipboard bytes. Each import has a unique `att-<32 lowercase hex>` identity.
Duplicates with the same display name retain independent identities and ordering.
An immutable `AttachmentReference` contains the identity, display name, kind,
media type, byte count and SHA-256 hash. It contains no original path, provider
upload ID, content, credentials or executable metadata.

The default store is beside the conversation JSON, under `attachments/`; the
application therefore uses ignored `state/conversation_v1/attachments/`. An
explicit shared store can also be supplied. Each published directory contains
`content` and `metadata.json`. Streamed imports write and flush both files in a
private staging directory before atomically publishing the directory. Failed and
cancelled imports remove their unpublished staging files. Filesystem failures do
not publish a reference or send a message.

The default storage guard is 512 MiB per snapshot, configurable on the store.
This is a storage bound, **not** a provider allowance: later phases must apply
actual file types, per-file, aggregate request and context limits. File extensions
provide advisory media classification only; decoding and format validation are
later-phase work. Binary data is never embedded in the conversation JSON.

On Windows, selected sources and verified copies are opened without following
reparse points and without write/delete sharing. Parent directories stay pinned
through the operation. Readers verify the manifest, byte count and hash before
yielding a read-only stream, and hold the stream open while an adapter consumes
it. Mutation of an original file after importing cannot change the snapshot.
The app does not expose a method to overwrite a published snapshot.

Starting a new session retains snapshots; automatic garbage collection is
deferred until draft, active chat and archive ownership can all be accounted for.
This also keeps copies available if saving a turn fails. Archives live alongside
the same attachment store. Reopening an archive in the conventional `archives/`
directory resolves its sibling store; custom locations must pass the original
store explicitly. Restoring a conversation requires its attachment directories,
not just its JSON. Missing or corrupt snapshots preserve chat history and block
inference with an attachment error; no files or capabilities are automatically
re-executed during recovery.

## Message and inference contract

Only user messages carry an ordered tuple of attachment references. An empty
text field is valid only when the user message has attachments. Plain messages
project to the existing `{role, content}` shape. Attached messages additionally
carry an `attachments` array of metadata in provider-neutral history. Returning
history or visible messages does not allow callers to mutate the saved references.
Legacy conversation JSON without the field remains readable.

The worker freezes the selection before handing it to `ConversationService.run`.
Local mode admits at most one combined file or image per outgoing message; earlier
messages may each retain their own attachment. Cloud storage/plumbing imposes no
small artificial count cap. Provider limits will be implemented before enabling
production cloud input.

An inference adapter must explicitly opt into `supports_attachment_inputs` and
implement both `respond_with_attachments(messages, attachment_store=...)` and
`count_attachment_message_tokens(messages)`. Attached messages cannot use text
token estimates of filenames or metadata. The latter interface will be refined
alongside extraction/vision accounting in the provider phases. Lazy and hybrid
wrappers retain the selected backend and pass the references and resolver through.
An attachment failure does not invoke the existing text-only cloud fallback.

At the phase 1 checkpoint, all shipped adapters remained opted out. Agent attachment transport was separately
blocked until native tool continuation and replay are implemented in the provider
phases. These gates run before beginning a new durable turn or issuing inference.
An attachment in earlier history cannot be silently stripped after switching to
an unsupported backend. A current attached turn that cannot fit context is retained
as a failed turn and never silently dropped to obtain a model response.

Local text-document adapters and native continuations are implemented in
[phase 3A](attachments-phase3a.md); local vision and cloud input remain gated.

Attached bytes and filenames are user material. They cannot activate a skill,
become system guidance, add capabilities, or grant access to the original folder.
Skill choice remains explicit. No attachment content is logged in diagnostics.

## Verification

Final focused native verification: **160 passed in 9.21 seconds**. Coverage includes
immutable imports, multi-chunk streaming, original-file edits/deletion, source and
snapshot handle locks, attachment-only input, order and duplicate names, restarts,
archives, interrupted turns, legacy chats, invalid/forged metadata, damaged blobs,
copy cancellation and disk failures, failed conversation saves, worker transport,
local per-message limits, cloud collections, mode switching, unsupported backend
admission, token-count boundaries, current-turn context failure, and skill/authority
isolation. Existing local/cloud, turn lifecycle, context and skill tests passed too.

Full native regression verification: **2,070 passed, 49 skipped and 15 subtests
passed in 246.74 seconds**. All 40 new attachment contract cases passed; the
49 skips are existing gated or host-dependent checks. Live local/cloud attachment
tests are deferred to the adapter phases and are not claimed as passed by these
contract tests. Dependency and Git whitespace checks also passed.

The first routing check named two nonexistent test files and collected no tests;
the corrected command and final focused run above passed. No product failure was
inferred from that command error.
