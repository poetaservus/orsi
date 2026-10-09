# Personal Vault phase 3: verification record

9 October 2026. Started from verified local `main` `d456cd3` on
`codex/vault-phase3`. The user authorized the next available roadmap phase and
requested necessary tests only. That overrides the usual full-suite requirement.
Real SSD, minimum-machine and independent security qualification remain deferred.
See [the application contract](vault-phase3-contract.md).

## Delivered and remaining scope

The selected profile now owns conversation/history/recovery, private preferences,
model/image selections, attachment and generated-image originals, prepared text
and metadata, personal skills/references, crash journals and minimal diagnostics.
One explicit-consent credential provider serves chat and image generation, with
session-only and encrypted-save modes and no encrypted-profile environment fallback.
Session gates, cancellation/join, cache/view clearing and protected file-tool
exclusions enforce lock and profile boundaries.

Normal startup remains the existing unencrypted behavior until an unlocked profile
is explicitly supplied to application composition. Setup/unlock/selection UI,
migration, user-facing backup/retention controls and automatic maintenance belong
to phase 4, which was not started. No new unsupported memory/OCR/personality or
independent image/login features were introduced.

## Focused evidence

New synthetic application checks run the same consumer pipeline against local and
portable directory simulations. They cover protected namespaces, conversation
goals and archives, actual text/Office/PDF parsing, image previews, explicit export,
draft expiry and shared-asset reclamation, cached preferences and journals,
personal skill install/discovery/reference revocation/removal, both credential
policies, saved key replacement/deletion, token consent, independent connection
sessions, cloud round trips, and real mocked SDK chat/image requests. They also
exercise actual application composition, the Qt lock boundary, ignored late UI
callbacks, active conversation cancellation/join, failed-drain retry, old stream
and path revocation, quota failure and protected tools in both read scopes.

The initial fixture mistakenly supplied text to the engine's bytes-only password
API; correcting the fixture exposed two encrypted skill integration failures.
These were resolved by supplying a real `SkillInstaller` adapter for the existing
reviewed-import API. Forty integration cases then passed in 16.85 seconds.
Additional shutdown checks retain caches until failed drains can be retried and
verify an actual active conversation is stopped before another profile opens.
The cancelled-worker fixture was corrected to accept the existing fixed cancelled
return as well as a revoked-session exception. No acceptance prompts or existing
test expectations were changed.

Existing relevant regression passed **227 cases, with 2 skips, in 17.42 seconds**.
It covers inference lifecycle, conversation persistence, attachment processing,
local document projection, chat previews/viewer/export, skill registry startup,
crash recovery, host access, directory listing/find/search and native image saves.
The two skips are existing directory-symlink escape checks on this Windows host,
where creating those links is unavailable; they are not recorded as passes.
Deterministic traversal and native hardlink exclusions passed separately.

The application/lifecycle release passed **50 cases in 17.78 seconds**, with
zero failures/errors/skips, in `state/vault-phase3-release.xml`. Final verification,
including consumer size admission, stale references, failed cloud transition and
unavailable-profile request rejection, passed **52 cases in 18.01 seconds**, with
zero failures/errors/skips, in `state/vault-phase3-qualified.xml`: 44 new integration
cases and eight existing lifecycle checks.
Across this set and the focused regression, **271 distinct checks passed and two
were skipped**; repeated refinements are not counted as additional coverage.
Focused earlier evidence is in
`state/vault-phase3-integration.xml`, `state/vault-phase3-regression.xml` and the
initial/refinement reports. All temporary state and caches use repository-local
`state/vault-phase3-tests-*` / `state/vault-phase3-cache-*` directories. Test data
and credentials are synthetic; no real API or model calls were made.

## Preservation and deferred qualification

Pre-change refs/worktree maps and content-free configuration/preference hashes
are under ignored `state/backups/vault-phase3-20261009/`. Versioned model/cloud/
agent configuration and existing personal runtime settings are preserved.
Compilation, whitespace checks, startup crypto-import isolation and all seven
pre-change configuration/preference preservation records passed. No
remote publication or changes to other worktrees are authorized or performed.
After verification, preserve prior main, commit this bounded phase, fast-forward
local `main` and remove only its merged local feature branch.

The 2000+ full suite was not run. Physical SSD removal/reconnect, a second host,
minimum-machine memory/performance, real provider/login sessions, OS forensic or
power-loss validation and independent security review remain unrun. The offscreen
Qt checks verify lifecycle behavior, not the upcoming phase 4 setup/migration
interaction or complete accessibility/visual qualification.
