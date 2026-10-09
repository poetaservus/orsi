# Personal Vault phase 4: setup, migration and everyday controls

Implements roadmap phase 4 items 1–8 and section 4.1. Both local and portable
encrypted profiles use the existing phase 2 format and phase 3 consumers.
No prompts, routing, model profiles, sampling or acceptance prompts change.

## Setup and startup

Open **Settings → Personal profile → New profile**. Choose local computer or
portable drive, a new directory, encrypted/unencrypted storage and, for encryption,
a matching password, growing quota and credential policy. Local defaults use
`%LOCALAPPDATA%/O.R.S.I/profiles/`; portable defaults use `profiles/` beside the
application. The latter is ignored by Git. Neither mode reserves the full quota.
Use **Select existing** to choose another profile without merging or importing.
An existing unencrypted installation remains available through **Use current
unencrypted storage**. New unencrypted profiles keep their own state and skills.

The public `state/profile_locator_v1.json` contains only version, location,
relative-location flag, storage mode, encryption flag and stable profile ID.
Portable locations inside the application tree follow that tree across drive
changes; other relocated locations can be selected explicitly. Passwords,
recovery keys, credentials, full preferences and personal contents never belong
in bootstrap. An unreadable selection fails closed rather than opening legacy
history. A different profile at the same locator needs explicit selection.

An encrypted selection starts with unlock/recovery and restore controls before
composing personal consumers. Composer and private Settings pages are disabled.
Ordinary unconfigured startup remains quiet. An unencrypted selection opens
without a password and takes an exclusive ownership lease; its data is plaintext.

The locked shell identifies itself as **Locked** and shows **Unlock your personal
profile** instead of a default welcome that could resemble old settings. Personal
greeting/preferences load only after unlock. Creating a new profile does not
implicitly migrate legacy preferences.

After successful password/recovery unlock, the bundled `orsi_start.png` covers
the previous window's position and size while personal services and the full UI
are composed. The artwork fills the area with its proportions preserved and
centered cropping when needed. It is painted before blocking initialization,
has no private content, and closes when the replacement view is shown (including
the locked error view if initialization fails). The image lives with the UI
assets and follows portable copies; no Desktop path is used at runtime.

Desktop startup admits one owner per application directory. Repeated launches
activate its current window and exit before composing another profile/backend.
Separate application directories remain independent; the engine's profile lease
still prevents concurrent unlock of one profile. The ignored public desktop lock
contains only runtime ownership metadata, separately from the profile locator.

## Everyday controls

The profile page shows location/mode and separate application/runtime, model,
personal usage/quota and disk-free figures. It exposes quota changes, manual
lock, optional idle lock (off by default), password change, optional recovery key,
managed/independent encrypted backup, restore and verified relocation.

Password changes rewrap keys. Recovery generation explicitly displays the new
key and offers an outside-vault export; keep that copy accessible independently
of the vault and its disk. Generation replaces the current recovery key. Recovery
can be disabled. Older independent backups can still accept previous passwords
or recovery keys; there is no reset backdoor. Restore accepts the backup's
password or recovery key, including from the locked screen.

Relocation drains old workers before making/authenticating a complete encrypted
snapshot. It selects the verified destination in a locked state. Restore verifies
and opens a new independent destination. Both retain the source and its independent
backups. They do not synchronize, merge or automatically remove source copies.

Lock and profile changes revoke old handles, stop/join work and clear views,
composer, previews, credential inputs and private dialogs. Failed drains keep
their hidden owner alive for an explicit retry while vault keys are released.
Migration reload drains and revokes consumers before rebuilding the same unlocked
profile, so imported preferences are used without asking for its password again.
Retiring a window disables it and shuts down its activation/sound callbacks before
replacement. Its stale actions cannot unlock or replace the new active session.
A failed action that leaves the current session intact keeps that existing view
and consumers, displaying the error without composing duplicates.
Locking rejects pending credential dialogs and prevents their obsolete callbacks
from binding credentials to a retired view.

## Credentials

Cloud chat and native image generation share the existing credential provider.
**Ask whenever cloud is selected** is the default. **Use explicitly saved encrypted
credentials** loads only the selected provider connection's previously saved value.
Changing policy or accepting storage recommendations does not save a key.
Use the masked value field and separate save-consent checkbox to save/replace an
API key or supported login/access/refresh token. Deleting ends the connection
session and removes the chosen value; provider-side revocation is separate.

**Save / replace credential** and credential-file import also apply the policy
currently selected in the dropdown. Choose **Use explicitly saved encrypted
credentials** to reuse a saved API key without another key prompt. If a key is
already saved, select that policy and press **Apply credential policy**; no
re-entry is needed. **Ask whenever cloud is selected** deliberately continues
asking even when a credential has been saved. Settings explicitly shows whether
an API key is saved for this connection and whether automatic use is enabled.
In Ask mode with a saved key, the Cloud decision offers **Use saved key**, **Enter
a different key**, or Cancel. Choosing Use saved key explicitly enables the saved
policy for that connection; other choices leave the policy unchanged. No key
value is displayed. Save feedback also identifies this choice. Saving/replacing
an API key clears a previously missing or stale cached
key under the saved policy, so the next cloud attempt loads the saved value.
Cloud chat requires an API key; the other token types remain separate.

Credential-file import accepts a selected JSON file containing the chosen
`api_key`, `login_token`, `access_token` or `refresh_token` field. It requires
separate encrypted-save consent, does not display/log its value, and writes only
to the separately keyed credential domain. Unknown configuration shapes are not
automatically interpreted. No independent login/provider feature is introduced.

Desktop unencrypted connections, including current legacy storage, use an
ephemeral session-only provider and explicitly suppress environment-key lookup.
Leaving cloud, changing profile or exiting releases its key. Direct legacy
backend API callers retain their existing opt-in environment behavior.

## Migration and originals

**Migrate selected personal data** presents unchecked category choices and an
optional explicit replacement choice. Choose the source application directory
and personal skills directory. Close other source instances before importing
or cleaning originals. Source snapshots reject links/shared hardlinks, validate
supported history/attachment relationships and skill packages, and are checked
again for changes before publication. No source is moved during import.

| Choice | Imported material |
| --- | --- |
| Preferences | Existing greeting/UI preferences and model/image/account-limit selections |
| History | Conversations/archives, generated-image and attachment originals, metadata and prepared text/previews |
| Recovery | Existing capability crash journal |
| Skills | Main instructions and supported Markdown reference documents |
| Personality | Existing files under the personal `personality/` directory; supported greeting remains part of preferences |
| Templates | `templates/` and `instructions/` |
| Documents | `documents/` |
| Memory | Existing `memory/`, `context/` and `indexes/` files |
| Drafts | Existing `drafts/`, `recovery/` and interrupted conversation staging/cache files |

These choices preserve supported data and allow explicit copies of existing
personal files; they do not introduce unsupported memory, OCR, personality
editing, embeddings or new media features. Shipped public defaults and host
projects remain outside. Active source history becomes saved archives rather
than replacing the destination's live conversation. Attachment originals,
prepared records and shared relationships publish in the same catalog batch.
Imported orphan drafts/staging expire after 24 hours. Files are bounded to
512 MiB; one personal-data batch is bounded to 1 GiB, in addition to engine and
consumer limits. Large batches can require substantial RAM; minimum-host
qualification remains pending.

All selected records are read back and checked before an encrypted receipt is
marked verified. A failed/incomplete receipt cannot authorize original cleanup
and expires after 24 hours. Source paths, private names and digests stay encrypted.
Conflicting destinations require explicit replacement. Full settings/cache
consumers reload after import; no unrequested plaintext fallback is created.

**Review retained originals** lists exact remaining outside locations from verified
imports. Select specific originals for separate cleanup. Recheck the protected
copies and originals first. Regular files are removed by their verified Windows
handle while write/delete access remains locked. Credential JSON cleanup removes
only the selected imported field and atomically replaces the configuration;
close editors/source applications beforehand. Empty folders and unrelated package
metadata are left alone. Interrupted multi-file cleanup may be partial; verified
vault copies remain, and missing/cleared originals are not reported as retained.
Deletion does not guarantee physical erasure.

## Saved material, retention and guidance

The existing attachment picker labels protected imports as copies that leave
external originals unchanged. Personal skill installation identifies its vault
destination. Image viewers distinguish **Store in vault** from **Export outside
vault**. Protected image saves atomically promote any draft and add a retained
owner, so composer abandonment or expiry cannot remove the saved image. The
saved-record list opens archived text/images and imported records, offers explicit
outside export and deletes selected saved records with unshared dependencies.
The active conversation continues to use its existing clear/new-session control.

Recommendations explain protection of stored copies while locked and appear at
save/import decisions. The profile preference dismisses them persistently; disabled
encryption has no vault recommendations. Outside exports remain deliberate copies
after lock or deletion. Protected operations fail visibly when locked, unavailable
or full; errors offer unlock, reconnect/retry or quota/data management. They never
silently write plaintext. Host/provider copies are outside vault protection.

Unsent attachment drafts have a 24-hour lifetime. **Clean expired drafts and caches**
applies expiry and managed backup retention; **Delete abandoned attachment drafts**
removes uncommitted copies from earlier sessions while preserving current composer
drafts and retained/shared assets. The page exposes managed backup count/age policy
(default three copies/30 days) and explicit saved-record deletion. Independent
backups, outside originals and exports remain unless separately removed, and can
retain deleted material or previous credentials.

The Windows dependency extra now includes pinned PyNaCl 1.6.2. This checkout's
bundled runtime received the already available verified package and its dependencies;
existing runtime files/settings were not replaced. Ordinary imports do not load
crypto before an encrypted operation. See [focused verification](vault-phase4-verification.md)
for passed checks and deferred physical, live-provider and security qualification.
