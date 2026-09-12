# Phase 10: approved folder creation

Date: 2026-09-12
Status: first development checkpoint; manual application acceptance pending.

## Scope and authority

- One empty directory at one explicit absolute Windows local-drive path. Its parent must exist.
- No recursive parent creation, overwriting, content writes, moving, deletion, or automatic undo.
- Separate feature gate and WRITE/ASK rules. The executor refuses blanket ALLOW for WRITE calls.
- User input selects the target deterministically. Read/model-selected turns advertise only reads;
  returned file content and previous tool history cannot select or approve a write.
- The UI displays the exact canonical path as plain text. Cancel is the default; closing, Escape,
  expiry, and shutdown cannot approve. Each approval is consumed for one bound call only.
- Request digests bind arguments, capability, path, and parent volume/file identity. The parent is
  checked again after approval; changing the directory at the same path invalidates permission.

## Windows boundary

- Reject UNC/device/network paths, drive-root children, traversal, ADS, reserved names, ambiguous
  trailing characters, bidirectional display controls, redirects, and reparse ancestors.
- Protect the running application and state, standard Windows/boot/recovery/program directories,
  AppData, environment-resolved OS/application roots, and configured additional protected roots.
- Pin ancestors with non-following directory handles and no write/delete sharing during checks
  and creation. The drive root may carry the system attribute; system directories below it remain
  denied. Current account ACLs apply; no elevation, shell, or subprocess is used by the capability.
- Use handle-relative NtCreateFile with FILE_CREATE and DIRECTORY_FILE. A collision fails rather
  than opening/replacing an entry. Check FILE_CREATED and inspect the returned handle before success.
- Preparation does not create anything. It acquires short-lived read handles and records an identity.

## Failure and recovery

- Known pre-creation errors return normalized failures without raw exception details.
- Writes interrupted after dispatch, invalid results, and verification failures are conservatively
  OUTCOME_UNKNOWN. The journal retains review-required state; further calls are blocked.
- If result persistence itself fails, a session latch also blocks operations; the durable RUNNING
  record becomes unknown on restart. No unknown operation is replayed automatically.
- The journal retains digests, not raw target paths or file contents. In-memory approval records
  contain the exact preview path. Conversation text continues to follow existing session persistence.
- There is no in-app recovery acknowledgement or undo yet. Review the requested target manually
  before an explicit administrative journal acknowledgement. Do not clear the journal to bypass review.

## Verification and remaining limits

- 342 passed, 14 skipped in the full Windows suite; 44 new Phase 10 tests. Tests use temporary
  targets and fake inference, but real native directory creation and real Qt worker/dialog signals.
- Tested create, deny, Escape, expiry, shutdown, missing/existing targets, collisions during approval,
  parent replacement, junction rejection, write isolation, interruption, and journal/restart failures.
- Manual app acceptance, live-model conversation after a write, removable-drive/filesystem diversity,
  denied-ACL variants, and fresh packaging remain release gates. Preflight native calls are cooperative,
  not force-killable; unusual filesystem drivers can stall outside the execution deadline.
- Protection covers standard and explicitly configured locations, not discovery of every application
  or service installed in custom folders. Broader service/application inventory is still required
  before unrestricted host-write release. NTFS was exercised; other local filesystem identities need
  dedicated validation. A privileged external process remains outside this protection boundary.
- Empty-folder creation is manually reversible; automatic rollback is intentionally absent because
  another process could populate the folder after creation. Later trash/undo needs its own design.

## Native API references

- [NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile)
- [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
- [GetFileInformationByHandle](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileinformationbyhandle)
