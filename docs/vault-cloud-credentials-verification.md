# Saved cloud credential correction

9 October 2026. Started on `codex/vault-cloud-credentials` from local main
`4b9defa` after the user reported a key prompt despite saving a cloud API key in
a personal profile. Only focused tests were run; the full suite remains excluded.

## Reproduction and correction

Four local/portable synthetic UI reproductions failed on the original code:

- Changing the policy dropdown to use saved credentials and pressing Save saved
  the key but left the old Ask policy in force unless Apply was also pressed.
- Cancelling a prior key prompt cached an empty connection session. Saving a key
  under the already-active saved policy did not clear that result, so cloud asked
  again. Replacing an active saved key could similarly keep the previous value.

Save and credential-file import now persist the explicitly selected policy after
validating consent and saving/importing the credential. Denied consent does not
change policy or enable a previously saved credential. Saving/replacing an API
key under the saved policy invalidates only that connection's cached key; the
next cloud attempt loads the persisted value. Ask mode remains intentional and
does not automatically consume saved credentials. Tokens do not substitute for
the chat API key. In-page guidance and save feedback explain these distinctions.

For an already-saved key, restart O.R.S.I, unlock the same encrypted profile, and
open Settings → Personal profile. Choose **Use explicitly saved encrypted
credentials**, press **Apply credential policy**, then select Cloud. Re-entering
the saved key is unnecessary.

## Focused verification

`state/vault-cloud-credentials-release.xml`: **14 passed in 17.22 seconds**.
These new UI/application checks cover the cancelled-prompt reproduction, actual
mode selector, key replacement while cloud is selected, saving with the selected
policy without a separate Apply click, lock/unlock reload, intentional Ask mode,
denied consent, import into a renewed session under both policies, and actual
application composition with its provider-specific connection identifier.

`state/vault-cloud-credentials-regression.xml`: **40 passed in 16.40 seconds**.
The affected existing checks cover credential consent/domains, cloud round trips,
replacement/deletion, failed transitions, independent connection tokens, shared
image credentials through mocked SDK requests, plaintext/session-only startup,
credential-file field cleanup, guidance consent, inference lifecycle and shutdown.

**54 distinct checks passed, with zero final failures, errors or skips.** Initial
reproduction failures are retained separately in
`state/vault-cloud-credentials-repro.xml`; intermediate passing runs are not
counted as additional coverage. All temporary/cache paths are repository-local.
Changed Python files compile and `git diff --check` passes.

All keys and profiles are synthetic. No real key was read, created, changed,
displayed or sent to a provider, and no personal profile was opened or migrated.
Content-free hashes for all eight recorded configuration/state/selected-profile
paths match their pre-change values. Recovery refs/worktree maps and hashes are
under ignored `state/backups/vault-cloud-credentials-20261009/`. Preserve prior
main at `archive/2026-10-09/main-before-vault-cloud-credentials`, commit the bounded
fix, fast-forward local main and remove only its merged local feature branch.
Other worktrees and remote branches remain untouched. Physical SSD, minimum-host,
live-provider and independent security qualification remain deferred.
