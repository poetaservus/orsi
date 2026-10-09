# Personal Vault phase 1: storage map

Audit date: 9 October 2026. Source baseline: local main `aeb350d`.
This is a source-code inventory and proposed destination/retention contract,
not a migration. Existing files and settings have not been moved or inspected
for personal contents. The companion [contract](vault-phase1-contract.md)
defines the format and lifecycle; [verification](vault-phase1-verification.md)
distinguishes completed checks from external qualification gates.

## Current location model

`app/settings/paths.py` resolves `ROOT` from the application checkout or executable.
Both an ordinary local launch and a launch from portable media use `ROOT/state`;
there is currently no separately selected encrypted personal profile. On portable
media, application-managed state follows the application drive letter. Default
skills instead use the current Windows account's home directory. A portable
launch therefore does not currently bring all personal resources with it.

Classes below are **public application**, **personal vault**, **host project** and
**disposable runtime**. A retained derivative inherits its source's protection;
calling it a cache or diagnostic does not make it public.

## Current sinks and proposed behavior

Internal paths in this table are encrypted logical names in a catalog, never
cleartext names on disk. Only supported features are migrated in later phases.

| Current source or sink | Classification and proposed destination | Retention/deletion contract |
| --- | --- | --- |
| `app/`, shipped UI assets/sounds, `runtime/`, `models/`, launchers, shipped public docs | Public application; remain outside the vault | Application update/uninstall owns them. No user data is added to these trees. |
| Versioned `config/model.json`, `config/agent.json`, `config/cloud.json` defaults | Public application defaults | Versioned profiles stay unchanged. User-specific copies/overrides belong in encrypted `preferences/`; secrets in arbitrary custom headers/config are credential import candidates, never public defaults. |
| `state/ui_preferences_v1.json`, including custom greeting and tool approval preference (`app/main.py`, `app/ui/main_window.py`) | Personal vault: `preferences/ui` | Retain until changed/reset or profile deletion. The custom greeting is personal personality content. No preference is copied into public bootstrap. |
| `state/local_model_selection_v1.json`, `state/cloud_model_selection_v1.json` | Personal vault: `preferences/models` | Retain selected IDs until changed/reset. Accepted model definitions remain public. Before unlock, only public launch defaults/unlock controls are available. |
| `state/image_generation_v1.json` (`app/inference/openai_backend.py`, `app/settings/images.py`) | Personal vault: `preferences/images` | Retain until changed/reset; generation history/metadata follows output retention, not public defaults. |
| `state/cloud_rate_limits_v1.json` | Personal vault: `connections/account-limits` | Explicit account-capacity configuration persists until reset; stale derived provider observations expire after 24 hours. Never store account tokens here. |
| `state/conversation_v1/conversation.json` | Personal vault: `conversations/<id>` | Retain admitted turns until conversation/profile deletion. Includes requests, responses, partial responses, source references, goals, source/save receipts and tool-result excerpts. Deleting a conversation removes its search entries and unshared assets. |
| `state/conversation_v1/archives/<random>.json` (`app/conversation/store.py`) | Personal vault: `conversations/<id>` plus encrypted catalog relationships | Current startup/new-session archives are retained until explicit deletion. Proposed archive retention remains explicit, with no automatic deletion of user history by default. UUID filenames alone do not hide the current plaintext contents. |
| `state/conversation_v1/attachments/<id>/content` (`app/conversation/attachments.py`) | Personal vault: `assets/<id>/original` | Retained input copies, clipboard images and generated image originals follow owning records. Reference counting preserves shared assets; remove when no retained record/draft owns them. External originals are unaffected. |
| `attachments/<id>/metadata.json` | Personal vault: `assets/<id>/metadata` | Filenames, hashes, type, size and source relationships inherit asset retention. No names/hashes are copied into public bootstrap or OS recent-file lists. |
| `attachments/<id>/prepared_v1.json` (`app/conversation/attachment_processing.py`) | Personal vault: `assets/<id>/prepared` | Extracted PDF/Office/text content and dimensions/summaries follow the asset; delete/rebuild with it. No OCR is currently implemented; any later OCR results follow the same rule. |
| `attachments/.pending-<id>/content`, metadata and JSON `.tmp` siblings | Personal vault staging, even when disposable: `transactions/<opaque-id>` | Encrypt before the first disk write. Successful commit removes staging; after unlock, remove unreferenced abandoned staging within 24 hours. Preserve transactions necessary to recover consistent referenced data. |
| Unsent attachment snapshots and `_DraftOwnership` (`app/conversation/attachments.py`) | Personal vault: `drafts/<id>` if retained; otherwise RAM only | Existing cancellation removes owned copies, but ownership tracking is in memory and a crash may leave an orphan. Proposed encrypted ownership survives crashes; expire abandoned drafts after 24 hours. Explicitly saved drafts persist until deletion. |
| Unsent text/composer state, selected skill, active worker buffers (`app/ui/composer.py`, worker) | Disposable runtime RAM by default; opt-in retained drafts in personal vault | No new text autosave is required for v1. Clear on lock/switch/exit. If autosave is later supported, default recovery retention is 24 hours and is encrypted. |
| Generated images, edits, original source links and generation metadata (`app/inference/image_generation.py`, conversation history) | Personal vault: `outputs/<id>` and referenced `assets/` | Retain deliberately saved/admitted outputs until owning records/output are deleted. Interrupted image jobs do not create persistent unowned outputs. Future supported document/audio/video outputs use the same rule. |
| `MessageImageLoader` bounded QImage cache, composer thumbnails, full viewer images, generated partial-frame displays | Disposable runtime RAM; deliberately retained previews in personal vault: `assets/<id>/preview` | Today previews are decoded from attachment snapshots rather than a separate persistent thumbnail cache. Clear jobs, QImages and viewer/composer references on lock/switch. Persistent previews expire with the parent and may be rebuilt. |
| Image parser uses a real content path; sent-image loader uses a pinned descriptor (`app/conversation/attachment_processing.py`, `app/ui/message_images.py`) | Consumers needing audit/adaptation; prefer RAM `QBuffer` access | No plaintext preview files may be created automatically. Path-only third-party integrations stay disabled for encrypted data until a separately documented temporary-file policy is implemented. |
| Image viewer `Save original image` via `QSaveFile` (`app/ui/image_viewer.py`) | Host project / explicit outside-vault export | The selected outside destination remains an explicit export. Exported plaintext and external-editor/OS copies survive lock/deletion; no automatic cleanup. Future protected save must be separately labeled from export. |
| `state/capability_journal_v1.json` (`app/agent/bootstrap.py`, `app/execution/audit.py`) | Personal vault: `recovery/tool-journal` | Existing journal has digests, timestamps, capability/session/call IDs and outcomes, not raw arguments, but is private relational metadata. Unacknowledged unknown outcomes never expire silently; terminal/acknowledged records are purge-eligible immediately once durable conversation reconciliation is verified. No replay of host mutations. |
| Tool results, source-read cache, OpenAI response/reasoning replay items | Personal vault when in conversation history; otherwise disposable runtime RAM | Keep only context needed by retained turns; no independent permanent result cache. Provider objects/source excerpts are never considered public diagnostics. Clear RAM on lock/switch. |
| Cloud attachment input-token/count cache and request preparation | Disposable runtime RAM (`app/inference/openai_backend.py`, `app/conversation/cloud_attachments.py`) | Current hashed/numeric measurements are not a persistent search index. Clear on lock/switch; any later persistent cache belongs in the profile and expires within 24 hours or on parent deletion. |
| `~/.orsi/skills/<name>/SKILL.md`, `references/**`, `.orsi-package.json`; install/remove staging/locks next to that tree | Personal vault: `skills/<id>` plus encrypted catalog | Installed/customized/imported instructions and docs are personal copies. Retain until removal; remove their derived references/index entries, preserving still-shared assets. Installer staging expires after 24 hours; lease/lock files contain only opaque runtime identifiers. Public shipped packages remain separate. |
| Explicit host project `.orsi/skills`, project files, filesystem tool read/write/copy/move/trash outputs | Host project | Keep on host under existing authorization; import into vault only by explicit choice. Adjacent `.orsi-write-*`, `.orsi-copy-*`, `.orsi-move-*` staging belongs to the explicit host operation, not personal-vault persistence. Vault integration must exclude protected application paths/aliases without claiming a host-code sandbox. |
| `%TEMP%/orsi-skill-git-<id>/` clone/materialization/output (`app/runtime/skills/git_installer.py`) | Disposable runtime for public imports; personal vault staging for private material | Current HTTPS Git source is public, but source locations/installation metadata can be private. Cleanup is attempted by the installer. Later encrypted-profile imports must use protected staging/in-memory access; no decrypted private documents in host temp. Leftovers expire after 24 hours when safely identifiable. |
| Shared `PERSONALITY_GUIDANCE` in `app/conversation/personality.py` | Public application default | Keep shipped guidance outside. Personal personality files/overrides have no current dedicated persistent loader; reserve encrypted `personality/` and retain until reset/deletion. |
| Saved prompts/templates, custom instructions, personal workflows/docs, general memory/notes/embeddings | Personal vault: `templates/`, `instructions/`, `documents/`, `memory/`, `indexes/` | General persistent stores for these are not currently implemented, apart from skill documents and conversation goals/context. Do not add features in phase 1. Future user-saved material persists until deletion; derived indexes share the parent's lifetime and are rebuildable. |
| `state/orsi.log` and three rotated files (`app/infrastructure/logging.py`) | Personal vault for any retained app diagnostics: `diagnostics/` | Current rotation is 2 MiB/file plus three backups. SDK/HTTP records are filtered, but traceback paths and skill names/locations can still be personal: this is not a proof of plaintext safety. Proposed profile diagnostic cap is 8 MiB/7 days; never include credentials, prompts, files or raw provider output. Locked startup errors remain transient fixed messages. |
| `state/diagnostics/effective_baseline_v1.json` | Personal vault: `diagnostics/baseline` | Current content-free baseline still contains selected runtime/model IDs, timestamps, source revision and host capacity. It does not store prompts or source bodies. Retain latest successful snapshot only; sanitize before explicit diagnostic export. No new baseline dump before unlock. |
| Local model/server stderr pipe, model contexts, HTTP clients, sessions and session API keys | Disposable runtime RAM | Stderr is consumed through a bounded pipe/classifier, not a dedicated persistent stderr file. Shut down/cancel and release resources on lifecycle boundaries; never spill credentials or personal contexts to runtime files. Paging/crash dumps are a host limitation. |
| `OPENAI_API_KEY` / compatibility `OPENROUTER_API_KEY`, session prompt, in-memory backend fields | Session credential; explicitly saved credentials require separately keyed vault store | Current app can read a host-provided environment key; phase 1 does not read/change it. Later encrypted-profile policy removes implicit persistent fallback. Session credentials expire on provider exit/lock/switch/exit. Explicitly saved API/login/refresh tokens persist until replaced/deleted; older backups may retain them. |
| Repo `state/backups/**`, test fixtures, qualification output, development screenshots | Development artifacts; content-free evidence is disposable runtime, personal snapshots would be personal vault data | Not a production backup implementation. Never copy real conversations/secrets into phase 1 evidence. Synthetic experiments can be disposed as whole owned directories. Existing historical artifacts are not swept/migrated automatically. |
| Application-managed encrypted backups (not yet implemented) | Personal vault ciphertext copies, included in configured usage | Proposed default: at most three managed backups and at most 30 days, evaluated only after a verified new backup; expose policy controls. Independent user copies are never silently rewritten/deleted. Deleted data/previous credentials can remain in retained backups. |
| Windows thumbnails, recent files, clipboard, swap, crash dumps, security tools, external providers/editors | External host/provider boundary | Source audit finds no intentional OS-shell preview invocation for protected snapshots. Phase 1 does not prove zero OS traces. Avoid decrypt-to-path and shell preview by default; clipboard/export are explicit copies, and external retention needs separate user controls. |

## Common deletion and retention rules

The numeric disposable/backup/diagnostic defaults above are the proposed v1
contract, not new behavior enabled by this change. Phase 2 implements enforcement;
phase 3 connects each supported consumer; phase 4 exposes controls and migration.
All expiration uses authenticated encrypted metadata after unlock, not a public
filename/title database. A missing vault never triggers cleanup on a different
location. Locking never requires decrypting a catalog just to locate the profile.

Delete the selected logical records and their catalog/search references in the
same consistent transaction. Remove dependent original/preview/extraction data
only when reference counts reach zero. Keep a protected deletion tombstone until
cleanup finishes so a stale index cannot make removed data visible. Backups have
their own retention and can contain previous records/credentials. Application
deletion does not promise physical erasure on an SSD. Independent exports and
host originals are not owned by the vault and are never swept.

## Audit limits and next wiring points

This inventory covers source-controlled persistence paths, including the
currently unsupported categories so they cannot quietly acquire plaintext
defaults later. It is not a forensic inventory of this user's disk. The later
consumer audit must exercise Qt codecs, Office/PDF processing, skill import,
provider exceptions and OS thumbnail/recent-item behavior with synthetic markers.
Application startup, current preferences, history, tools, prompts, routing,
model profiles and credentials remain unchanged in phase 1.
