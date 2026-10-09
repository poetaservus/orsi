# Personal Vault phase 3: application storage and credentials

Phase 3 connects the phase 2 engine to existing application consumers. It does
not migrate existing files or enable encryption without an explicit selection.
Phase 4 supplies profile setup, selection/unlock controls, migration and retention
UI. Normal `orsi` startup remains unchanged until that flow supplies a profile.

## Composition and ownership

Create/unlock a `Vault` using the phase 2 API, then create a `ProfileSession`, or
use `ProfileSelection.select(unlocked_vault)`. Pass that session to
`build_application(profile_session=session)` or `main(profile_session=session)`.
Both local and portable locations use these identical APIs and consumers. The
optional pinned crypto dependency is required only for encrypted storage.

`PersonalPath` is the shared private-state interface: join paths, inspect presence
and bounded sizes, read bytes/text, atomically write bytes, or delete a record.
`JsonStore` accepts either an ordinary legacy `Path` or a session-bound
`PersonalPath`. A protected path is deliberately not a native filesystem path;
converting it into a host filename fails instead of creating decrypted storage.
Each handle remains bound to its original unlock and never switches its backend.
Private path components exist only in the authenticated encrypted catalog.

The application routes existing consumers as follows:

| Consumer | Encrypted destination and behavior |
| --- | --- |
| Conversations, goals, tool results, provider replay and recovery state | `state/conversation_v1/conversation.json` and encrypted archives. Existing schemas and acceptance prompts remain unchanged. |
| Attachment originals and generated images/edits | Immutable ciphertext content and private manifests, with original display names inside encryption. External attachment sources remain untouched. |
| Prepared PDF/Office/text and image metadata | Encrypted `prepared_v1.json` dependent records. Image decoding and previews use memory buffers; parsers use verified seekable memory streams. |
| Interface setup, greeting, notification and approval preferences | Profile `state/ui_preferences_v1.json`, without reading legacy preferences as a fallback. |
| Local/cloud model selections, image settings and account limits | Profile state records. Accepted versioned model/provider/agent profiles remain application configuration. |
| Capability crash journal | Profile `state/capability_journal_v1.json`, with the existing content-free lifecycle schema and unknown-outcome recovery rules. |
| Personal skills and reference documentation | Encrypted immutable packages in `skills/`; selected-profile discovery, reviewed install, reload, reference access and removal use the vault. Global host skills are not a fallback. |
| Baseline and logs | Encrypted baseline; up to 200 fixed severity/event diagnostics. No log message arguments, paths, provider text or tracebacks are formatted. SDK logs are discarded. |

The same private-state interface supports personal personality/configuration,
templates, notes, summaries, indexes and drafts. This phase does not introduce
new personality editing, memory, embeddings, OCR, media formats or composer
autosave features where they did not previously exist. Public shipped personality
guidance and templates remain application resources. Personal skill instructions
and reference bodies enter model context only through the existing selection and
reference authority; discovery does not enable automatic skill selection.

## Attachments and retention

Original content and its manifest publish in one catalog transaction. Preparing a
document links its extracted text/preview metadata to that manifest. A conversation
commit atomically promotes its draft assets and publishes all asset references.
Archives retain their own references; deleting the final owning conversation or
archive removes the unshared manifest, original and prepared-data chain. Shared
assets survive while another owner still references them.

Unsent attachment drafts expire after 24 hours, including originals and prepared
data. Explicit abandonment removes only drafts owned by that composer. A
committed draft no longer has temporary expiry. Read/list hide expired records;
the engine's `expire`/cleanup APIs perform physical reclamation. Phase 4 must
expose those maintenance/retention controls. Explicit independent encrypted
backups can still retain prior data.

The existing maximum attachment size is 512 MiB. Encrypted imports and verified
reads use bounded process memory; large inputs can require multiple buffers.
There is no decrypted temporary-file fallback. This has not yet been qualified
on the minimum machine. Image pixel/count and parser safety limits remain in
place. A deliberate viewer export writes the user-selected outside copy, which
remains outside vault protection after lock.

## Credential policy

`CredentialProvider` is shared by cloud chat and its native image generation.
Startup derives a connection identity from the configured provider endpoint and
environment-variable *name*, never its value. Encrypted composition passes an
explicit empty key into both supported cloud backends, preventing their legacy
environment lookup. Provider secrets are held in the separate credential key
domain and never appear in personal paths, manifests, prompts or diagnostics.

- `configure(connection, ASK)` selects session-only credentials (the default).
  Entering cloud opens a session; the existing key prompt supplies its key through
  the provider. Leaving cloud, local fallback, lock, switch and exit end it. Every
  later entry into cloud requires another key. Repeated sends in the same cloud
  session do not prompt again.
- `configure(connection, SAVED)` permits loading an explicitly saved credential
  for that exact connection when it is needed. Merely selecting the profile or
  selecting this policy does not save an entered key.
- `save(connection, secret, consent=True, kind=...)` requires separate explicit
  consent for API keys, login/access tokens and refresh tokens. Policies themselves
  are encrypted under `setup/credential_policies_v1.json`.
- `delete_saved` ends the connection session and removes the chosen saved secret.
  Saving a replacement updates the encrypted record; the next connection session
  uses it. Older encrypted backups can retain previous keys. Provider-side
  revocation remains a separate action.

For an independently used image/auth service, `bind`, `begin`, `supply`,
`saved_token` and `end` define the equivalent explicit connection-session boundary.
Consumers must cancel and drain requests when their key is released. This supplies
the common policy interface without adding a new independent provider or login UI.

## Lock, switch and tools

Lock revokes the storage gate before stopping active work. Workers are cancelled
and joined before cached content is cleared. A late callback retains its old
session handle and cannot write to the next profile or to a plaintext fallback.
Conversation/document caches, private skill catalogs, image previews, composer
text, greeting, skill-import previews and viewer backdrops are cleared. Previously
opened protected streams close and subsequent reads fail. The attached Qt window
must be locked on its interface thread.

A failed stop/join keeps selection blocked and permits a close retry; vault keys
are released even on this path. Undrained worker caches remain inaccessible and
are cleared after a successful retry. An interrupted turn/journal may retain its
last durable state, which existing recovery reconciles on the next unlock;
unknown tool outcomes are never automatically replayed. Calls already handed to
an external provider cannot be withdrawn from that provider's systems.

File tools reject direct protected paths, resolved aliases, traversal into the
vault, and conservatively reject hardlinked files in protected mode. Parent
listing/find/search omit protected entries and do not descend into vaults. Writes,
copy/move sources and destinations, and launch targets use the same protected
roots. The selection owner preserves previously known vault roots in later
sessions; callers can supply additional known roots when constructing a session.
Runtime state is also excluded. This is an application tool boundary, not an OS
sandbox or protection from a compromised host.

No existing host projects or global personal files are copied automatically.
Phase 4 must make import/export choices explicit and preserve original files
until migration verification. Password/recovery/backup limits from the
[phase 2 contract](vault-phase2-contract.md) still apply.
