# Git layout and baseline hygiene

## Reproduced workflow fixes, 19 October 2026

`codex/workflow-reproduction-fixes` starts from clean local main `2f94758`.
It repairs source-bound image follow-ups, contradictory Excel read-failure
reporting, missing local-stop catalogs and a stale local-stop test expectation.
It also waits for pinned owned descendants to finish exiting before reporting
worker cleanup complete, after a native browser-preview reproduction proved
that zero active job accounting could precede a process object's exit signal.
Word uncertain-operation feedback and encrypted provider diagnostics now retain
bounded failure evidence without retrying or claiming an uncertain write passed.
See [changes, actual workflow qualification and limits](workflow-reproduction-fixes.md).

Final native suite: 4,578 passed, one failed, 82 skipped and 15 passing subtests.
The remaining failure is the documented intermittent skill-fixture directory
rename denial; no owned file-handle leak was established. The suite is not called
clean. Focused cleanup tests and 30 native preview probes qualify the proven
descendant-exit fix; controlled image, Word save/reopen and npm API workflows
pass with their recorded scope limits. Historical streaming and Word failures
are not claimed resolved by those successful repeats.

The user authorized fixes after the read-only investigation. Acceptance prompts,
core prompts, model profiles/sampling, context policy and user settings remain
unchanged. Prior main is preserved at
`archive/2026-10-19/main-before-workflow-reproduction-fixes`. After verification,
commit the bounded changes, fast-forward local main and remove only this merged
feature branch. Other worktrees, historical/unmerged refs, user documents and
remote refs remain untouched. The running user app is preserved.

## Excel execution reliability, 18 October 2026

`codex/office-mcp-reliability` starts from clean local main `0acc369`. It repairs
native Excel mutation/preparation deadlines, dispatch-time budgets for shared
save/revert tools, formula-result verification after same-patch recalculation,
plain line-chart palette verification, and content-free Excel failure evidence. See
[reproductions, focused verification and limits](office-excel-reliability.md).

158 distinct deterministic/owned-stdio checks and the disposable native 200-cell,
1,000-cell and four-chart gates pass. One opt-in Word gate remains skipped;
native cleanup diagnostics are recorded separately. Only focused tests are used. Preserve prior
main at `archive/2026-10-18/main-before-office-mcp-reliability`, commit, fast-forward
local main and remove only this merged feature branch. Other worktrees, user
settings/documents, historical/unmerged tips and remote refs remain untouched.
No full suite or live-model acceptance is claimed.

## Office read reliability, 18 October 2026

`codex/office-read-reliability` starts from clean local main `2a0c399`. It yields
slow native reads before the unchanged deadline, budgets normalized result
defaults, aligns native Word preflight/revision guards, and persists safe read
failure details. See [changes, proof and limits](office-read-reliability.md).

Only focused tests run: 28 deterministic/owned-stdio cases and four native read
gates pass, with zero failures/skips. The 1,000-cell Excel read completes across
13 cursor pages at production defaults; the first native Word read passes.
Native COM/RPC cleanup diagnostics remain recorded; all owned processes release.
No full suite, live-model run, user-document/settings change or remote operation
is made. Preserve prior main as
`archive/2026-10-18/main-before-office-read-reliability`, commit, fast-forward local
main and remove only this merged branch. Other worktrees/refs remain intact.

## Focused Word failure fix, 18 October 2026

`codex/word-failure-fix` starts from clean local main `6ece427`. It restores
compose geometry guidance and repairs the stale schema/finalization fixtures
behind the audit's three Word failures. Eight essential focused checks pass;
six in-memory mutations demonstrate the relevant assertions. The accepted Office
manifest and budget ceilings remain unchanged. See [scope, proof and limits](office-word-failure-fix.md).

The user requested only focused tests, so no full suite, native Word gate or
live-model run is made. Earlier non-Word blockers remain unresolved. Preserve
prior main as `archive/2026-10-18/main-before-word-failure-fix`, commit the bounded
change, fast-forward local main and remove only its merged branch. Other
worktrees/settings and remote refs remain untouched.

## Deep test and legacy-code audit, 18 October 2026

`codex/deep-test-audit` starts from clean local main `220263c`. Qualified
reachability/history review removes five retired definitions and the obsolete
Settings drag translation entry. It repairs plain-chat failure, agent picture
source binding and owned-inference handle release after polling errors. Existing
tests remain intact; failure injection and targeted mutation demonstrate their
value. See [the audit, reproduced bugs and remaining gates](deep-test-audit-2026-10-18.md).

The focused selection passes 273 tests with two opt-in Word gates skipped.
The localization selection records 47 failures and 26 passes: all catalogs lack
the pre-existing local-stop explanation. Retired-source cleanup preserves every
other catalog message and verifies regenerated translation readback; it does not
hide that validator failure. The complete native suite records **4,480 passed,
53 failed, 79 skipped and 15 passing subtests** in **1,609.97 seconds**. Four of
the six additional failures reproduce; cancellation and vault-rename cases pass
unchanged in isolation but remain unexplained native failures. Word guidance and
stale fixture/exception assumptions are documented without weakening assertions.
The interrupted first run remains separate; the full suite is not called clean.
No live model/provider/Office quality gate
or user-document edit is made. Prompts, routing, accepted model profiles, sampling
and context policy remain unchanged.

Content-free ref/worktree inventories and ignored test/diagnostic evidence are
under `state/deep-test-audit/`. Prior main is preserved as
`archive/2026-10-18/main-before-deep-test-audit`. After verification, commit the
bounded change, fast-forward local main and remove only its merged feature branch.
Other worktrees, historical/unmerged tips, private settings and remote refs remain
preserved. No remote operation is authorized.

## Word COM stabilization, 18 October 2026

`codex/word-com-stability` starts from clean local main `be5d21d`. It corrects
inherited Word pagination, closes final two-column flow for balancing, verifies
exception outcomes without replay, preserves confirmed saves through failed
authority refresh, detaches STA exceptions, and persists content-free operation
diagnostics. See [findings, qualification and limits](office-word-com-stability.md).

Only essential focused checks run: 200 distinct deterministic cases and three
disposable native gates. The accepted MCP manifest is unchanged. No full suite,
live-model acceptance, user-document edit, settings/model/prompt change or remote
Git operation is made. Historical incident arguments/HRESULT remain unavailable;
reproduced defects are not attributed to that run without its evidence. Preserve
prior main as `archive/2026-10-18/main-before-word-com-stability`, commit, fast-forward
local main and remove only this merged branch. Other refs/worktrees remain intact.

## Word revision workflow, 18 October 2026

`codex/word-revision-workflow` starts from clean local main `a862446`, preserving
that save fix. It binds Word authoring, page/image inspection, correction findings
and save receipts to semantic revisions; gates further edits on concrete defects;
detects recurring revisions; and finishes after clean review/current save.
See [cause, bounded changes and essential qualification](office-word-revision-workflow.md).

229 distinct deterministic checks pass (225 combined, then 33 focused with overlap),
plus a separate isolated native Word gate with scripted image-capable responses,
save/reopen and released owned resources. No live-model acceptance or full suite
was run. The user's computers.docx and article task remain untouched. Excel,
shared budgets, model settings, routing, core/acceptance prompts and context policy
are unchanged. Recovery refs/worktrees and a verified complete-history bundle are
under ignored `state/backups/word-revision-workflow-20261018/`; prior main is
`archive/2026-10-18/main-before-word-revision-workflow`. Commit, fast-forward local
main and remove only the merged bounded branch. No remote operation is authorized.


## Word save finalization, 18 October 2026

`codex/word-save-finalization` starts from clean local main `fdba4a1`. It narrows
the model's save choices only for Word, explains Word save validation failures,
and preserves historical save evidence without changing Excel or retry limits.
See [scope, evidence and essential checks](office-word-save-finalization.md).
The focused selection passes 191 tests; no full suite, real Word COM gate or paid
model run is made. Prior refs/worktrees and verified history bundle are retained
under ignored `state/backups/word-save-finalization-20261018/`. Preserve prior main
at `archive/2026-10-18/main-before-word-save-finalization`, commit, fast-forward
local main and delete only the merged feature branch. No remote action or change
to user documents/settings or another worktree is authorized.

## Local-stop reporting, 17 October 2026

`codex/local-stop-reporting` starts from local main `45c4240`. It distinguishes
local recovery stops from provider incompleteness in conversation presentation
and retains content-free terminal/receipt evidence after verification exceptions.
See [cause, focused checks and uncertainty](local-stop-reporting.md). No renewal
policy defect was demonstrated; save/no-op exclusions and actual-edit renewal
remain protected. 98 focused checks pass; an unrelated existing plain-chat failure
and sandbox bridge failures are recorded separately. No full suite or paid live
run was made. Preserve prior main and the ignored recovery bundle, commit,
fast-forward local main and delete only the merged feature branch. No remote
action, user-document edit or other-worktree change is authorized.


## Native Word pictures and column sections, 17 October 2026

`codex/word-pictures-columns` starts from clean local main `528c9e8`. It adds
immutable local/attachment PNG/JPEG registration, embedded native pictures,
one/two-column sections and column breaks, with exact approval, native readback,
save/reopen and owned recovery. Historical pages/blocks, prior read-recovery
corrections, prompts, model settings, routing and retry limits are preserved.
See [scope, limits and qualification](office-word-pictures-columns.md).

Only focused checks are run: 259 distinct deterministic checks and separate real
Word gates. The final unchanged live fixture produces a saved five-page DOCX
with native columns 1/2/1, two embedded original diagrams and an editable table.
All pages are inspected; the model turn remains incomplete and word count/layout
quality fail acceptance. This is not recorded as a clean live pass. Windows
sandbox/teardown evidence is recorded separately from product failures.

Recovery refs/worktrees and a verified complete-history bundle are under ignored
`state/backups/word-pictures-columns-20261017/`. Preserve prior main at
`archive/2026-10-17/main-before-word-pictures-columns`, commit, fast-forward local
main and remove only the merged bounded branch. Preserve private settings,
other worktrees, historical/unmerged tips and remote refs. No remote action or
full suite is authorized. Desktop/report.docx remains unchanged.

## Office read recovery, 17 October 2026

`codex/office-read-recovery` starts from clean local main `183d660`. It renews
successful initial Office reads only after matching settled document changes,
preserves unchanged-call stops, and retains bounded failure/plan diagnostics in
profile storage. Exact approval, recovery, prompts, model settings and retry
limits retain their existing policies. The historical failed read remains
unidentified; see [scope and verification](office-read-recovery.md).

Only 95 essential focused checks were run and passed, including the actual
owned bridge/executor path with synthetic Word state and scripted responses.
No live model/native Word document acceptance or full suite was run. No user
document was edited. Recovery inventories and a verified complete-history bundle
are under ignored `state/backups/office-read-recovery-20261017/`. Preserve prior
main at `archive/2026-10-17/main-before-office-read-recovery`, commit, fast-forward
local main and remove only the merged bounded branch. Preserve other worktrees,
historical/unmerged tips, private settings and all remote refs.

## Word complete-body pages and live proposal qualification, 16 October 2026

`codex/word-compose-complete-body` starts from clean local main `b79137d`.
It replaces the model-facing content-free break alternative and optional page
flag with required complete page groups, while retaining historical/native
block plans, exact approval and guarded recovery. Real GPT-6 Luna investigation
also demonstrates and repairs invalid justified-alignment XML and overly strict
standard-spacing readback. See [the evidence and live qualification](office-word-complete-body.md).

The final deterministic selection passes 273 checks. The unchanged live proposal
request completes through the configured GPT-6 Luna/ConversationService/Office
path, including complete generated body/table calls, approval, rendering and
save. The saved editable proposal has exactly two A4 pages; both were visually
inspected and pricing/payment arithmetic checked. The original report is unchanged.
Failed intermediate attempts, the corrected test-harness read scope, Windows
environment evidence and the unavailable historical raw response remain explicit.
No local model or full repository suite was run. Model settings, routing, core
prompts, acceptance request and retry limits retain their existing policies.

After focused/native qualification, commit the bounded change, preserve prior
main at `archive/2026-10-16/main-before-word-complete-body`, fast-forward local
main and remove only the merged feature branch. Preserve private settings,
other worktrees, historical/unmerged tips and every remote ref. No remote action
is authorized. Content-free evidence is under ignored `state/word-complete-body/`;
isolated live artifacts are in this task's visualization directory.

## Word empty-plan investigation, 16 October 2026

`codex/word-compose-empty-plan` starts from clean local main `c50f731`.
The reported rejection occurs before Word dispatch when the submitted body has
no paragraphs or tables. A baseline reproduction confirms that an optional
page-break discriminator allowed empty objects in both advertised and provider
schemas. The change requires that discriminator, explains empty/break-only
plans with content-free structural counts, and preserves older failed-call
history without granting live execution authority. See
[the evidence, qualification and unresolved live gate](office-word-empty-plan.md).

The 214 focused checks passed and the accepted schema remains within its
existing budget. The full suite was not repeated after the user's stop request.
The actual failed call is unavailable because the user cannot access that chat;
empty objects versus explicit breaks cannot be distinguished. The live proposal
acceptance case remains unqualified. Commit, fast-forward local main, and remove
only the merged bounded branch. Preserve private settings and other worktrees;
no remote operation is authorized.

## Full-suite repair, 16 October 2026

`codex/full-suite-repair` starts from clean local main `cdd7f5b`. It repairs
missing Word approval-title translations, settings popup sizing/painting, and
Windows skill cleanup/publication races. Portable font and cold-start UI
fixtures retain their behavioral assertions. See
[the repair and qualification record](full-suite-repair.md).

The affected installer/rollback/ownership/state selection passed **182 tests**.
The two intermittent cases passed 30 and 200 repeated runs, and five native
held-reader/identity regressions were added. Native shell fixtures now observe
actual readiness and completion; 66 affected checks pass. The final completed
active-checkout suite recorded 4,339 passed, one failed and 70 skipped, plus 15
passing subtests. The sole failure was an intermittent Windows directory-rename
denial in unchanged reference-reader validation; its 73-test module passed
unchanged on recheck. The user requested stopping further full runs. The full
suite is not claimed clean. Initial failed runs and separately skipped live
gates remain explicit in the repair record. Model profiles, prompts, capability routing/permissions,
sampling, context policy and private runtime settings are unchanged.

Pre-change inventories and a verified complete-history bundle are retained under
ignored `state/backups/full-suite-repair-20261016/`. Prior main is preserved at
`archive/2026-10-16/main-before-full-suite-repair`. After verification, commit,
fast-forward local main and remove only the merged local feature branch. Preserve
other worktrees and historical/unmerged tips. No remote publication or cleanup
is authorized by this task.

## Word page breaks and failed-worker cleanup, 16 October 2026

`codex/word-page-breaks` starts from main `e240296` in the active checkout,
preserving the pending full-suite repair. It normalizes redundant report page
separators before approval and finishes invalidated Office worker cleanup before
returning failed receipts. Original uncertain-write classification and no-retry
protections remain. See [scope, failures and qualification](office-word-page-breaks.md).
The final focused Office selection passes 148 checks; the native Word report
gate passes with production settings, three pages, genuine editable text/table,
rendering, recovery, save/reopen and owned-process release. Its three PNGs match
the visually reviewed pages exactly. The full-suite results and unresolved
Windows rename denial are recorded above. No further tests are required by this
wrap-up after the user's stop request.

Commit Word and full-suite repairs separately, then fast-forward local main to
both qualified changes and remove only their merged feature branches. Preserve
all other worktrees, historical refs and private settings. Recovery is retained
under ignored `state/backups/word-page-breaks-20261016/`; no remote action is
authorized.

## Word report confirmation, 16 October 2026

`codex/word-write-completion` starts from main `d7b5688` in the isolated Word
checkout. It fixes the reproducible ten-second production confirmation cutoff
for full report composition, aligns SDK/client/outer budgets and preserves
already settled receipts at the wait boundary. Genuine uncertain outcomes still
require review. See [reproduction and qualification](office-word-write-completion.md).
The native gate now uses production call settings. Pending full-suite repair,
private settings, prompts/model policy and existing write protections are preserved.

After qualification, commit, fast-forward local main and remove only the merged
feature branch. Preserve other worktrees and historical/unmerged refs. Recovery
is under ignored state/backups/word-write-completion-20261016; no remote action
is authorized.

## Word composition validation, 16 October 2026

`codex/word-compose-validation` starts from local main `363b271` in the existing
isolated Word checkout. It exposes existing report composition constraints in
the schema/tool description and provides bounded field-specific diagnostics
before any native write. See [scope and qualification](office-word-compose-validation.md).
The unchanged prompt and write/approval/recovery/loop policies remain in force.
The active checkout's pending full-suite repair and private settings are preserved.

After qualification, commit, fast-forward local main and remove only the merged
feature branch. Retain the recovery inventory/bundle under ignored
state/backups/word-compose-validation-20261016. Preserve other worktrees and
historical/unmerged refs; no remote operation is authorized.

## Native Word report authoring, 16 October 2026

`codex/word-authoring` starts from local main `cdd7f5b` in a separate checkout.
It adds native report body composition, typography/layout, tables, running
matter, page fields and actual page rendering through the existing guarded
Word connection. See [scope and qualification](office-word-authoring.md).
The active checkout's unfinished full-suite repair is preserved. Qualification
passed 210 focused checks and three native Word gates. The full run recorded
4,215 passed, 51 failed and 99 skipped; 50 failures match the prior baseline,
and the additional unchanged discovery rename failure passed its 32-test recheck.
The full run is not claimed clean. Separate provider/model gates remain unrun.
Recovery inventories and a verified complete-history bundle are under ignored
state/backups/word-authoring-20261016; prior main is archived before integration.

After qualification, commit the bounded change, fast-forward local main and
remove only its merged feature branch. Preserve other worktrees, unmerged tips
and private settings. No remote publication or branch cleanup is authorized.

## Typesetter Flagship package, 16 October 2026

`codex/typesetter-flagship` starts from clean local main `0dfe35b`. It adds an
optional MIT Word instruction package and primary-source research, following
the user's frontend/analyst flagship architecture. Twelve progressive references
cover typography, composition, anti-slop and anti-premium-slop, editable Word
structure, preservation, pagination, accessibility, and evidence. The package
does not install itself or add Word tool capabilities. See
[the research and qualification record](typesetter-flagship.md).

Frontmatter/link/budget checks and isolated native import/reference roundtrip
pass; 84 bounded pages reproduce every reference byte. The affected selection
passed **249 tests**. The full native Windows run recorded **4,226 passed,
48 failed, 67 skipped**, and **15 passing subtests**, in **1,605.49 seconds**.
Forty-seven failures reproduce an unchanged baseline catalog coverage defect
(missing `Edit`); one installer CLI I/O failure passed unchanged in isolation.
An intervening installer-module recheck's two other I/O failures also passed
their targeted recheck; their cause remains unresolved. The full suite is not
claimed clean. Skipped live gates and unrun document-quality evaluations remain
separate from package verification. No application code, model profiles,
prompts, routing, tools, context policy, or private settings are changed.

Inventories, pinned research, and validation evidence are retained under ignored
`state/backups/typesetter-flagship-20261016/` and `state/typesetter-flagship-*`.
Prior main is preserved at `archive/2026-10-16/main-before-typesetter-flagship`.
Commit the bounded package, fast-forward local main, and remove only the merged
feature branch. Preserve all other worktrees and historical/unmerged refs. No
remote publication or remote cleanup is authorized by this task.

## Remaining Office MCP Word actions, 16 October 2026

`codex/office-word-actions` starts from clean main `3d984d7` and completes the
pending bounded Word insertion, paragraph-style and existing-table actions.
Structured table/style discovery, exact native ranges, direct-format
preservation, approved dispatch, guarded recovery and separate saving share
the existing connection. See [scope and qualification](office-mcp-word-actions.md).

The final essential selection passed 301 checks; both synthetic native
UI/bridge/preservation gates passed, with released owned processes and no forced
fixture termination. No provider calls or user document edits occurred. The
full suite and provider/second-host gates were not run per the user's instruction.
Model profiles, prompts, routing, sampling, context policy and private settings
remain unchanged. PowerPoint mutations remain phase 6 work.

Inventories are retained under ignored
`state/backups/office-mcp-word-actions-20261016/`. Prior main is preserved at
`archive/2026-10-16/main-before-office-word-actions`. Commit, fast-forward local
main and remove only the merged feature branch. Preserve other worktrees,
historical/unmerged tips and all remote refs.

## Office MCP Word replacement slice, 16 October 2026

`codex/office-mcp-phase5` starts from clean main `33328c8` and implements the
initial qualified Word replacement slice through actual approval UI, production
stdio, native readback, guarded restoration and separate Save/Save As. Remaining
Word actions and PowerPoint mutations stay unavailable. See
[scope, native findings and focused evidence](office-mcp-phase5.md).

The final focused selections passed 339 checks, including 287 core checks,
21 connection/permission checks and 31 filesystem-report checks. The report
module's initial sandboxed failure remains separately recorded. The final native Word
UI/bridge/persistence gate passed with released owned processes and no forced
termination. Other focused connection results are retained in the phase record.
The full suite and live provider/second-host gates were not run per the user's
essential-tests-only instruction. Prompts, model profiles, routing, sampling,
context policy and private settings remain unchanged.

Pre-change inventories are under ignored `state/backups/office-mcp-phase5-20261015/`.
Prior main is retained at `archive/2026-10-15/main-before-office-mcp-phase5`.
Commit, fast-forward local main and remove only the merged local feature branch;
preserve other worktrees, historical/unmerged tips and all remote refs.

## Analyst Flagship package, 15 October 2026

`codex/analyst-flagship-package` starts from clean local main `d582731` and adds
the user's Desktop `analyst-flagship` v1.1.2 under `skills/analyst-flagship`.
It is an optional instruction-only package, retaining source/license notices;
it does not install itself or change the application's runtime behavior.
The update strengthens initial layout, defined performance status, neutral
missing comparisons, partial-period labels and numeric presentation.

Frontmatter/link/budget checks and an isolated native import/reference roundtrip
pass. Live dashboard/model behavior remains for the user's installation test;
the full suite was not run under the essential-checks-only instruction.
Inventories and the Desktop snapshot are retained under ignored
`state/backups/analyst-flagship-publish-20261015/`. Prior main is preserved at
`archive/2026-10-15/main-before-analyst-flagship-package`. Fast-forward main and
publish only main under the user's explicit merge-and-push request; preserve
other worktrees and historical/unmerged refs.

## Native Excel dashboard objects, 15 October 2026

`codex/excel-dashboard-objects` starts from clean local main `adc5d0f`. It adds
native chart, shape, PivotTable and slicer creation plus solid cell fills through
the existing guarded Excel edit contract. Complete same-session snapshots,
document identity, approvals, uncertain-outcome handling and owned recovery apply.
Object discovery and GETPIVOTDATA support usable filter-linked dashboards. A
narrow read-only history compatibility adapter preserves earlier Office call
evidence after the additive schema change. See
[the feature and qualification record](excel-dashboard-objects.md).

The final essential connector/approval/protocol selection passed **304 checks in
69.40 seconds**. Both native synthetic direct/stdio gates passed in **35.01
seconds**, qualifying construction, actual slicer filtering, persistence,
recovery and clean process release. The full suite was not run per the
user's explicit essential-tests-only instruction. Provider/model, second-host
and large/OLAP-workbook gates remain separate. Model settings, prompts, routing,
context policy, private preferences and installed skills are unchanged.

Pre-change refs/worktree/status inventories are retained under ignored
`state/backups/excel-dashboard-objects-20261015/`. Prior main is preserved at
`archive/2026-10-15/main-before-excel-dashboard-objects`. Commit, fast-forward
local main and remove only the merged feature branch after verification.
Other worktrees and remote refs remain intact.

## Office dashboard patches and read packing, 15 October 2026

`codex/office-dashboard-patches` starts from clean local main `2b771b9`. Compatible
overlapping value/formula/format assignments compose into one write per cell;
conflicting assignments still reject before writes. Bounded same-workbook
formula references bind retained worksheet identities, including for approval
and restoration. Used-range row matrices reduce a 288-cell read from nine to
three model/tool exchanges. Stop reports retain successful Office operations.
No model/system prompt, routing, context, schema, manifest, preference or approval
changes are introduced. See [the repair record](office-dashboard-patch-repair.md).

The final necessary selection passed **315 checks in 54.09 seconds**. One native
synthetic dashboard qualification passed in **15.94 seconds**, including source
updates, linked KPIs, compatible formatting, restoration and owned-process
release. It made zero provider requests and changed no user workbook. An initial
native finding corrected recalculation during patch restoration; its uncertain
test journal was preserved. Manifest, budget, compilation and whitespace checks
pass. The full suite and live model/latency gates were not run per the user's
focused-test instruction.

Inventories are retained under ignored `state/backups/office-dashboard-patches-20261015/`.
Preserve prior main at `archive/2026-10-15/main-before-office-dashboard-patches`,
commit, fast-forward local main and remove only its merged feature branch.
Other worktrees, private settings, historical/unmerged tips and remote refs remain intact.

## Office workbook range repair, 15 October 2026

`codex/office-range-discovery` starts from clean local main `ed4aa49`. The existing
Office reader discovers worksheet extents and reads complete used ranges through
bounded pages. A turn-local completion check prevents a started full-range read
from being reported complete with unread pages. Office edit descriptions expose
the supported subset; semantic-limit stops retain the underlying settled Office
error. No native worksheet creation, cross-sheet formulas, approval bypass or
model/prompt/routing/context changes are introduced. See
[the repair record](office-workbook-range-repair.md).

The necessary affected selection passed **215 checks in 42.76 seconds**. The
final eight new regressions passed in **4.68 seconds**. One synthetic native
Excel gate read **288 cells across nine pages** through the production bridge
and released its owned processes. No real workbook was edited or saved and no
provider requests were made. Manifest, schema budget, compilation and whitespace
checks pass. The full suite was not rerun per the user's latest instruction to
run only necessary tests; live model/provider and second-host gates remain unrun.

Inventories are retained under ignored `state/backups/office-range-discovery-20261015/`.
Preserve prior main at `archive/2026-10-15/main-before-office-range-discovery`,
commit, fast-forward local main and remove only its merged feature branch.
Other worktrees, private settings, historical/unmerged tips and remote refs remain intact.

## Office approval UI repair, 15 October 2026

`codex/office-approval-ui` starts from clean local main `9d0dfc2`.
The composer now presents the existing guarded Excel edit, restore and save
approvals instead of silently denying their unknown presentation keys. Saved
reviews show their path; unsaved reviews use the bound workbook title and
operation preview. Permissions, argument binding, schemas, prompts, routing,
sampling, context policy and private settings remain unchanged. See
[the repair and verification record](office-approval-ui-repair.md).

All six saved/unsaved presentation cases reproduced the silent rejection before
repair. The final affected Windows selection passed **96 checks in 51.31 seconds**,
including actual window/conversation/SDK/stdio approve, deny and approval-OFF
flows with normal production write policy. The full Windows suite completed
**4,153 tests and 15 subtests successfully**, with **63 skips, three failures and
two unchanged Qt deprecation warnings**, in **1,595.18 seconds**. All Office
checks passed. The complete Git installer and native startup modules passed
**68 checks in 68.92 seconds** on unchanged follow-up. The three full-run failures
were not reproduced; their cause remains unresolved and the full run is not
claimed as clean. See the repair record for exact failures and skipped gates.
All 45 translation catalogs validate; compilation and whitespace checks pass.
No real workbook cells were read or changed and no live provider request was
made. Opt-in live gates remain separate.

Inventories are retained under ignored `state/backups/office-approval-ui-20261015/`.
Preserve prior main at `archive/2026-10-15/main-before-office-approval-ui`, commit,
fast-forward local main and remove only the merged feature branch. Other
worktrees, private settings, historical/unmerged tips and remote refs remain intact.

## Office conversation catalog and full-suite repair, 15 October 2026

`codex/office-catalog-regression` starts from clean local main `c1f305c`.
The compact conversation prompt now accepts exactly the reviewed Office contract
names, allowing ordinary chat while Office is connected. Startup defaults a
missing inference mode to local. Profile number editors fit enlarged Settings
text; the attachment picker again uses its intended plain native dialog.
Stale UI fixtures, cleanup and bundled translation coverage are corrected.
Prompt wording, acceptance prompts, profiles, sampling, routing, context,
Office schemas, permissions and approvals remain unchanged. See
[the repair and verification record](office-mcp-conversation-repair.md).

The exact conversation error was reproduced before repair. The final affected
selection passed **100 checks in 103.09 seconds**. The fresh full suite on Qt's
Windows platform passed **4,141 tests and 15 subtests**, with **63 skips**, no
failures/errors, in **1,448.80 seconds**. Two unchanged test-only Qt activation
deprecation warnings remain. The initial full run's 77 failures and preliminary
native picker-driving interruptions are retained separately. The native Shell
picker is isolated at the synthetic fixture boundary; actual Shell-chrome
interaction and opt-in live provider/model/Office gates are not claimed.

All 45 catalogs validate and compile; unrelated translated wording is preserved.
Hungarian editorial fingerprints reflect punctuation/source maintenance while
native-language review remains pending. Compilation and whitespace checks pass.

Inventories are retained under ignored `state/backups/catalog-full-suite-20261015/`.
Preserve prior main at `archive/2026-10-15/main-before-office-catalog-regression`,
commit, fast-forward local main and remove only the merged feature branch.
Other worktrees, private settings, historical/unmerged tips and remote refs remain intact.

## Office MCP phase 4 Excel editing, 15 October 2026

`codex/office-mcp-phase4` starts from clean local main `3e6a9d0`. It adds
bounded Excel value/formula/format patches, conflict checks, guarded in-memory
restoration and separate approved Save/Save As. Existing permissions, exact
approvals, cloud gating, uncertainty journaling and accepted v1 manifests remain
authoritative. See [the implementation and verification record](office-mcp-phase4.md).

The final essential selection passed **134 focused checks in 64.94 seconds**,
without failures, errors or skips. One opt-in live Excel gate passed in
**12.01 seconds**, covering synthetic content, focus binding, conflicts,
restoration, invariant formulas/formats, Save As and save/reopen. Caught Windows
RPC diagnostics during native fixture shutdown remain in the live log and are
separate from passing edit correctness. No full-suite run was performed.

The six exposed tools measure **4,520 bytes / 1,795 reserve tokens**; the full
accepted manifest remains **7,390 bytes / 2,848 reserve tokens**. Runtime pins,
licenses, relocation, compilation and whitespace checks pass. Live provider
billing, physical second-host qualification and later Word/PowerPoint writes
remain unverified gates.

Inventories are retained under ignored `state/backups/office-mcp-phase4-20261015/`.
Preserve prior main at `archive/2026-10-15/main-before-office-mcp-phase4`, commit,
fast-forward local main and remove only the merged feature branch. Other
worktrees, private settings, historical/unmerged tips and remote refs remain intact.

## Office MCP phase 3 live reads, 15 October 2026

`codex/office-mcp-phase3` starts from clean local main `97db799`. It adds
per-run registered Office discovery, document-bound COM STA adapters, bounded
read pagination and basic connection/document controls in Settings > Models.
Only listing, attachment and reading are exposed. Existing host permissions,
cloud gating and accepted v1 manifests remain authoritative. See
[the implementation and verification record](office-mcp-phase3.md).

The final essential selection passed **111 focused checks in 69.57 seconds**,
without failures/errors/skips. Three opt-in live gates passed in 32.28 seconds,
using synthetic unsaved Excel/Word instances and PowerPoint presentations,
one-character Unicode pages and focus changes. Native fixture shutdown emitted
caught RPC diagnostics, retained separately from read correctness. Two known
fixture processes from earlier failed cleanup were recovered using exact owned
PIDs and creation times. Existing popup assertions reproduce against unchanged
main Settings source; they are recorded as baseline failures, not passed checks.
The sandbox EnumWindows error is separate from passing normal desktop discovery.

The three exposed tools measure **1,824 bytes / 752 reserve tokens**; the full
accepted manifest remains **7,390 bytes / 2,848 reserve tokens**. Runtime pins,
licenses, relocation, compilation and whitespace checks pass. The full suite,
real cloud billing and physical second-host gates were not run.

Inventories are retained under ignored `state/backups/office-mcp-phase3-20261015/`.
Preserve prior main at `archive/2026-10-15/main-before-office-mcp-phase3`, commit,
fast-forward local main and remove only the merged feature branch. Other
worktrees, private settings, historical/unmerged tips and remote refs remain intact.

## Office MCP phase 2 foundation, 15 October 2026

`codex/office-mcp-phase2` starts from clean local main `1c2354e`.
It bundles MCP 2.3.0 and pinned runtime additions, uses atomic Windows ownership
for bounded stdio pipes, and composes reviewed Office capabilities through the
existing permission, approval, executor and crash-journal paths. Native calls
and constrained recovery preserve cloud-only Office execution. Default startup
stays disconnected; live Office discovery and adapters remain phase 3 onward.
See [the implementation and verification record](office-mcp-phase2.md).

All **105 essential focused checks passed in 41.16 seconds**, without failures,
errors or skips. Real SDK/stdio fixtures prove persistent calls, exact approvals,
unknown-outcome review, timeouts, owned process cleanup and a relocated MCP/native
runtime. Selected existing ownership, cloud fallback, token-accounting and fresh
node checks pass. Runtime pins, license files, dependency consistency, compilation,
builder syntax, staged whitespace and the unchanged **7,390-byte /
2,848-reserve-token** schema budget verify.
Full-suite, live Office/provider, physical second-host and complete GUI gates were
not run. Early fixture/collection failures remain separate evidence.

Inventories are retained under ignored
`state/backups/office-mcp-phase2-20261015/`. Preserve prior main at
`archive/2026-10-15/main-before-office-mcp-phase2`, commit, fast-forward local main
and remove only the merged feature branch. Other worktrees, historical/unmerged
tips, private settings and remote refs remain intact.

## Office MCP phase 1 contracts, 15 October 2026

`codex/office-mcp-phase1` starts from clean local main `ada5219`.
It adds strict Office argument/result contracts, cloud-only exposure snapshots,
an accepted schema manifest and offline budget verification. No transport,
production Office capability, Office automation or provider request is enabled.
See [the contract and verification record](office-mcp-phase1.md).

All **104 essential focused checks passed in 0.86 seconds**, with no failures,
errors or skips. The complete eight-tool schema measures **7,390 UTF-8 bytes**
and **2,848 conservative reserve tokens**, below the accepted **9,000-byte /
3,500-reserve-token** ceiling. Local/disabled/not-ready exposure has zero Office
schema overhead. These are offline estimates, not billed provider usage. The
accepted-manifest verifier, compilation and staged whitespace review pass.
Full-suite and live gates were not run, following the
user's explicit essential-focused-tests-only default.

Ref/worktree inventories are retained under ignored
`state/backups/office-mcp-phase1-20261015/`. Preserve prior main at
`archive/2026-10-15/main-before-office-mcp-phase1`, commit, fast-forward local
main and remove only the merged feature branch. Other worktrees, historical/
unmerged tips, private settings and remote refs remain intact.

## Dropdown choices and sliding module highlight, 15 October 2026

`codex/settings-dropdown-motion` starts from clean local main `2cdc6ec`.
Shared Settings dropdown choices remove their borders and gain a faint hover
fill. A single module highlight slides behind the selected button, supports
rapid changes and follows layout changes and later-added modules. See
[the presentation and verification](spacious-settings.md).

All **20 essential native UI checks passed in 31.61 seconds**, without failures,
errors, skips or warnings. Representative popup and moving/settled highlight
screenshots were visually inspected in both bundled themes. Compilation and
whitespace checks pass. Full-suite and live gates remain outside the user's
focused UI scope.

Inventories are retained under ignored
`state/backups/settings-dropdown-motion-20261015/`. Preserve prior main at
`archive/2026-10-15/main-before-settings-dropdown-motion`, commit, fast-forward
local main and remove only the merged feature branch. Other worktrees,
historical/unmerged tips, private settings and remote refs stay intact.

## Installed skills, switches and greeting backdrop, 15 October 2026

`codex/settings-skills-switches` starts from clean local main `b793854`.
Installed skills gains a taller outlined list without entry separators and
Remove aligns with its heading. Notifications spacing and switch appearance
are corrected. Settings bypasses Qt's nested greeting opacity effect during
the backdrop blur, restoring it on close. See
[the presentation and verification](spacious-settings.md).

All **22 essential native UI checks passed in 37.12 seconds**, with no failures,
errors or skips; two test-only Qt window-activation deprecation warnings remain.
Twenty native module/theme/size states were checked and affected screenshots
visually inspected. Compilation and whitespace checks pass. An unchanged
notification layout assertion failed on a preserved starting-revision snapshot
and now follows the current responsive row structure. Full-suite and live gates
remain outside the user's focused UI scope.

Inventories are retained under ignored
`state/backups/settings-skills-switches-20261015/`. Preserve prior main at
`archive/2026-10-15/main-before-settings-skills-switches`, commit, fast-forward
local main and remove only the merged feature branch. Other worktrees,
historical/unmerged tips, private settings and remote refs stay intact.

## Settings action alignment, 15 October 2026

`codex/settings-action-alignment` starts from clean local main `3ed7306`.
Notifications retains one bold label, Skills shares one import action row, and
Image Generation/Appearance separate their compact footer buttons from the
preceding row. See [the presentation and verification](spacious-settings.md).

All **13 focused native checks passed in 30.87 seconds**, without failures,
errors or skips. Twenty native module/theme/size states were checked and the
affected modules' screenshots visually inspected. Compilation and whitespace
checks pass. Full-suite and live gates remain outside the user's focused UI scope.

Inventories are retained under ignored
`state/backups/settings-action-alignment-20261015/`. Preserve prior main at
`archive/2026-10-15/main-before-settings-action-alignment`, commit, fast-forward
local main and remove only the merged feature branch. Other worktrees,
historical/unmerged tips, private settings and remote refs stay intact.

## Flat Settings and compact action buttons, 15 October 2026

`codex/settings-cleanup` starts from clean local main `1502224`. The ordinary
Settings modules remove gray group backgrounds/borders and visible static
subtexts. Installed skill entries show names. Action buttons use native content
bounds to avoid accidental wrapping and double heights. Personal profile,
login, preferences, translations and model behavior are unchanged. See
[the current presentation and verification](spacious-settings.md).

All **32 focused native tests passed in 51.25 seconds**, without failures,
errors or skips. Twenty native module/theme/size states were rendered and checked;
representative final screens were visually inspected. Compilation and whitespace
checks pass. Full-suite and live gates remain outside the user's focused UI scope.

Inventories are retained under ignored `state/backups/settings-cleanup-20261015/`.
Preserve prior main at `archive/2026-10-15/main-before-settings-cleanup`, commit,
fast-forward local main and remove only the merged cleanup branch. Other
worktrees, historical/unmerged tips, private settings and remote refs stay intact.

## Spacious Settings and centered login, 15 October 2026

`codex/spacious-settings` starts from clean local main `7b15478`. The five ordinary
Settings modules use a centered, wider content column, rounded groups, visible
descriptions, larger type and responsive controls. Skills separates import and
installed entries with compact actions and visible descriptions. Regular login
removes the password caption and centers Unlock and More/Less. Personal profile
source, geometry and typography remain unchanged. See
[the presentation and verification record](spacious-settings.md).

All **54 essential native tests passed in 151.84 seconds**, with no failures,
errors or skips; nine targeted checks passed in 18.19 seconds after the last
wrapped-caption height correction, and four native caption-fitting checks passed
in 4.62 seconds. Thirty module/theme/size states have reachable
controls, and all 20 Personal profile baseline measurements match. Representative
module, login and wrapped-caption previews were visually inspected. Earlier
layout failures and the stale Skills assertion reproduced on starting main are
recorded separately. Full-suite and live inference gates were not run under
the user's necessary-UI-test scope.

Pre-change refs/worktree inventories are retained under ignored
`state/backups/spacious-settings-20261015/`. Preserve prior main at
`archive/2026-10-15/main-before-spacious-settings`, commit, fast-forward local
main and remove only the merged layout branch. Other worktrees, historical/
unmerged tips, private settings and remote refs remain unchanged.

## Independent interface font, 15 October 2026

`codex/font-selector` starts from clean local main `302e182`. Appearance's Text
size placeholder becomes an English-only Font selector with Theme default,
Lora, Merriweather, Outfit, Nunito, DM Sans and Montserrat. The independent
profile preference overrides theme typography without modifying theme exports.
Bundled font binaries, italic faces, complete licenses and pinned source/hash
metadata travel with the app and work offline after relocation. Login restores
the public bundled font ID before unlock; protected settings remain in the vault.
See [the behavior and verification record](interface-font.md).

All **76 essential native checks passed** with no failures/errors/skips: 15
focused checks in 55.64 seconds and 61 existing UI regressions in 57.04 seconds.
Twenty-eight font/theme/window-size layouts fit, representative previews were
visually inspected, and the built wheel's fonts load from a relocated extraction.
The initial new-test optical-size-alias expectations and sandbox lock denial
remain separate evidence. Full-suite/live inference gates and a full standalone
runtime rebuild were not run under the user's essential-UI-test scope.

Pre-change refs/worktree inventories are retained under ignored
`state/backups/font-selector-20261014/`. Preserve prior main at
`archive/2026-10-15/main-before-font-selector`, commit, fast-forward local main
and remove only the merged font branch. Other active worktrees, historical/
unmerged tips, private user settings and remote refs remain unchanged.

## Full-window Settings, 14 October 2026

The accepted GUI-language work (`b87c29b`, Hungarian editorial revision
`4619c92`) was fast-forwarded into local main before starting the bounded
`codex/settings-full-window` presentation change. Prior main `7ba2278` is
preserved at `archive/2026-10-14/main-before-gui-language`; the merged language
branch was removed. Other active worktrees and remote refs were untouched.

Settings now fills the application window with the actual chat blurred behind
it, retaining its section/control layout and theme colors. Typography increases
within Settings and adapts at minimum size. Native caption controls, close/Escape,
drafts, profile and worker lifetimes retain their behavior. See
[the presentation and verification record](settings-full-window.md).

All **46 essential native tests and eight subtests passed in 85.99 seconds**,
with no failures, errors or skips. Forty-five synthetic screen states were
rendered with no measured caption or horizontal overflow. No full-suite or live
model/API qualification is claimed under the user's essential-test scope.
The initial compact fitting failure is retained in the presentation record;
its unchanged check passes after the responsive typography correction.

Ref/worktree inventories are retained under ignored
`state/backups/settings-full-window-20261014/`. Preserve prior main `4619c92` at
`archive/2026-10-14/main-before-settings-full-window`, commit, fast-forward local
main and remove only the merged Settings branch. Other worktrees, historical/
unmerged tips, user settings and remote refs remain outside this operation.

## Greeting question-form guard, 14 October 2026

`codex/greeting-question-guard` starts from clean main `47343cf`. Known
standalone greetings, check-ins and thanks keep the ordinary composer across
dedicated/generic form metadata and plain-text extraction. Greeting-prefixed
tasks and short clarification answers remain eligible. Old saved greeting
forms are suppressed in the visible projection without migrating their saved
content. Matching is conservative and covers common English/Hungarian/Dutch
social turns; unknown text keeps the existing workflow.

All **127 focused native checks passed** in **23.35 seconds**, including 44 new
regression cases. The unchanged timeout group and revised host greeting check
passed all **41 checks** in **5.01 seconds**. The host greeting's acceptance
prompt, reply and no-filesystem-action assertions remain unchanged; only its
expectation of a question-extraction request changes. Preliminary new-test
fixture failures concerned required outcome counts and comparisons spanning
the store's normal activation/timestamp write; the final fixture verifies
unchanged saved messages/turns and a read-only visible projection. Earlier
evidence remains under ignored `state/greeting-guard-*.xml`.

The full native run recorded **3,899 passed, four failures, 61 skips and 15
passing subtests** in **1,004.63 seconds**. Failures were the obsolete greeting
extraction expectation, an unchanged 30-millisecond runtime deadline, custom
login font restoration and a skill-import worker deadline. The greeting and
runtime groups passed their 41-check recheck. A final four-module recheck
recorded 58 passed and three UI failures in 105.44 seconds, including a second
skill-import worker deadline. All three UI failures reproduced identically on
an untouched source archive of starting main `47343cf` in 34.96 seconds. No
full run is labeled passing; unrelated login/skill behavior and assertions were
not changed. Evidence is retained under ignored `state/greeting-guard-full.*`,
`state/greeting-guard-final-recheck.xml` and `state/greeting-guard-baseline.xml`.

The 61 skips, including opt-in live-model/API gates, remain separate from
deterministic checks; no live model/API qualification was performed. Prompt
constants, accepted configuration and existing
acceptance `run` calls are unchanged; dependency, compilation and whitespace
checks pass. See [the presentation contract](question-composer.md).

Pre-change refs/worktree inventories are retained under ignored
`state/backups/greeting-question-guard-20261014/`, and prior main is preserved at
`archive/2026-10-14/main-before-greeting-question-guard`. After verification,
commit, fast-forward local main and remove only the merged feature branch.
Other active worktrees, historical/unmerged tips and remote refs remain intact.

## Centered login composer and neutral Settings borders, 14 October 2026

`codex/original-settings-borders` starts from clean main `a4146f7`. The locked
backdrop positions the composer in the center independently of the hidden intro
greeting. Original's settings and app-owned settings dialogs use neutral gray
borders across controls and interaction states, including dropdown/list selections,
checkbox/radio indicators, switch focus rings, profile cards/tabs and panel edges.
Other themes retain palette mapping. This change does not alter authentication,
notification/sound behavior, response formatting or animation timing.

All **45 essential native checks passed** in **65.70 seconds**, with no failures,
errors or skips. Coverage includes border/indicator pixels in native interaction
states, settings navigation/geometry, theme switching, numeric editing, checkbox
consent and login centering through lock, resize and cold restart. The initial
pixel probe included text antialiasing; the final probe samples border perimeters.
Native Settings and Original/Conformist locked previews were visually inspected.
Evidence is under ignored `state/settings-borders-final.xml` and
`state/settings-borders-preview/`. Full-suite and live inference gates were not
run under the user's essential-test scope. Whitespace checks passed.

Ref/worktree inventories are retained under ignored
`state/backups/original-settings-borders-20261014/`, with prior main preserved at
`archive/2026-10-14/main-before-original-settings-borders`. Commit, fast-forward
local main and remove only this merged branch. Other worktrees, historical/unmerged
tips, private settings and remote refs remain unchanged; no push is part of this task.

## Login panel polish, 14 October 2026

`codex/login-panel-polish` starts from clean main `8cdc851`. Normal login labels
the profile location `Profile Path:` instead of repeating storage/encryption/lock
status. More/Less now invalidates and measures the inner page before its container,
so Less returns the panel to its compact height without a residual scrollbar.
Login fields and buttons keep neutral borders on focus/press across themes;
other controls retain their existing theme focus roles. Locked windows suppress
the background greeting and disabled-composer prompt behind the blur.

The final **22 essential native checks passed** in **50.04 seconds**, with no
failures/errors/skips. Checks cover More/Less geometry, border pixels on click,
hidden backdrop text, theme persistence, password/recovery unlock, onboarding
and saved/manual/cancel credential choices. Native expanded/collapsed/focused/
pressed and full-window previews were inspected. Evidence is under ignored
`state/login-polish-final.xml` and `state/login-polish-preview/`. Full-suite and
live inference gates were not run under the user's essential-test scope. No
provider requests, authentication-policy changes or private settings migrations.

Ref/worktree inventories are retained under ignored
`state/backups/login-panel-polish-20261014/`, with prior main preserved at
`archive/2026-10-14/main-before-login-panel-polish`. Commit, fast-forward local
main and remove only this merged branch. Other worktrees, historical/unmerged
tips, private settings and remote refs remain unchanged; no push is part of this task.

## Minimal themed profile login, 14 October 2026

`codex/minimal-profile-login` starts from clean main `d363b11`. Normal login
shows a password field, a content-sized unlock button and an underlined More
control. More reveals recovery, profile location and alternative profile/restore
actions. Inputs use 18px text, with 16px labels/actions and explicit font smoothing.
Panel styling and painting follow the theme, including Conformist's flat colors
and DM Sans. Layout adapts to font changes and scrolls in compact windows.
Setup, unavailable-profile and deletion-retry screens keep their necessary actions.

An ignored public login appearance preference remembers built-in theme identity
and custom colors/installed font families, keyed to the public profile ID.
Protected custom assets and other profile contents remain encrypted; unavailable
custom fonts fall back before unlock. Existing installations initialize this
preference after one successful unlock. Corrupt appearance files are preserved.

The final **37 essential native checks passed** in **77.97 seconds**, with no
failures/errors/skips. Real synthetic password/recovery unlocks, cold theme
restoration, More keyboard access, compact geometry, missing-profile and deletion
retry flows passed. Native collapsed/expanded/error previews were inspected.
Evidence is under ignored `state/minimal-login-final.xml` and
`state/minimal-login-preview/`. Full-suite and live inference gates were not run
under the user's essential-test scope. No authentication, prompt, inference,
response-formatting, animation or notification policy changes.

Ref/worktree inventories are retained under ignored
`state/backups/minimal-profile-login-20261014/`, with prior main preserved at
`archive/2026-10-14/main-before-minimal-profile-login`. Commit, fast-forward local
main and remove only this merged branch. Other worktrees, historical/unmerged
tips, private settings and remote refs remain unchanged; no push is part of this task.

## Questionnaire header and footer text, 14 October 2026

`codex/questionnaire-chrome-text` starts from clean main `f9a5741`. Questionnaire
header, required-count, hint and action text now use 16px instead of 14px. The
header uses medium weight rather than semibold. The form uses the same explicit
antialiasing and vertical hinting preferences as Settings, retaining each theme's
font family. Answer handling, transition animations and notifications are unchanged.

All **5 focused native checks passed** in **6.00 seconds**, with no failures,
errors or skips. Original/Conformist header/footer and compact previews were
inspected. Evidence is under ignored `state/questionnaire-chrome-essential.xml`
and `state/questionnaire-chrome-preview/`. Full-suite and live inference gates
were not run under the user's essential-test scope.

Ref/worktree inventories are retained under ignored
`state/backups/questionnaire-chrome-text-20261014/`, with prior main preserved at
`archive/2026-10-14/main-before-questionnaire-chrome-text`. Commit, fast-forward
local main and remove only this merged branch. Other worktrees, historical/unmerged
tips, private settings and remote refs remain unchanged; no push is part of this task.

## Readable questionnaire typography, 14 October 2026

`codex/questionnaire-typography` starts from clean main `1c1d51d`. Questionnaire
titles use 18px type; answers/choices use 16px, with 14px hints and footer text.
The form follows the selected theme font (including Conformist's DM Sans), with
larger fields, indicators and spacing. Long native radio/checkbox labels wrap
without changing their answer values or keyboard behavior. The panel may grow
to 720px when space permits; compact windows retain vertical scrolling.

All **44 essential native checks passed** in **13.90 seconds**, with no
failures/errors/skips. Two focused cases also verified clicks on wrapped labels
after final test additions. Native Conformist/Original, compact, long-choice and
custom-answer previews were inspected. Evidence is under ignored
`state/questionnaire-typography-essential.xml`, `state/questionnaire-typography-click.xml`
and `state/questionnaire-typography-preview/`. Full-suite and live inference gates
were not run under the user's essential-test scope. Prompts, routing, answer
validation, response formatting, transition animations and notifications are unchanged.

Ref/worktree inventories are retained under ignored
`state/backups/questionnaire-typography-20261014/`, with prior main preserved at
`archive/2026-10-14/main-before-questionnaire-typography`. Commit, fast-forward
local main and remove only this merged branch. Other worktrees, historical/unmerged
tips, private settings and remote refs remain unchanged; no push is part of this task.

## Lean Settings modules, 14 October 2026

`codex/lean-settings` starts from clean main `b4b9e77`. Settings retain module
introductions, field names and controls, with routine helper subtitles, selected
personality/model descriptions and the technical status footer removed from
the layout. Contextual help remains in tooltips/accessibility descriptions;
unavailable states, errors, skill previews and save/import feedback remain visible.
No preference, inference, response-formatting, animation or notification behavior changes.

All **87 essential native checks passed** in **40.59 seconds**, with no
failures/errors/skips. The Settings tests also passed independently (**21 tests**)
after checking their import order. Native previews of all five modules and the
compact General page were inspected. Evidence is under ignored
`state/lean-settings-essential.xml`, `state/lean-settings-isolated.xml` and
`state/lean-settings-preview/`. Full-suite and live inference gates were not run
under the user's essential-test scope.

Ref/worktree inventories are retained under ignored
`state/backups/lean-settings-20261014/`, with prior main preserved at
`archive/2026-10-14/main-before-lean-settings`. Commit, fast-forward local main
and remove only this merged branch. Other worktrees, historical/unmerged tips,
private settings and remote refs remain unchanged; no push is part of this task.

## Conformist shimmering-dot image placeholder, 14 October 2026

`codex/conformist-dot-placeholder` starts from clean main `75a98bd`. The user's
requested placeholder appearance uses stationary white dots which slowly vary
in opacity over flat darker charcoal. A bounded `image_placeholder` manifest
option preserves it in exported custom themes. Original/Ocean cloud visuals,
pause/stop behavior, image reveal, other UI animations and notifications remain
unchanged. No prompts, routing, inference policy or private settings change.

All **62 essential native checks passed**, with no failures/errors/skips, in
**21.80 seconds**. Native square/portrait and animated previews were inspected;
compile/whitespace checks passed. Evidence is retained under ignored
`state/conformist-dots-essential.xml` and `state/conformist-dots-preview/`.
Full-suite and live inference gates were not run under the user's essential-test scope.

Inventories are retained under ignored `state/backups/conformist-dot-placeholder-20261014/`,
with prior main at `archive/2026-10-14/main-before-conformist-dot-placeholder`.
Commit, fast-forward local main and remove only this merged feature branch.
Other worktrees, historical/unmerged tips, private settings and remote refs
remain unchanged; no push is part of this task.

## Conformist attachment plus icon, 14 October 2026

`codex/conformist-plus-icon` starts from clean main `ca43447`. Only Conformist's
attachment artwork changes from a paperclip to a plus, retaining its neutral
stroke, button geometry and attachment behavior. All **10 essential native
Conformist/icon checks passed** in **3.56 seconds**; the composer preview was
visually inspected. Full-suite and live inference gates were not run under
the user's essential-test scope.

Inventories are retained under ignored `state/backups/conformist-plus-icon-20261014/`,
with prior main at `archive/2026-10-14/main-before-conformist-plus-icon`. Commit,
fast-forward local main and remove only this merged branch. Other worktrees,
historical/unmerged tips, private settings and remote refs remain unchanged.

## Conformist circular send icon, 14 October 2026

`codex/conformist-send-circle` starts from clean main `b1390a7`. The Conformist
send SVG now uses a flat blue circle and a centered arrow at 70% of its previous
size. Hit targets, behavior and other themes remain unchanged. All **10 essential
native Conformist/icon checks passed** in **3.81 seconds**; the composer preview
was visually inspected. Full-suite and live inference gates were not run under
the user's essential-test scope.

Inventories are retained under ignored
`state/backups/conformist-send-circle-20261014/`, with prior main at
`archive/2026-10-14/main-before-conformist-send-circle`. Commit, fast-forward local
main and remove only this merged branch. Other worktrees, historical/unmerged
tips, private settings and remote refs remain unchanged; no push is part of this task.

## Conformist theme, 14 October 2026

`codex/conformist-theme` starts from clean main `356482e`. The new bundled theme
uses flat charcoal surfaces, one blue accent, Google Fonts DM Sans and Lucide
outline icons. Font/icon licenses travel with exports, and public portable/Python
packages include the assets. Existing user selection, response formatting,
animations, notifications/audio and inference remain unchanged. See
[the design and essential verification](conformist-theme.md).

The final native essential run passed **124 tests**, with no failures/errors/skips,
in **44.32 seconds**. Actual DM Sans wrapping and switching, font release,
license-preserving round trips, packaging, settings, composer/approval motion and
notification regressions passed. Native previews were visually inspected.
Full-suite and live inference gates were not run under the user's essential-test scope.

Ref/worktree inventories are preserved under ignored
`state/backups/conformist-theme-20261014/`, with prior main retained at
`archive/2026-10-14/main-before-conformist-theme`. Commit, fast-forward local main
and remove only this merged feature branch. Other worktrees, historical/unmerged
tips, private preferences and remote refs remain intact; no push is authorized here.

## Cosmetic UI themes, 14 October 2026

`codex/ui-themes` starts from clean main `32a51bc`. Theme manifests control only
cosmetic values and static assets, with live selection/import/export, preserved
Original appearance and profile-owned portable storage. Response formatting,
animation behavior, notifications/audio and inference remain unchanged. See the
[theme contract](ui-themes.md) and [essential verification](ui-themes-verification.md).

Essential regression passed **173 tests and 5 subtests**, with **2 native-only
skips**, in **58.00 seconds**. Final native theme checks passed **40 tests** in
**7.71 seconds**. Original's chat capture is pixel-identical to unchanged main.
The existing native attachment-picker teardown crash reproduces on unchanged
main and remains separate from the passing offscreen regression. Full-suite and
live inference gates were not run under the user's essential-test scope.

Ref/worktree inventories are preserved under ignored
`state/backups/ui-themes-20261014/`, with prior main at
`archive/2026-10-14/main-before-ui-themes`. Commit, fast-forward local main and
remove only this merged feature branch. Other worktrees, historical/unmerged
tips, private settings and remote refs remain intact; no push is authorized here.

## Main publication and final cleanup, 14 October 2026

The user requested consolidation of all current work on main, publication to
GitHub and immaculate Git hygiene. All feature tips were already included in
main `51caff8`, which was fifteen commits ahead of origin. The bounded
`codex/final-integration-20261014` branch includes the user's pending notification
sound and corresponding regression-fixture maintenance. See the
[integration and verification record](repository-integration-2026-10-14.md).

Final full native verification passed **3,786 checks and 15 subtests**, with
**61 optional/host skips**, no failures/errors, in **773.73 seconds**. Earlier
fixture and Windows rename failures remain recorded separately. Acceptance
requests, production inference policy and private settings remain unchanged.

Preserve original refs and the sound in the verified ignored recovery bundle,
retain pre-integration main as `archive/2026-10-14/main-before-final-integration`,
convert inactive archive branches to identical recovery tags, and preserve the
merged personality tip as `archive/2026-10-14/codex-profile-personalities` before
removing its branch. After verification, commit, fast-forward local main, remove
the merged integration branch and push only main without rewriting history.
Other worktree attachments, HEADs, files and private runtime state remain intact.

## Fresh taskbar icon resource, 14 October 2026

`codex/taskbar-icon-resource` starts from local main `b31ea82`. The user still
saw the older wide taskbar artwork after a targeted Windows cache refresh. Native
inspection found square 16/32 pixel window icons, and no matching pinned link;
the exact taskbar selection mechanism was not established. The app, native tray/
notification backend and shortcut creator now use the fresh `orsi-app.ico`
resource path. The existing builder also retains byte-identical `orsi.ico` for
external launcher compatibility. Application identity and launch behavior stay
unchanged; no global icon-cache deletion or Explorer restart is needed.

All **25 focused branding/notification checks passed** in **5.65 seconds**, with
no failures/errors/skips. Native Windows assigned the new resource a different
image-list entry; all nine icon frames retain square artwork. The matching
desktop shortcut now points to the new resource, preserving target, arguments,
description and working directory. A real native notification received its show
callback and released owned resources. The displayed taskbar button after the
user reopens the app remains a separate visual check; it is not claimed passing
from native icon measurements. Full-suite and live-model/API checks were not run
under the essential-test scope.

Evidence is retained in ignored `state/taskbar-icon-resource-tests.xml`,
`state/taskbar-icon-investigation/resource-fix.json`, and
`state/icon-dimensions/native-fixed.json`. Ref/worktree inventories, prior matching
shortcut and the unrelated uncommitted sound edit are backed up under ignored
`state/backups/taskbar-icon-resource-20261014/`. That sound edit is excluded from
the commit. Prior main is preserved at
`archive/2026-10-14/main-before-taskbar-icon-resource`. Commit, fast-forward local
main and remove only the merged branch; other worktrees and remote refs stay intact.

## Corrected application icon dimensions

`codex/icon-dimensions` starts from local main `1ff4abd`. The user's corrected
256 × 256 desktop `bsw_o.png` replaces the bundled source byte-for-byte, and the
existing builder regenerates all nine ICO sizes. App/window/loading, native tray,
notification and shortcut paths already share these assets; runtime behavior
does not change. The existing proportion assertion now follows the source size.

All **25 essential branding/notification checks passed** in **7.72 seconds**, with
no failures/errors/skips, using repository-local temporary/cache storage. Results
are retained in ignored `state/icon-dimensions-essential.xml`. All sizes were
visually inspected in `state/icon-dimensions/sizes.png`. Real Windows banner
delivery accepted the new artwork with a show callback and released owned native
resources; evidence is in `state/icon-dimensions/native-fixed.json`. The matching
desktop shortcut was refreshed after backup, preserving target, arguments,
working directory and description. Full-suite and live-model/API checks were
not run under the user's essential-test scope.

The pre-existing uncommitted `noti_1.ogg` edit remains byte-identical and is
excluded from this commit. Its recoverable copy, the previous matching shortcut
and ref/worktree inventories are preserved under ignored
`state/backups/icon-dimensions-20261013/`. Prior main is retained at
`archive/2026-10-13/main-before-icon-dimensions`. Commit, fast-forward local main
and remove only the merged feature branch. Other worktrees, historical/unmerged
tips and remote refs remain unchanged.

## Native notification delivery and audio completion, 13 October 2026

`codex/notification-delivery-audio` starts from clean local main `36fa457`.
The default-size custom icon now uses `NIIF_LARGE_ICON`, fixing real Windows
banner rejection with error 1462. Audio idle states only complete a stream after
all source bytes are read and the full duration is processed; temporary underruns
preserve playback. Existing focus/foreground rules, settings, files, volume,
event timing and inference behavior remain. See [the follow-up contract](notification-bugfixes.md).

The final native essential run passed **29 tests**, with no failures/errors/skips,
in **6.32 seconds**, using repository-local temporary/cache storage. Results are
retained in ignored `state/notification-fix-essential.xml`. New regressions cover
startup/half-read/queued-but-unprocessed idle states, eventual single completion,
cancellation, device failure, stale callbacks and custom/stock icon ownership.
Before production changes, six new cases failed on the starting implementation
and seven existing cases passed; that expected failing baseline is retained in
`state/notification-fix-before.xml`.

The production backend, without diagnostic flag overrides, now receives a real
Windows banner-show callback with no native errors and releases its tray/icon resources. Real audio
output at zero volume processed both padded sounds fully (3.487 and 3.559 seconds),
including an injected 600 ms UI stall, and released owned sinks without errors.
Content-free diagnostics are retained in ignored
`state/notification-investigation/native-fixed.json` and `muted-fixed.json`.
This verifies samples/device completion, not acoustic output; the precise audible
cutoff was not reproduced during investigation. Full-suite and live-model/API
checks were not run under the user's essential-test scope.

Ref/worktree inventories are retained under ignored
`state/backups/notification-delivery-audio-20261013/`; prior main is preserved at
`archive/2026-10-13/main-before-notification-delivery-audio`. Commit, fast-forward
local main and remove only the merged feature branch. Other worktrees,
historical/unmerged tips, remote refs and private user settings remain unchanged.

## Stable selected question choices, 13 October 2026

`codex/question-choice-stability` starts from clean local main `a1804d4`.
The selected radio indicator previously changed its border from one to three
pixels, growing from 16 to 20 pixels and moving its top/label. A one-line style
change keeps the inherited dimensions, border width and radius; selection only
changes colors. Synthetic Qt measurements confirm identical row, indicator and
text geometry for all four choices and keyboard selection. Essential existing
question/presentation checks passed **41 tests** in **10.42 seconds**; native
results are retained in ignored `state/question-choice-stability-tests.xml`.
The integrated focused-radio screenshot was visually inspected. Full-suite and
live-model/API checks were not run under the user's essential-test scope.
Measurements and ref/worktree inventories are retained under ignored
`state/question-choice-stability/` and
`state/backups/question-choice-stability-20261013/`. Prior main is preserved at
`archive/2026-10-13/main-before-question-choice-stability`. Commit, fast-forward
local main and remove only the merged feature branch; other worktrees and
historical/unmerged/remote refs remain unchanged.

## Question choice and transition polish, 13 October 2026

`codex/question-composer-polish` starts from clean local main `a82485f`.
Radio/checkbox rows no longer gain a white focus rectangle; native keyboard
focus and selection remain available. Profiling identified repeated bottom-glass
snapshot/blur work, especially growing empty composer clearance, as the main
transition cost. The blur now excludes that empty space and temporarily reuses
an unchanged transcript fragment during settled questionnaire transitions.
The content opacity effect is disabled after the reveal. Existing timing,
easing, per-frame transcript clearance, approvals and inference behavior remain.

The essential native run passed **57 checks** with no failures/errors/skips in
**15.93 seconds**, using repository-local temporary/cache storage. Results are
retained in ignored `state/question-polish-final.xml`. Checks cover forms,
keyboard/mouse selection, height/fade geometry, cache reuse/release, interrupted
transitions and resize, plus the existing inline approval lifecycle. Focused
radio and checkbox screenshots were visually inspected. Initial new assertions
needed queued Qt layout/focus updates and a click on the actual checkbox
indicator; those fixture failures remain in the earlier XML runs. Production
acceptance requests were unchanged. Full-suite and live-model/API checks were
not run under the user's essential-test scope.

A synthetic 40-message, 64-frame rendering probe measured median frame work
at **11.70 ms before / 4.54 ms after**, and 95th percentile **15.52 / 7.43 ms**.
Blur calls fell from **64 to 14**. These are local rendering measurements,
not a live frame-rate guarantee. Backdrop output was pixel-identical to the
starting implementation at six collapsed/expanded and scroll positions.
Content-free measurements are retained under ignored
`state/question-polish-profile/`.

Ref/worktree inventories are preserved under ignored
`state/backups/question-composer-polish-20261013/`; prior main is retained at
`archive/2026-10-13/main-before-question-composer-polish`. After verification,
commit, fast-forward local main and remove only the merged feature branch.
Other worktrees, historical/unmerged tips and remote refs remain unchanged.

## Questionnaire presentation and composer motion, 13 October 2026

`codex/question-composer-presentation` starts from clean local main `13ac8d3`.
The reported normal `json` component fence is recognized and suppressed from
chat/streaming. Form handoffs display only the introductory remark, keeping full
questions in durable/model history and applying the same projection on restore.
The questionnaire uses the regular composer gradient/palette/rounding and the
approval animation's cubic timing, with a coordinated fade and natural-height
layout. Inference prompts, routing, model profiles, sampling, context limits,
tool schemas and approval authority are unchanged.

Under the user's essential-test scope, the final native run passed **91 checks**
with no failures/errors/skips in **14.08 seconds**. Results are retained in ignored
`state/question-presentation-final.xml`. Checks include the reported control
payload, per-character streaming boundaries, remark-only/question-only UI and
restored history, ordinary JSON/quoted examples, animation midpoint/end geometry
and input size, plus existing local/cloud forms, Luna synthetic SDK flow,
approvals, cancellation and default-context acceptance. The themed form was
visually inspected. Full-suite and live-model/API checks remain separately unrun.
Earlier runs retain one normal-JSON closing-fence preview defect (fixed in the
parser) and an existing preview assertion that expected duplicated question text
(updated for the requested presentation); acceptance requests remain unchanged.

Content-free ref/worktree inventories are retained under ignored
`state/backups/question-presentation-20261013/`. Prior main is preserved at
`archive/2026-10-13/main-before-question-presentation`. After verification,
commit, fast-forward local main and remove only the merged feature branch.
Other worktrees, historical/unmerged tips and remote refs remain unchanged.

## Plain-text question handoffs, 13 October 2026

`codex/plain-question-handoff` starts from clean local main `b814390`. The
reported Luna reply asked what a sand-simulation prompt should request, but
omitted the optional question fence. The initial scripted UI checks assumed
that fence was present. A bounded, tool-free presentation fallback now extracts
actual clarification questions from plain replies, verifies their provenance,
and attaches existing form metadata. The original reply, task review and
receipts stay intact; no choices are invented. Valid fenced forms still use
the original path without another request. See [the fallback contract](question-composer.md).

The user retained the essential-test scope. Final native checks passed **78
tests**, with no failures/errors/skips, in **22.94 seconds**. Results are in
ignored `state/plain-question-qualified.xml`. They include the exact reported
reply through the Luna Medium SDK over a synthetic streaming transport, settled
visible input fields and subsequent answer submission, plain local/cloud
handoffs, faithful/multilingual extraction, unavailable/invalid output,
cancellation/timeouts, and existing forms, approvals, streaming and default
context checks. The rendered reproduction was visually inspected. The first
new test run had one incorrect fixture import (19 passed, one failed), corrected
without changing production behavior. An intermediate 77-test run and isolated
settled-render check also passed and overlap the final run. Full-suite and live
provider/model reliability checks remain separately unrun.

Content-free Git inventories are retained under ignored
`state/backups/plain-question-handoff-20261013/`. Prior main is preserved at
`archive/2026-10-13/main-before-plain-question-handoff`. After verification,
commit, fast-forward local main and remove only the merged feature branch.
Other worktrees, historical/unmerged tips and remote refs remain unchanged.

## Interactive question composer, 13 October 2026

`codex/question-composer` starts from clean local main `67e1259`. Clarification
handoffs can now replace the composer with a mixed native question form,
including radio buttons, dropdowns, checkboxes and text. Answer-in-chat retains
the form; existing drafts/attachments/skill selection survive form submission,
and unadmitted answers remain available for retry. Optional history metadata
binds pending forms to their conversation/turn. Tools, runtime permissions,
provider APIs, model profiles, sampling and context limits are unchanged. See
[the contract, lifecycle and verification scope](question-composer.md).

The user requested efficient scope and essential tests only. The final native
run passed **136 checks**, with no failures/errors/skips, in **26.34 seconds**,
using repository-local temporary/cache storage. Results are retained under
ignored `state/question-composer-qualified.xml`; the preceding affected
provider-history round-trip recheck passed **53 checks**, overlapping this run.
The new checks cover all four inference adapter families using synthetic
transports and local/cloud reviewed handoffs with Original and Choom; live
model/API format reliability and the full suite are separately unrun. Synthetic
Qt rendering was visually inspected.

Earlier collection/streaming-assertion errors and default-context failures
remain recorded in their separate XML runs. The two tight default-context
failures also reproduce against the starting main prompt in memory; numeric
evidence is in `state/question-context-baseline/summary.json`. Redundant compact
prompt wording already covered by the core was condensed while adding the
question format. Unchanged default-context acceptance checks now pass; no
sampling, schemas, routing or limits were adjusted.

Content-free ref/worktree inventories are retained under ignored
`state/backups/question-composer-20261013/`. Prior main is preserved at
`archive/2026-10-13/main-before-question-composer`. After verification, commit,
fast-forward local main and remove only this merged feature branch. Other
worktrees, historical/unmerged tips and remote refs remain unchanged.

## Clarification handoff, 13 October 2026

`codex/prompter-question-handoff` starts from clean local main `8246fc9`.
Completion review now accepts a required clarification as ready to return for
the current assistant turn, allowing the user to answer before later workflow
stages. Questions already answered or deferring doable work still require
continuation; real capability failures, denied approvals and unknown outcomes
retain their existing boundaries. Production changes only the review guidance.

The user requested essential tests only. All **40** focused completion and
streaming/UI checks pass natively, including scripted two-turn interview
handoffs in local/cloud modes and existing unfinished-work/approval guards.
The initial new UI assertions incorrectly assumed optional visible-message
metadata was present; they now check the actual runtime outcome. That failed
run is retained separately under ignored `state/prompter-handoff-essential.xml`;
the passing run is `state/prompter-handoff-final.xml`. Scripted checks verify
handoff and context retention, not live model assessment quality. Full-suite
and live provider/model gates are separately unrun. User settings, installed
skills, routing, schemas and model profiles are unchanged.

Prior main is preserved at `archive/2026-10-13/main-before-prompter-handoff`.
After verification, commit, fast-forward local main and remove only the merged
feature branch. Other worktrees and remote refs remain unchanged.

## File-based personalities and Choom v2, 13 October 2026

`codex/personality-core-files` starts from clean local main `8d5e33d`.
Core prompts now own operational, security, tool-use and approval guidance;
one selected file supplies the conversational voice. Original is file-backed,
the supplied Choom 2.0.0 source is retained unchanged, and additional Markdown
or text personalities are discovered on restart without code registration.
Legacy Choom IDs resolve without rewriting private settings. Model profiles,
sampling, routing, tool schemas, runtime permissions, language selection and
history handling are preserved. See [the architecture and authoring guide](personality-files.md).

The affected native run passed **378 checks**, and the final switching/file
checks passed **26 checks**, with no failures, errors or skips. These runs
overlap. An earlier restricted run's three Windows lease denials are sandbox
limitations, not product failures. An initial new oversized-input test lacked
a bounded pytest case ID and exceeded Windows' environment-value limit; its
test ID was corrected, with production behavior unchanged.
The first full native run passed 3,711 checks and 15 subtests, skipped 61 and
failed four in 765.84 seconds. Three failures exposed excessive prompt overhead
at the default full-catalog model limit and a large-read workflow. Redundant
wording was reduced without changing model/context limits, schemas or acceptance
requests; all **96** targeted admission, read and personality checks pass. The
fourth failure was the unchanged paged-reader revision-timestamp check, which
also passes in that isolated group. That first full run remains recorded as
failing in `state/personality-core-full.xml`/`.log`. The second native full
regression rerun passed 3,714 checks and 15 subtests, skipped 61 and failed only
that same unchanged revision-timestamp check in 771.94 seconds. Loading main's
reader and test source in memory reproduced it **26/30** times on synthetic
files. The fixture now advances the changed file's timestamp explicitly;
production reader/security behavior and test acceptance assertions are unchanged.
After the timestamp fixture correction, the third full run passed 3,714 checks
and 15 subtests, skipped 61 and failed one unchanged skill-discovery directory
rename with native Windows access denied in 752.78 seconds. Its unchanged
discovery/loader group passes **85 checks**, with two host symlink skips, in
isolation; no skill-runtime or corresponding test code was changed. Earlier
full runs remain recorded as failing. The fourth full run passed 3,714 checks
and 15 subtests, skipped 61 and failed the unchanged vision-cache identity
fixture in 735.68 seconds. Main's checker/test source reproduces its same-size,
same-timestamp write failure **11/30** times. That fixture now explicitly advances
its changed file's timestamp too; model/projector verification is unchanged.
All **95** combined image, reader, personality and default-admission checks pass
after both fixture corrections. The final native full suite passed **3,715
checks and 15 subtests**, with **61 skips**, no failures/errors, in **736.15
seconds**. Results are retained in ignored
`state/personality-core-final-regression.xml`/`.log`, using repository-local
temporary storage. Earlier full failures remain recorded separately.
Paid live API and real-model style-quality gates are separately unrun.

Content-free refs/worktree inventory is retained under ignored
`state/backups/personality-core-20261013/`. Prior main is preserved at
`archive/2026-10-13/main-before-personality-core`. Commit this bounded
change, fast-forward main and remove only its merged feature branch. Other
worktrees, historical/unmerged tips and all remote refs remain intact.

## Response languages, 13 October 2026

`codex/response-language` starts from local main `410d45d`, then fast-forwards to
the existing committed personality tip `099b4b0` to retain the active launcher's
features. General settings now offer Auto and 45 profile-scoped reply languages,
with shared prompt policy and bounded multilingual presentation recovery. See
[the behavior, storage and verification](response-language.md). Accepted model
profiles, sampling, production context limits, tool schemas and existing user
settings are preserved.

The final affected run passed 387 checks; the recovery/UI/source-scope recheck
passed 170 checks and five subtests. Final full native regression passed **3,689
checks and 15 subtests**, with **61 optional skips**, no failures/errors, in
575.43 seconds. The earlier five full-run failures and their fixture/baseline
diagnosis remain recorded; live API/model language-quality gates are separately
skipped. This passing full run qualifies the combined personality/composer tree
as well as the language change without rewriting the earlier qualification record.

Content-free refs/worktrees are preserved under ignored
`state/backups/response-language-20261013/`; prior main is retained at
`archive/2026-10-13/main-before-response-language`. Commit the bounded change,
fast-forward local main and remove only the merged response-language branch.
Retain the prior personality branch as a recovery tip. Other worktrees and all
remote refs remain intact; no publication is part of this task.

## Profile-level personalities, 13 October 2026

`codex/profile-personalities` starts from main `1315375`. General settings now
select Original or the supplied Choom 1.0.0 voice, with per-profile durable
selection and bundled portable definitions. Original guidance, operational
policy, accepted model profiles and existing user settings are preserved. See
[the storage, packaging and checks](profile-personalities.md).
Prior main is preserved at `archive/2026-10-13/main-before-profile-personalities`.
All 310 affected checks pass. Two full runs recorded separate unchanged runtime
timing and Windows Git installer cleanup failures; all 92 corresponding checks
pass in isolation. Preserve the committed feature branch while its full
regression gate remains unmet. The later UI-only composer polish advanced
local main to `410d45d` and was merged back into this branch; 12 narrow composer
and personality-control checks pass on the combined checkout. After personality
qualification, fast-forward main and remove only the merged feature branch.
Other worktrees and remote refs remain intact.

## Composer effort slider, 13 October 2026

`codex/composer-effort-slider` starts from clean main `f334762`. It moves model,
reasoning and microphone controls beside Send, opens the model menu upward and
replaces the reasoning dropdown with a model-aware slider popup. Existing API
selection and private preferences are retained. See [the change and checks](composer-effort-slider.md).
After native verification, preserve prior main at
`archive/2026-10-13/main-before-composer-effort-slider`, commit, fast-forward
local main and remove only the merged feature branch. Other worktrees and
remote refs remain intact.

## Composer alignment and popup polish, 13 October 2026

`codex/composer-menu-polish` starts from local main `1315375`. It aligns the
composer icons and controls and positions the model list before its first
visible frame. All 58 relevant UI checks passed; the user explicitly excluded
the full suite for this presentation change. See [the fix and checks](composer-menu-polish.md).
Preserve prior main at `archive/2026-10-13/main-before-composer-menu-polish`,
commit, fast-forward local main and remove only the merged UI branch. Bring
updated main back into the preserved `codex/profile-personalities` branch and
leave that branch active. Its earlier qualification record remains unchanged.
Other worktrees and remote refs remain intact.

## Complete integration and cleanup, 13 October 2026

The user explicitly requested all new changes on main, Git cleanup and a push.
`codex/integrate-and-clean` starts at main `189be24` and merges the remaining
14-commit `codex/scroll-behavior-acceptance` branch, preserving main's working
composer, history reader and Responses reasoning fix. See
[integration, verification and cleanup](repository-integration.md).
The older live scroll-repair failures remain historical failures; this explicit
integration request does not reclassify those gates. Recovery tags preserve
both tips and inactive archive branches. Other active worktrees and private
runtime state remain intact. After verification, fast-forward main, remove the
merged feature branches and push only main to origin without rewriting history.

## Responses reasoning-content compatibility, 13 October 2026

`codex/responses-reasoning-compatibility` starts from main `f30a597`. It accepts
the documented optional reasoning `content` field in private Responses replay
evidence, preserving strict validation and existing runtime behavior. The live
synthetic malformed-response reproducer passed after the fix; a live Luna
Medium read/summary run also completed with source and history checks. All 264
affected native deterministic checks passed. See [the fix and qualification](responses-reasoning-compatibility.md).
The full suite was not run under the requested necessary-test scope. Preserve
prior main at `archive/2026-10-13/main-before-responses-reasoning-compatibility`,
commit, fast-forward local main and remove only this merged feature branch.
Retain the earlier unmerged repair branch, other worktrees and remote refs.

## Saved repair-history compatibility, 13 October 2026

`codex/history-evidence-compatibility` starts from composer main `766dba3`.
It retains the known v2 evidence history contract from the unmerged repair
branch so its saved conversations can load, while preserving receipt equality
checks and current runtime behavior. See [the repair and checks](history-evidence-compatibility.md).
All 127 necessary native checks passed, including encrypted startup, retained
archives and sending from the actual composer with a synthetic provider.
The user's encrypted profile remains untouched; live API and full-suite gates
were not run. Preserve prior main at
`archive/2026-10-13/main-before-history-evidence-compatibility`, commit,
fast-forward main and remove only this merged feature branch. Preserve the
earlier unmerged repair branch, other worktrees and all remote refs.

## Composer model and reasoning selection, 13 October 2026

`codex/composer-model-reasoning` starts from verified local main `aae279a`.
It adds composer model/reasoning controls and a microphone placeholder,
with per-model reasoning preferences in ignored or encrypted state. Effective
API requests use the selection while preserving versioned profiles, prompts,
tools, routing, and context limits. See [the change and checks](composer-reasoning.md).
The necessary native run passed 246 tests. The full suite and live repair gates
were not run by user request. Preserve prior main at
`archive/2026-10-13/main-before-composer-reasoning`, commit, fast-forward local
main and remove only this merged feature branch. Retain the unmerged
`codex/scroll-behavior-acceptance` branch and other worktrees; no publication.

## Complaint-driven repair qualification, 13 October 2026

`codex/scroll-behavior-acceptance` starts from verified local main `aae279a`.
It adds bounded checkpoint evidence, source-grounded repair diagnosis, revision
and failed-check progress tracking, and completion review scoped to the user's
request. See [the contract and qualification](complaint-repair-loop.md).
Content-free refs and worktree inventory are retained under
`state/backups/complaint-repair-20261012`; prior main is preserved at
`archive/2026-10-12/main-before-complaint-repair`. Profiles, sampling, routing,
context policy and user settings remain unchanged. The original later prompt
is unavailable and its exact replay is separately skipped.
Integration requires repeated independent live behavioral acceptance as well
as deterministic checks. Final live qualification passed 0/3 replays. The final
full suite recorded one unchanged installer cleanup failure; its 60-test group
passed in isolation. Preserve the feature branch and verified main while
the gates remain unmet. Once qualified, fast-forward local main and remove only its
merged feature branch. Preserve other worktrees and remote branches; no publication.

## Native cloud reversal recovery, 12 October 2026

`codex/native-reversal-recovery` starts from local main `ce21a68`. It adds a
bounded tool argument for rollback explanations, renews required source reads,
permits one diagnosis into a new revision after a blocked second rollback,
preserves existing cloud edit evidence, and keeps inspection from resetting
an already visible scroll-driven section. The final full suite passed 3,453
checks with 61 skips; the unchanged default-cloud three-prompt replay completed.
See [the contract and qualification](native-reversal-recovery.md).
Production prompts, routing, sampling, context policy, profiles and user settings
remain unchanged. Content-free refs/worktrees are retained under
`state/backups/native-reversal-20261012/`. After verification, preserve prior main
at `archive/2026-10-12/main-before-native-reversal-recovery`, commit, fast-forward
local main and remove only the merged feature branch. Preserve other worktrees,
historical/unmerged tips and remote branches; no publication.

## Cloud inspection recovery and regression qualification, 12 October 2026

`codex/cloud-recovery-and-regressions` starts from local main `c9dddd3`. It fixes
required recovery reads, bounded duplicate-check reassessment, concrete
inspection errors, conflicting no-change feedback, preview memory limits and
final viewport capture checks. See [the repair and qualification](cloud-recovery-and-regressions.md)
for full-suite results, the unchanged default-cloud replay, visually reviewed
captures and separately recorded skipped gates. Production prompts, routing,
sampling, context policy, accepted profiles and user settings are preserved.
Content-free refs/worktrees are retained under `state/backups/full-repair-20261012/`
and prior main at `archive/2026-10-12/main-before-cloud-recovery-and-regressions`.
After verification, commit, fast-forward local main and remove only the merged
feature branch. Preserve other worktrees, historical/unmerged tips and remote
branches; no publication.

## Windows project command recovery, 12 October 2026

`codex/project-command-recovery` starts from local main `053fbb6`. It resolves
Windows npm build/preview commands to installed Node/npm-cli.js, exposes and
binds that command to approval, and gives actionable executable recovery errors.
See [the repair and qualification](project-command-recovery.md). All 140
necessary checks passed, including real npm build/preview execution and the
reported request through scripted runtime recovery. Full-suite and live model
gates were not run by request. Preserve content-free refs/worktrees under
`state/backups/project-command-recovery-20261012/` and prior main at
`archive/2026-10-12/main-before-project-command-recovery`. Commit, fast-forward
local main and remove only the merged feature branch. Preserve configuration,
other worktrees, historical/unmerged tips and remote refs; no publication.

## Visual verification and useful rechecks, 12 October 2026

`codex/visual-verification-recovery` starts from local main `3a79fdb`. It renews
project checks after proven edits, delivers verified inspection pixels to
vision-capable models, adds bounded intro/viewport/model readiness checks and
directs already-present patches toward diagnosis. See
[the repair and qualification](visual-verification-recovery.md). Necessary
qualification passed 314 distinct checks; the final affected run passed 93,
with one host symlink skip. Four older fixture failures reproduce on unchanged
main and remain separate. Full-suite and live inference gates were not run by
request. Preserve content-free refs/worktrees under
`state/backups/visual-verification-recovery-20261012/` and prior main at
`archive/2026-10-12/main-before-visual-verification-recovery`. Commit,
fast-forward local main and remove only the merged feature branch. Preserve
other worktrees, historical/unmerged tips and configuration; no publication.

## Interrupted-operation recovery, 11 October 2026

`codex/operation-review-recovery` starts from local main `3ec1c1f`. It replaces
the global conversation lock with operation-level guards and exposes explicit
human review of uncertain outcomes. Chat and permitted reads remain available;
further changes retain their review and approval requirements. Necessary
qualification passed 195 distinct checks, including actual Qt interaction,
scrolling, native edits and encrypted profile recovery. One older configuration
fixture also fails on unchanged main and is recorded separately. See
[the contract and qualification](operation-review-recovery.md). Preserve
content-free evidence under `state/backups/operation-review-recovery-20261011/`
and prior main at `archive/2026-10-11/main-before-operation-review-recovery`.
Commit, fast-forward local main and remove only the merged feature branch.
Preserve configuration, historical refs, other worktrees and remote branches;
no publication.

## Persistent shell sessions, 11 October 2026

`codex/persistent-shell-sessions` starts from local main `f35d4a5`. It adds
explicit managed background sessions to the existing shell tool, with status,
stop, bounded logs/lifetimes and runtime shutdown cleanup. Ordinary commands
retain their current lifecycle and approvals. The real npm start/status/stop
chat passed with independent HTTP checks and released owned processes; 205
distinct focused checks passed, including actual browser interactions. See
[the contract and qualification](persistent-shell-sessions.md). Preserve
content-free integration evidence under
`state/backups/persistent-shell-sessions-20261011/` and prior main at
`archive/2026-10-11/main-before-persistent-shell-sessions`. Commit, fast-forward
local main and remove only the merged feature branch. Preserve other worktrees,
historical refs, configuration and remote branches; no publication.

## Recursive filename searches, 11 October 2026

`codex/recursive-file-search` starts from local main `1e47484`. It guides
unknown-location file requests through approved recursive filename-only shell
searches and constrains cloud completion reviews to the current goal's JSON
schema. The unchanged two-prompt live reproduction first missed nested files
and stopped on invalid reviews; both repaired runs found all three synthetic
matches and completed. Necessary focused qualification passed 174 distinct
checks. See [the contract and qualification](recursive-file-search.md).
Preserve content-free integration evidence under
`state/backups/recursive-file-search-20261011/` and prior main at
`archive/2026-10-11/main-before-recursive-file-search`. Commit, fast-forward local
main and remove only the merged feature branch. Preserve other worktrees,
historical refs and configuration; no remote publication.

## Shell output and preview recovery, 11 October 2026

`codex/shell-repeat-recovery` starts from local main `1198acb`. It flushes
PowerShell object output, makes owned preview-server recovery explicit, separates
failed checks from unavailable inspection and preserves execution reports through
supporting source reads. The final unchanged live shell prompt completed in 18
requests with its reviewed report intact. Necessary focused qualification passed
105 distinct tests; intermediate failed live gates remain separately recorded.
See [the repair and qualification](shell-repeat-recovery.md). Preserve content-free
integration evidence under `state/backups/shell-repeat-recovery-20261011/` and prior
main at `archive/2026-10-11/main-before-shell-repeat-recovery`. Commit, fast-forward
local main and remove only the merged feature branch. Preserve other worktrees,
historical refs and user configuration; no remote publication.

## General shell access, 11 October 2026

`codex/general-shell-access` starts from local main `2c2e33b`. It adds approved
PowerShell/cmd commands with an absolute working folder, output/exit status,
bounded deadlines and owned descendant cleanup. Existing review preferences
and exact-call permissions remain in force. Both installed project-tool probes
passed; 206 distinct focused checks passed. Six older catalog fixture failures
also reproduce on unchanged main and are recorded separately. See
[the contract and qualification](general-shell-access.md). Only necessary checks
ran; no full suite or live inference gate. Content-free preservation evidence is
under `state/backups/general-shell-access-20261011/`; prior main is retained at
`archive/2026-10-11/main-before-general-shell-access`. Commit, fast-forward local
main and remove only the merged feature branch. Preserve existing settings,
historical tips and other worktrees; no remote publication.

## Browser verification and answer retention, 11 October 2026

`codex/browser-verification-preview` starts from local main `84ee315`. It fixes
preview-startup callback failures, local development sockets and rejected socket
cleanup, and keeps the answer visible through stream resets and final context
refresh. Both development and built previews of the user's Vite project passed
inspection; 68 focused checks passed. See [the repair and qualification](browser-verification-preview.md).
Retain content-free integration evidence under
`state/backups/browser-verification-preview-20261011/` and prior main at
`archive/2026-10-11/main-before-browser-verification-preview`. Commit,
fast-forward local main and remove only the merged feature branch. Preserve
configuration, historical tips and other worktrees; no remote publication.

## Bounded completion checks, 11 October 2026

`codex/bounded-completion-check` starts from local main `c45f42f`. A live run
reproduced another completion tool loop after the streamed summary. Review is
now assessment-only, with provider tool selection disabled and a runtime guard
before execution. Continue assessments resume ordinary work in the same turn.
See [the contract and live qualification](bounded-completion-check.md). Both
repaired fresh live chats completed in seven requests; 354 distinct focused
checks passed. Preserve content-free refs/worktrees under
`state/backups/bounded-completion-check-20261011/` and prior main at
`archive/2026-10-11/main-before-bounded-completion-check`. Commit, fast-forward
local main and remove only the merged feature branch. Other worktrees and
historical/unmerged tips remain intact; no remote publication.

## Live completion loop, 11 October 2026

`codex/live-completion-loop` starts from local main `afc4e14`. A live reproduction
found that review tool calls discarded the proposed answer, causing ready JSON
to become another answer and trigger repeated reviews. Candidate retention and
explicit review streaming now keep assessments separate from user answers.
See [the repair and live verification](live-completion-loop.md). Two fresh live
cloud chats completed after repair; 210 focused native checks passed. Only
necessary checks ran. Preserve content-free refs/worktrees under
`state/backups/live-completion-loop-20261011/` and prior main at
`archive/2026-10-11/main-before-live-completion-loop`. Commit, fast-forward local
main and remove only the merged feature branch. Other worktrees and historical
tips remain intact; no remote publication.

## Stable active-turn recall, 11 October 2026

`codex/stable-turn-recall` starts from local main `3b9ed54`. Immutable bounded
history snapshots prevent an active turn's own read receipts from invalidating
its next page; nested recall bodies are omitted from recovered history. See
[the repair and focused qualification](stable-turn-recall.md). Qualification
passed 155 distinct focused checks, including a simulated first cloud turn
through the real streaming adapter. Full-suite and live provider/model gates
remain unrun by request. Before integration, retain content-free refs/worktrees
under `state/backups/stable-turn-recall-20261011/` and prior main at
`archive/2026-10-11/main-before-stable-turn-recall`. Commit, fast-forward local
main and remove only the merged feature branch. Other worktrees and historical
tips remain intact; no remote publication.

## Project verification, context and paging, 11 October 2026

`codex/verification-context-paging` starts from local main `527b5e9`. It adds
approved bounded project build/test execution and browser/desktop inspection,
loss-aware long-conversation context with original history recovery, and
revision-bound contiguous source paging. See [the contract and qualification](verification-context-paging.md).
Only necessary focused checks run; full-suite and live model/provider gates are
unrun by request. Qualification passed 380 distinct focused native checks with
one host symlink skip, including real browser and desktop inspection. Before
local integration, retain content-free refs/worktrees
under `state/backups/verification-context-paging-20261011/` and prior main at
`archive/2026-10-11/main-before-verification-context-paging`. Commit, fast-forward
local main and remove only the merged feature branch. Other worktrees and
historical/unmerged tips remain intact; no remote publication.

## Current request and completion checks, 11 October 2026

`codex/current-task-completion` starts from local main `dd2da89`. It separates
the latest request from standing requirements and historical work, checks a
proposed final answer against requested work, and continues routine source reads
and corrected patches within the same turn. Known denied or unresolved edits
cannot be marked complete by a positive model review. Existing authority and
budgets remain in force; a normal final answer adds one model review request.
See [the contract and qualification](current-task-completion.md).

Qualification passed 479 distinct focused native tests with one host symbolic-link
skip. Only necessary checks ran; no full suite or live model/provider gate.
Pre-integration refs/worktrees are retained under ignored
`state/backups/current-task-completion-20261011/`; preserve prior main at
`archive/2026-10-11/main-before-current-task-completion`. Commit, fast-forward
local main and remove only the merged feature branch, preserving other worktrees
and historical/unmerged tips. No remote publication.

## Transparent application icon, 10 October 2026

`codex/app-logo-icon` starts from local main `8295169`. The unchanged bundled
transparent logo now provides application, taskbar, tray and shortcut artwork.
New nodes/pilot packages include the multi-size ICO and host shortcut creator.
Twenty-seven distinct focused native checks and an updated relocated-node
launch passed; see [usage and verification](app-icon.md). A branded local Desktop
shortcut was created and its shell identity verified. Seventeen preservation
fingerprints and four other worktree attachments are unchanged. Recovery:
`state/backups/app-logo-icon-20261010/`; prior main:
`archive/2026-10-10/main-before-app-logo-icon`. Commit, fast-forward local main,
then delete only the merged feature branch. No full suite, live provider/model
calls, distributed ZIP rebuild or remote publication.

## Portable-node identity and drive naming, 10 October 2026

`codex/portable-node-identity` starts from local main `5c5123c`. Portable/pilot
installations hide deployment and reject it in the exporter. Local deployment
reserves numbered node names and labels recognized external Windows volumes
after publication, with shorter names for FAT/exFAT and explicit rename-failure
feedback. Fifty focused native cases and an updated relocated-node launch
passed; see [usage and verification](portable-node-deployment.md#portable-node-restrictions-and-drive-names).
No real drive labels changed. No full suite, live provider/model or physical-media
qualification ran. Seventeen preservation fingerprints and four other
worktree attachments are unchanged. Evidence is under
`state/backups/portable-node-identity-20261010/`; prior main is preserved at
`archive/2026-10-10/main-before-portable-node-identity`. Commit, fast-forward
local main and remove only the merged feature branch. No remote publication.

## Portable-node deployment, 10 October 2026

`codex/deploy-portable-nodes` starts from local main `1627bfb`. Settings can
deploy a fresh node or copy the current profile, with optional installed local
models. Encrypted export includes skills, stored files, settings, credentials
and managed backups while retaining the source selection. Forty-one distinct
focused native cases and an actual relocated-node launch passed; see
[verification and usage](portable-node-deployment.md). Only necessary checks
ran; no full suite, live inference/provider call or physical-device gate.

Sixteen preservation fingerprints and the four other worktree attachments are
unchanged. Recovery evidence is under `state/backups/deploy-portable-nodes-20261010/`.
Prior main is preserved at `archive/2026-10-10/main-before-deploy-portable-nodes`.
Commit, fast-forward local main and remove only the merged feature branch.
No remote publication.

## Missing selected profiles, 10 October 2026

`codex/missing-profile-entry` starts from local main `e596c1a`. Missing saved
profile locations now show a dedicated recovery/creation screen before asking
for credentials. The locator remains available for disconnected-drive recovery;
unlock rechecks presence and distinguishes missing, incomplete and inaccessible
storage. Thirty-two distinct focused native cases and an appearance check
passed; see [verification](settings-finish-verification.md#missing-selected-profiles-10-october-2026).
Only necessary checks ran; no full suite, live provider call or portable rebuild.

Fourteen preservation fingerprints and the four other worktree attachments are
unchanged. Recovery evidence is under `state/backups/missing-profile-entry-20261010/`.
Preserve prior main at `archive/2026-10-10/main-before-missing-profile-entry`, commit,
fast-forward local main and remove only the merged feature branch.
No remote publication.

## Profile-first startup, 10 October 2026

`codex/profile-first-startup` starts from local main `02b20d4`. It removes the
login branding, standardizes profile terminology and makes fresh startup show
only Create profile before composing chat. Existing selected-profile and
explicit unencrypted-storage actions remain. Twenty-eight distinct focused
native cases and an appearance check passed; see
[verification](settings-finish-verification.md#profile-first-startup-and-terminology-10-october-2026).
Only necessary checks ran; no full suite, live provider call or portable rebuild.

Fourteen preservation fingerprints and the four other worktree attachments are
unchanged. Recovery evidence is under `state/backups/profile-first-startup-20261010/`.
Preserve prior main at `archive/2026-10-10/main-before-profile-first-startup`, commit,
fast-forward local main and remove only the merged feature branch.
No remote publication.

## Vault login redesign, 10 October 2026

`codex/vault-login-redesign` starts from local main `6d6117d`. It matches the
login background to Settings and reorganizes the existing controls into a
centered login card. All original actions and authentication handlers remain.
Eleven focused native cases and a separate appearance/action check passed; see
[verification](settings-finish-verification.md#vault-login-redesign-10-october-2026).
Only necessary checks ran; no full suite, live provider call or portable rebuild.

Fourteen preservation fingerprints and the four other worktree attachments are
unchanged. Recovery evidence is under `state/backups/vault-login-redesign-20261010/`.
Preserve prior main at `archive/2026-10-10/main-before-vault-login-redesign`, commit,
fast-forward local main and remove only the merged feature branch.
No remote publication.

## Settings accent palette, 10 October 2026

`codex/settings-accent-palette` starts from local main `6650355`. It replaces
neutral charcoal Settings control surfaces with flat slate blue `#243247`,
coordinates interaction states, and shares the palette with profile menus and
switch tracks. Eight focused native cases and an isolated visual check passed;
see [verification](settings-finish-verification.md#slate-blue-settings-controls-10-october-2026).
Only necessary checks ran; no full suite, live provider call or portable rebuild.

Fourteen preservation fingerprints and the four other worktree attachments are
unchanged. Recovery evidence is under `state/backups/settings-accent-palette-20261010/`.
Preserve prior main at `archive/2026-10-10/main-before-settings-accent-palette`,
commit, fast-forward local main and remove only the merged feature branch.
No remote publication.

## Settings gradient colors, 10 October 2026

`codex/settings-gradient` starts from local main `8c2796f`. Only the two Settings
panel gradient colors change, to `#090c15` and `#1d2637`. Radius, border, direction
and layout are preserved. Two existing native geometry cases and an exact-update
windowless visual/pixel check passed; see
[verification and portable update](settings-finish-verification.md#requested-darker-settings-gradient-10-october-2026).
Only necessary tests ran; no full suite or live provider call.

Fourteen preservation fingerprints and the four other worktree attachments are
unchanged. Recovery evidence is under `state/backups/settings-gradient-20261010/`.
Preserve prior main at `archive/2026-10-10/main-before-settings-gradient`, commit,
fast-forward local main and remove only the merged feature branch. The small
portable update includes the preceding number-field fix; original artifacts are
preserved. No remote publication.

## Profile number fields, 10 October 2026

`codex/profile-number-fields` starts from local main `3803022`. A compact-input
style correction prevents Qt 6.12 from collapsing the four profile number
editors. Eight focused native executions across five cases passed on the pilot
and working Qt versions; the exact one-file update also passed in a synthetic
encrypted pilot using its actual windowless runtime. See
[verification and update instructions](profile-number-fields.md). Only necessary
tests ran; no full suite or live provider call.

Fourteen preservation fingerprints and the four other worktree attachments are
unchanged. Recovery evidence is under ignored
`state/backups/profile-number-fields-20261010/`. Preserve prior main at
`archive/2026-10-10/main-before-profile-number-fields`, commit, fast-forward local
main and remove only the merged feature branch. The small update ZIP remains
under ignored `dist/`; the original pilot is preserved. No remote publication.

## Cloud-only portable pilot, 10 October 2026

`codex/portable-pilot-package` starts from local main `bdf3d66`. It adds a bounded
public-file assembler and produces the user's selected cloud-only pilot ZIP
from committed application files and the previously verified fresh runtime.
No application behavior or user settings change. Nine package cases, exact ZIP
inventory/checksum, actual launcher, offline runtime checks and native encrypted
profile create/restart/relocation passed; see [the artifact record](portable-pilot-package.md).
Only necessary tests ran; no full-suite repetition or live provider/model gates.

Fourteen preservation fingerprints and the four other worktree attachments are
unchanged. Recovery evidence is under ignored
`state/backups/portable-pilot-package-20261010/`. Preserve prior main at
`archive/2026-10-10/main-before-portable-pilot-package`, commit, fast-forward
local main and remove only the merged feature branch. The sanitized ZIP remains
under ignored `dist/`; no remote publication. Physical-media and second-host
qualification remain pending.

## Portable regression test maintenance, 10 October 2026

`codex/portable-regression-gates` starts from local main `c6aa4f9`. It repairs five
stale history-save injections, two startup setups and off-screen radio input in
two profile cases, preserving their original acceptance assertions. Only tests
and notes change. All nine affected cases pass off-screen, and the four UI cases
also pass on native Windows; see [verification](portable-regression-gates.md).
The full suite was not repeated at the user's request to run only necessary
tests. No live provider/model gates.

Fourteen preservation fingerprints and the four other worktree attachments are
unchanged. Recovery evidence is under ignored
`state/backups/portable-regression-gates-20261010/`. Preserve prior main at
`archive/2026-10-10/main-before-portable-regression-gates`, commit, fast-forward
local main and remove only the merged feature branch. No remote publication.

## Portable encrypted-profile packaging, 10 October 2026

`codex/portable-vault-packaging` starts from local main `8335102`. Fresh runtimes
now install pinned PyNaCl, and the shared offline package check verifies a real
synthetic portable vault through lock, reopen and cleanup. The same fresh build
exposed and fixed cloud-option splatting in PowerShell. The existing user runtime
and profile selection are preserved.

125 focused native cases and an actual clean cloud-runtime build passed; see
[verification and regression limitations](portable-vault-packaging.md). The full
suite is recorded separately from focused passes, including its pre-existing
failures and the aborted native Windows attempt. No live provider/model or
physical-media qualification is claimed.

Recovery refs, worktree tips and fourteen content-free preservation entries are
under ignored `state/backups/portable-vault-packaging-20261010/`. Prior main is
preserved at `archive/2026-10-10/main-before-portable-vault-packaging`. Commit,
fast-forward local main and remove only the merged feature branch. No remote
publication or changes to another worktree.

## Desktop startup splash, 10 October 2026

`codex/splash-launch` starts from main `70d4d28`. The desktop entry point now
presents the bundled animated splash on every fresh launch before composing
login or chat. Twenty-six focused native cases passed, including five actual
`pythonw.exe` entry-point cases; see [verification](splash-launch-verification.md).
No full suite or live gates. Recovery refs, worktree tips and twelve unchanged
preservation entries are under ignored `state/backups/splash-launch-20261010/`.
Preserve prior main at `archive/2026-10-10/main-before-splash-launch`, commit,
fast-forward local main, publish under the user's chat authorization and remove
the merged branch.

## Profile deletion and no-profile splash, 10 October 2026

`codex/profile-delete-startup` starts from main `c8be6fc`. Confirmed deletion removes
the complete profile, credentials, managed backups and recorded external copies,
with safe staging and persistent retries. No-profile continuation now receives
the same loading splash. Forty focused native cases and three synthetic visual
previews passed; see [verification](profile-delete-startup-verification.md).
No full suite, actual user-profile deletion or live gates. Recovery refs, worktree
tips and twelve preservation entries are under ignored
`state/backups/profile-delete-startup-20261010/`. Preserve prior main at
`archive/2026-10-10/main-before-profile-delete-startup`, commit, fast-forward local
main, publish under the user's chat authorization and remove the merged branch.

## Clear vault import browsers, 10 October 2026

`codex/vault-import-browser` starts from main `0181919`. Data now exposes file and
folder browsers for arbitrary host documents, separately from the clearly labeled
previous-installation import. Nineteen focused native cases and normal/minimum-size
visual previews passed; see [the verification record](vault-import-browser-verification.md).
No full suite or live gates. Recovery refs, worktree tips and configuration/artwork
fingerprints are under ignored `state/backups/vault-import-browser-20261010/`.
Preserve prior main at `archive/2026-10-10/main-before-vault-import-browser`, commit,
fast-forward local main, publish under the user's chat authorization and remove
only the merged feature branch.

## Quicker Settings navigation, 10 October 2026

`codex/settings-navigation-speed` starts from main `b62882a`. Settings sections
and profile tabs reveal in 50 ms with a faster initial easing curve. Six focused
native checks passed; see [the verification record](settings-finish-verification.md#quicker-settings-navigation-10-october-2026).
No full suite or live gates. Content-free recovery evidence is under ignored
`state/backups/settings-navigation-speed-20261010/`. Preserve prior main at
`archive/2026-10-10/main-before-settings-navigation-speed`, commit, fast-forward
local main and remove only the merged feature branch.

## Smaller splash and faster tabs, 10 October 2026

`codex/splash-motion-tuning` starts from local main `e1e7da0`. The splash logo now
has a 64-pixel cap, retaining its center and slow pulse. Both levels of Settings
tabs transition in 100 ms. Three focused native cases and a measured/visually
inspected splash capture passed; no full suite or live gates. See the
[verification follow-up](settings-finish-verification.md#smaller-splash-and-faster-tabs-10-october-2026).
Ten settings/artwork fingerprints and other worktree tips are preserved under
ignored `state/backups/splash-motion-tuning-20261010/`. Preserve prior main at
`archive/2026-10-10/main-before-splash-motion-tuning`, commit, fast-forward local
main and remove only the merged local branch. No remote publication.

## Settings consistency, transitions and loading logo, 10 October 2026

`codex/settings-finish` starts from local main `73304f5`, preserving the user's
uncommitted replacement loading background. The requested redundant profile
badges and credential explanation/footer are removed. A shared palette unifies
dropdowns and action buttons, saved-record selection is refined, and both levels
of Settings tabs reveal smoothly without changing panel geometry. The supplied
logo is bundled and pulses over the preserved background throughout loading.

Twenty-nine distinct focused native Windows cases passed, including the console
and windowless portable Python runtimes, blocked-parent pulse, topmost display,
early helper exit, fallback, navigation, save/lock clearing, desktop ownership
and shutdown. Synthetic local/portable visual probes also passed. No full suite,
live API/model calls or actual user-vault access. See
[focused verification](settings-finish-verification.md).
Nine configuration/artwork fingerprints and other worktree tips are preserved.
Recovery evidence and the user's original replacement asset are under ignored
`state/backups/settings-finish-20261010/`. Preserve prior main at
`archive/2026-10-10/main-before-settings-finish`, commit, fast-forward local main
and remove only the merged local feature branch. No remote publication.

## Stable Settings panel size, 10 October 2026

`codex/settings-panel-size` starts from local main `ad75989`. Personal profile
had a larger sizing rule than other Settings sections, causing the outer panel
to grow/shrink during navigation. All sections now use the normal 1120 × 740
preferred size, clamped to the available window. Navigation no longer refits
or recenters the panel. The five profile tabs retain their internal scrolling.

The native regression reproduced the bug before the fix. Six focused native
Windows cases now pass, covering local/portable profiles, normal/maximized/full
screen and minimum-size navigation, dragging and profile edit/save/lock behavior.
The full suite was not run. See the
[verification follow-up](vault-profile-tabs-verification.md#stable-panel-size-follow-up-10-october-2026).
Eight settings fingerprints and other worktree tips are preserved. Recovery
evidence is under ignored `state/backups/settings-panel-size-20261010/`.
Preserve prior main at `archive/2026-10-10/main-before-settings-panel-size`, commit,
fast-forward local main and remove only the merged local branch. No remote
publication.

## Tabbed personal profile settings, 9 October 2026

`codex/vault-profile-tabs` starts from local main `b07dc62`. The user selected
the focused-tabs mockup. The native page now has a persistent summary and compact
profile management, with Storage, Cloud access, Backups, Security and Data tabs.
Cloud policy uses radio choices with explicit Apply; credential save consent,
existing vault actions and lock cleanup retain their behavior. Same-profile
import rebuilds retain the current tab. See
[focused verification](vault-profile-tabs-verification.md).

Fifty-six distinct focused native Windows checks passed. Isolated local/portable
probes checked all five tabs at three window sizes, including the supported
minimum, without horizontal clipping. No full suite or live provider/model checks.
Eight settings fingerprints and other worktree tips are preserved. Recovery
evidence is under ignored `state/backups/vault-profile-tabs-20261009/`.
Preserve prior main at `archive/2026-10-09/main-before-vault-profile-tabs`, commit,
fast-forward local main and remove only the merged local branch. No remote
publication.

## Vault controls, login blur and layout concepts, 9 October 2026

`codex/vault-polish-concepts` starts from local main `dc2eb8d`. Backup retention
fields now match compact quota controls and ignore scrolling. Login blurs its
backdrop, and the loading picture fades out over 560 ms after the replacement is
raised and painted. The user-requested research and two saved mockups propose
the broader settings redesign without implementing it. See
[focused verification](vault-polish-concepts-verification.md).

Twenty-one focused native Windows checks passed, plus local/portable controls
and native fade/stacking/failure checks. No full suite or live provider/model
checks. All eight settings fingerprints and other worktree tips are preserved.
Recovery evidence is under ignored `state/backups/vault-polish-concepts-20261009/`.
Preserve prior main at `archive/2026-10-09/main-before-vault-polish-concepts`,
commit, fast-forward local main and remove only the merged local branch.
No remote publication.

## Vault login and settings controls, 9 October 2026

`codex/vault-login-settings` starts from local main `f7eb507`. All app dropdowns
ignore wheel changes, the unused credential-file import button is removed, and
quota uses the compact minutes-sized field with a small inline Change quota
button. Locked startup now uses a separate login panel in the existing style;
successful login opens the main app. See
[focused verification](vault-login-settings-verification.md).

Twenty-six focused native Windows checks passed, plus synthetic local/portable
interaction/layout checks and an actual desktop-entrypoint/repeated-launch probe.
No full suite or live provider/model checks. All eight settings/selection
fingerprints match; other worktrees and actual user vault/processes are untouched.
Recovery evidence is under ignored `state/backups/vault-login-settings-20261009/`.
Preserve prior main at `archive/2026-10-09/main-before-vault-login-settings`,
commit, fast-forward local main and remove only the merged local branch.
No remote publication.

## Compact idle-lock controls, 9 October 2026

`codex/vault-idle-controls` starts from local main `8a6b7b2`. The idle-lock row
now reuses the tool-approval switch with a 72-pixel typed minutes field and
128-pixel inline save button. Wheel changes and spinner buttons are removed;
Save preserves the existing zero/off or positive-minutes setting. See
[focused verification](vault-idle-controls-verification.md).

Seven existing focused Windows checks passed. Native local/portable checks
verified toggle/save/restart behavior, 16 wheel cases and minimum-width layout;
panel captures were visually inspected. No full suite or live provider/model
checks. All eight settings/selection preservation entries match; actual user
profiles and running processes were left alone. Recovery evidence is under
ignored `state/backups/vault-idle-controls-20261009/`. Preserve prior main at
`archive/2026-10-09/main-before-vault-idle-controls`, commit, fast-forward main
and remove only the merged local branch. No remote publication.

## Vault picture stacking and fades, 9 October 2026

`codex/vault-picture-fade` starts from local main `e21cd84`. The loading picture
now stays above application windows and fades in/out with 240 ms cubic easing.
Fade-in completes before blocking composition; fade-out reveals the ready view.
Retired views are collected after the fade's local event loop. See
[focused verification](vault-picture-fade-verification.md).

Twenty-three existing focused Windows checks passed. Native local/portable
checks verified the actual topmost style, stacking above a separate test process,
intermediate native opacity values in both directions, geometry and failed-load
cleanup. An actual desktop-entrypoint/repeated-launch probe also passed. The full
suite and live provider/model tests were not run. All eight settings/selection
preservation entries match; the user vault and running instance were left alone.
Recovery evidence is under ignored `state/backups/vault-picture-fade-20261009/`.
Preserve prior main at `archive/2026-10-09/main-before-vault-picture-fade`, commit,
fast-forward main and remove only the merged local branch. No remote publication.

## Vault unlock picture, 9 October 2026

`codex/vault-unlock-picture` starts from local main `c7f8916`. Successful unlock
now shows the user's supplied picture over the previous window while the unlocked
profile is composed. The original image is bundled unchanged in UI assets and
included in package data; the existing compiled build already includes that
asset directory. See [focused verification](vault-unlock-picture-verification.md).

Twenty-three existing focused Windows checks passed, plus native visual checks
for normal/maximized windows, failed initialization and a relocated portable
asset, and an actual desktop-entrypoint/repeated-launch probe. No full suite or
live provider/model tests were run. All eight configuration/selection preservation
entries match; the actual user vault and running instance were left alone.
Content-free recovery evidence is under ignored
`state/backups/vault-unlock-picture-20261009/`. Preserve prior main at
`archive/2026-10-09/main-before-vault-unlock-picture`, commit, fast-forward main
and remove only the merged local branch. Remote branches remain untouched.

## Desktop unlock/window and saved-key follow-up, 9 October 2026

`codex/vault-unlock-lifecycle` starts from local main `39da460`. The user reported
two windows and another cloud-key prompt after unlock. Six synthetic reproductions
exposed stale window activation, obsolete unlock actions and duplicate consumer
composition after rejected actions. The fix retires/guards old views, keeps a
valid current session after rejection, coordinates repeated desktop launches and
shows explicit saved-key availability/use choices. See
[focused verification](vault-unlock-lifecycle-verification.md).

Ninety-five distinct focused checks passed, including 23 on Qt's native Windows
platform, plus an isolated native desktop entrypoint/two-process probe. The full
suite was not run. All eight settings/profile-selection hashes/absence and other
worktree tips are preserved; no actual vault was opened. Recovery evidence is under
ignored `state/backups/vault-unlock-lifecycle-20261009/`. Preserve prior main at
`archive/2026-10-09/main-before-vault-unlock-lifecycle`, commit, fast-forward local
main and remove only the merged feature branch. No remote publication is authorized.

## Saved cloud credential correction, 9 October 2026

`codex/vault-cloud-credentials` starts from local main `4b9defa`. The reported
saved-key prompt reproduced in local/portable synthetic UI checks: Save ignored
the selected policy without a separate Apply click, and a cancelled prompt could
cache a missing key. Save/import now apply the explicit policy, saved API-key
replacement invalidates the affected cached connection, and feedback explains
intentional Ask mode. See [focused verification](vault-cloud-credentials-verification.md).

Fourteen new and 40 affected existing checks passed; the full suite was not run.
All eight recorded settings/profile-selection hashes/absence match. Preserve
prior main at `archive/2026-10-09/main-before-vault-cloud-credentials`, commit the
bounded fix, fast-forward local main and remove its merged feature branch.
Content-free preservation evidence is under ignored
`state/backups/vault-cloud-credentials-20261009/`. Other worktrees, personal
profiles and remote branches remain untouched; no remote publication is authorized.

## Personal Vault phase 4 setup and controls, 9 October 2026

`codex/vault-phase4` starts from verified local main `30053f6`. The user authorized
all phase 4 items and 4.1 and requested necessary tests only; the 2000+ suite is
excluded. Settings gains personal-profile setup/selection/unlock, credentials,
migration/original cleanup, quota/recovery/backup/restore/relocation, retention
and dismissible protected-storage guidance. See [the contract](vault-phase4-contract.md)
and [focused verification](vault-phase4-verification.md).

Focused checks passed 267 distinct cases with no final failures/errors/skips.
Real SSD, minimum-host, live provider/model and independent security gates remain
deferred; phase 5 is not started. All seven recorded user configuration/state
hashes/absence and other worktree tips are preserved. Content-free preservation
evidence is under ignored `state/backups/vault-phase4-20261009/`. The bundled
runtime gains already available, hash-verified pinned crypto dependencies without
replacing existing settings. Preserve prior main at
`archive/2026-10-09/main-before-vault-phase4`, commit the bounded change,
fast-forward local main and remove only the merged local feature branch.
No remote publication is authorized.

## Personal Vault phase 3 application integration, 9 October 2026

`codex/vault-phase3` starts from verified local main `d456cd3`. The user authorized
the next roadmap phase and necessary tests only, keeping physical SSD,
minimum-machine and independent security qualification deferred. This phase
connects an explicitly selected profile to private application state, attachments,
generated images, skills/references, diagnostics and shared credential policy;
it adds lock/switch cancellation, revocation and tool-path exclusions.
See [the contract](vault-phase3-contract.md) and
[focused verification](vault-phase3-verification.md). Setup/migration UI remains
phase 4; existing unencrypted startup remains the default until explicit selection.

Focused verification covers 271 distinct passed checks and two existing Windows
symlink skips. The full suite and live provider/model/hardware gates were not run.
Pre-change refs/worktree maps and content-free settings hashes are under ignored
`state/backups/vault-phase3-20261009/`. After verification, preserve previous main
at `archive/2026-10-09/main-before-vault-phase3`, commit the bounded change,
fast-forward local main and remove only the merged local feature branch. Preserve
other worktrees, user settings, historical/unmerged refs and remote branches.
No remote publication is authorized for this phase.

## Personal Vault phase 2 engine, 9 October 2026

The user authorized roadmap phase 2, requested necessary checks only and deferred
real SSD, minimum-host and independent security qualification. Verified phase 1
`abcd943` was fast-forwarded into local main and preserved at
`archive/2026-10-09/vault-phase1`; its merged feature branch was removed. Phase 2
starts on `codex/vault-phase2` from that local main. No remote branch is published.

The bounded engine adds authenticated catalogs/large objects, password/recovery
controls, atomic multi-record visibility, quota/free-space admission, verified
encrypted backup/restore, OS process ownership and reference-aware retention.
Application/UI/credential wiring remains for phase 3. See
[the format contract](vault-phase2-contract.md) and
[focused evidence and deferred gates](vault-phase2-verification.md).

Final focused native verification passed **71 cases in 18.56 seconds**, with no
failures/errors/skips. Compilation, import isolation, preservation hashes and
whitespace checks passed. The full suite and the explicitly deferred external
qualification gates were not run.

Preservation hashes and ref/worktree maps are under ignored
`state/backups/vault-phase2-20261009/`. After focused verification, preserve prior
main at `archive/2026-10-09/main-before-vault-phase2`, commit the bounded engine,
fast-forward local main and remove only its merged local feature branch. Preserve
other worktrees/historical tips and remote refs; do not run the full suite or infer
remote-push authorization from historical workflow records.

## Personal Vault phase 1 review branch, 9 October 2026

The user requested phase 1 of the external Personal Vault v1 roadmap on a new
branch, `codex/vault-phase1`, from local main `aeb350d`. This bounded change adds
the storage inventory, proposed format/lifecycle contract and an isolated
synthetic encryption experiment. No application storage migration or runtime
integration is enabled. See [scope, verification and pending gates](vault-phase1-verification.md).

The user explicitly requested necessary tests only. Final focused checks passed
36 tests in 3.80 seconds; large synthetic-image experiments, compilation, startup
import isolation, preservation hashes and whitespace checks passed. The full
suite and live model/API gates were not run. Physical SSD, minimum-host and
independent security qualification remain pending. Preservation hashes and
ref/worktree maps are under ignored `state/backups/vault-phase1-20261009/`.

Commit the bounded change and retain the requested branch for review. Immediate
fast-forward integration/branch deletion are deferred; local main, remote refs,
other active worktrees and user settings remain unchanged.

## Tool approval and UI integration, 9 October 2026

The user authorized merging and publishing the eight commits from `585cfdb`
through `26085ff` on `codex/tool-approval-preferences`. They add persistent tool
approval preferences, flat settings controls, the native Windows attachment
picker, a burgundy image-generation animation without the active status overlay,
and the enlarged image viewer's editable `Edit this image: ` composer prefix.

The final focused integration check passed **107 tests** without failures or
skips in 39.68 seconds. Its repository-local temporary state, cache and result
are under ignored `state/integrate-approval-ui-focus`,
`state/integrate-approval-ui-cache` and `state/integrate-approval-ui-focused.xml`.
Whitespace checks passed. The full suite was deliberately not run at the user's
request, and no live model/API calls were made for this integration.

Previous main `d850fd7` is preserved at the local annotated tag
`archive/2026-10-09/main-before-tool-approval-ui`. Integration fast-forwards local
main, removes only the merged feature branch and pushes main without force.
Other worktrees, historical/unmerged refs and user runtime settings are preserved.

## Reversal checks and stored goal evidence, 9 October 2026

`codex/reversal-check-goal-evidence` starts from published, verified main `dd87567`. It adds pre-execution checks for known revision returns and stores each agent turn's literal request with receipt-bound save/source evidence. Successful reports and provider partial text retain their existing content. Requested runtime/GUI behaviour remains unverified; no new execution capability, model profile, routing or sampling policy is introduced. See [the contract and qualification](reversal-goals.md).

Final focused native checks passed 74 tests. Final full native checks passed 2734 checks including 15 subtests, with 58 optional/host skips, zero failures or errors, in 412.573 seconds. Four unchanged live coding gates and two controlled live reassessment gates passed. Runtime/GUI execution through ORSI and live local-model checks remain unrun. Pre-change refs/worktrees, a verified history bundle, preservation hashes and separate qualification reports are retained in ignored `state/backups/reversal-goals-20261009/`. Settings, runtime preferences, all fourteen installed Python skill files, twelve other installed skill files, historical refs and four other worktrees remain preserved. Preserve prior main at `archive/2026-10-09/main-before-reversal-goal-evidence`, commit the verified bounded change, fast-forward local main, remove only its merged feature branch, push main without force, and verify GitHub matches the clean checkout.

## Accepted baseline consolidation, 9 October 2026

The six routing/editing phases are integrated on verified local main `15cdb3d`.
The remaining bounded `codex/settings-status-overflow` change enables wrapping
of the full agent status in General settings, preserving reachable controls at
normal and compact window sizes. Its original settings work is retained exactly;
no routing, prompts, tool behavior, model profiles, recovery rules or runtime
preferences change during consolidation.

Pre-change refs/worktree maps, a verified complete-history bundle, the uncommitted
settings patch and content-free configuration/runtime-preference hashes are
retained in ignored `state/backups/main-consolidation-20261009/`. Refreshed GitHub
main is an ancestor of local main; 23 accepted commits await publication before
this final settings commit. The authorized credential is excluded from all
unpublished history blobs and the pending settings files. Focused native settings
checks passed 23 tests. The first full run stalled in the existing attachment UI
group and was stopped; its incomplete result is retained separately. All 33
attachment UI checks then passed unchanged in isolation. The existing root test
cache write warning is separate from product results; subsequent checks use fresh
repository-local caches. Final full native regression passed 2,693 tests and 15
subtests, with 58 optional/host skips, no failures/errors, in 507.304 seconds using
an unrestricted Windows shell and fresh repository-local test/cache directories.
No acceptance prompts or existing assertions change.
The four Phase 6 live coding gates remain passed historical evidence; this
settings-only consolidation does not rerun live model or image gates.

Preserve the three merged 8 October archive branches as annotated archive tags
before removing those redundant local branch names. Keep the separate
`archive/conversational-main-20260921` checkout and the other worktrees unchanged.
After verification, fast-forward local main, switch the clean active checkout to
main, remove only its merged settings feature branch and push main without force.
Verify GitHub main matches the accepted local commit. New reversal-check and
stored-goal work then starts on `codex/reversal-check-goal-evidence` from that
published baseline. The accepted baseline and future feature work remain separate.

## Content-free diagnostics, 9 October 2026

`codex/content-free-diagnostics` starts from verified main `1186871`. Phase 6
adds fixed-category route decisions, settled terminal counts and public
stream/event/code/SDK-version diagnostics. ORSI's owned log file excludes raw
OpenAI/HTTP library records. Parser acceptance, retry ownership, durable settled
work and unknown-outcome safeguards are unchanged. Prompts, routing, tool
contracts/permissions, model/context policies and Python Coder 1.0.1 remain
unchanged. See [the diagnostic contract and qualification](content-free-diagnostics.md).

Pre-change refs/worktree maps, a verified complete-history bundle and content-free
settings/configuration hashes are retained under ignored
`state/backups/content-free-diagnostics-20261009/`. Final focused native checks
passed 223 tests without skips, failures or errors. Final full native checks passed
2,691 tests and 15 subtests, with 58 optional/host skips, no failures/errors, in
484.479 seconds. All four unchanged cloud coding cases passed, with exact bytes,
finite approved mutations, originals preserved for copies, zero failed calls,
corrections or coding images, honest unrun checks and released transports. Four
route and four terminal records contain only approved metadata and match durable
outcomes. The fourteen installed Python skill package files and twelve other
installed skill files are unchanged. Python/GUI execution through ORSI, live image
and local-model gates remain unrun in this phase. Preserve prior main at
`archive/2026-10-09/main-before-content-free-diagnostics`, commit after verification,
fast-forward local main and the active checkout without changing its settings
branch, and remove only the merged feature branch. User settings, installed
skills, other worktrees, historical tips and remote refs remain preserved. The
original unknown stream event cannot be reconstructed from the old logs.

## Python Coder host guidance, 9 October 2026

`codex/python-coder-host-guidance` starts from verified main `9c5a061`. Phase 5 changes
only the Python skill's verification guidance and version (1.0.0 to 1.0.1). It states
ORSI's actual file-tool boundary, truthful unrun checks and bounded follow-up work.
Core prompts, routing, native capabilities/permissions, model/context policies,
progressive references and skill persistence are unchanged. See
[the qualification and preservation record](python-coder-host-guidance.md).

The entire installed prior package and identity, settings/configuration hashes,
refs/worktree maps and verified Git bundle are retained under ignored
`state/backups/python-coder-host-guidance-20261009/`. Focused native checks passed
262 tests with no skips/failures/errors. All four unchanged cloud cases passed before
and after the update with exact saved bytes, finite approved mutations, honest unrun
checks and released transports. Picker/message/session scopes were tested separately.
Final full native checks passed 2,672 tests and 15 subtests, with 58 optional/host
skips, no failures/errors, in 378.60 seconds. The installed updated package matches
the qualified source byte-for-byte; all twelve references round-trip and all twelve
other installed skill files are unchanged. Python/GUI execution through ORSI and real
local-model gates remain unrun. Preserve prior main at
`archive/2026-10-09/main-before-python-coder-host-guidance`, commit after verification,
fast-forward local main and the active checkout without changing its settings branch,
and remove only the merged feature branch. Preserve other installed skills,
worktrees, historical tips, remote refs and user settings edits. Phase 6 remains separate.

## Bounded edit recovery, 9 October 2026

`codex/bounded-edit-recovery` starts separately from verified main `3650e22`.
Its runtime-only recovery groups rejected edits by target, requires newly returned
source before a retry, detects verified revision cycles, and supplies detailed
stopped-work reports through the existing UI path. The core prompts, native tool
contracts, permissions, model/context policies and 128-step/four-correction budgets
are unchanged. Existing identical-read guards and valid read-after-edit work remain.
See [the recovery contract and qualification](bounded-edit-recovery.md).

Pre-fix native reproduction recorded 16 expected failures/three passes. Initial
focused checks passed 160 tests with one host symbolic-link skip; the first full
suite passed 2,663 tests and 15 subtests with 58 optional/host skips. A reproduced
same-batch recovery gap and missing failed-target label were subsequently fixed.
Final focused delivery checks passed 101 tests with one host symbolic-link skip.
All six cloud recovery cases passed on the final code; missing/stale patches recovered
through a complete read and one approved edit, while no-op cases inspected existing
text without a mutation. All four unchanged two-file fix/copy cloud cases passed;
every final report was preserved. Final full native regression passed **2,666 tests
and 15 subtests**, with **58 optional/host skips**, no failures/errors, in **382.18
seconds**. An earlier existing installer cleanup failure and related teardown error
remain recorded separately; its complete 60-test group and final full suite passed
unchanged on recheck. Skipped live gates remain separate. ORSI did not execute
Python or a GUI.

Refs/worktree maps, a verified complete-history bundle and content-free preservation
hashes are saved under ignored `state/backups/bounded-edit-recovery-20261009/`.
Preserve prior main at `archive/2026-10-09/main-before-bounded-edit-recovery`, commit
after verification, fast-forward local main and the requested active checkout
without changing its settings branch, and remove only the merged feature branch.
Settings edits, other worktrees, historical tips and remote refs stay intact.
Phases 5–6 remain separate.

## Scoped coding guidance, 9 October 2026

The separately bounded `codex/scoped-coding-guidance` change resumes on verified
main `32dc9a9` after the independent file-task reporting prerequisite. Its original
guidance tip `9e0b902` is retained at `archive/2026-10-09/guidance-before-report-fix`;
rebasing preserved its implementation and acceptance prompts. The only product
change is prompt guidance for finite requested changes, grounded edits, explicit
copies and honest verification. See [its contract and qualification](scoped-coding-guidance.md).

Final focused native checks passed 158 tests, with one host symbolic-link skip.
All four frozen default-cloud two-file fix/copy cases passed with and without the
unchanged Python skill: two approved edits per existing-file task, four mutations
per copy task, exact saved bytes, originals preserved for copies, and honest reports
retained. No coding images, failed tool calls or semantic corrections occurred;
all transports were released. ORSI did not execute Python or a GUI. Final full
native regression passed 2,638 tests and 15 subtests, with 58 optional/host skips,
no failures/errors, in 341.98 seconds. Opt-in live gates remain separate.

Pre-integration refs/worktree maps, a verified complete-history bundle and content-free
preservation hashes are saved in ignored `state/backups/scoped-coding-guidance-final-20261009/`.
Preserve prior main at `archive/2026-10-09/main-before-scoped-coding-guidance`, commit
after verification, fast-forward main and the requested active checkout without
switching its settings branch, and remove only the merged guidance branch. User
settings edits, other worktrees, remote refs and the archived earlier tip remain
intact. Phases 4–6 remain separate.

## File-task reports prerequisite, 9 October 2026

`codex/preserve-file-task-reports` starts independently from main `8462cdb` after
Phase 3 cloud qualification exposed a pre-existing answer-rendering bug. Supporting
source reads were replacing otherwise correct completion/verification reports with
the last file's contents. The prompt-guidance work remains preserved separately on
its unmerged branch and at `archive/2026-10-09/guidance-before-report-fix`.
See [the contract and qualification](file-task-reports.md).

Final focused native checks passed 89 tests and five subtests. The frozen pre-fix
reproduction has 13 expected failures/four passes, including actual result persistence.
Final full native regression passed 2,613 tests and 15 subtests, with 58 optional/host
skips, no failures/errors, in 350.04 seconds. A prior existing Git-installer cleanup
failure and related teardown error remain recorded separately; its complete 60-test
group and final full suite passed unchanged on recheck.
The unchanged cloud fix/copy gate passed all four cases using the original main prompts;
all four published answers retained their model reports. Python/GUI execution remains
outside ORSI's available tools. Prompt/routing/tool/model/context policies are unchanged.

Pre-integration refs/worktrees, a verified complete-history bundle and content-free
preservation hashes are saved in ignored `state/backups/file-task-reports-20261009/`.
Preserve prior main at `archive/2026-10-09/main-before-file-task-reports`, commit after
verification, fast-forward local main and the requested active checkout without changing
its settings branch, and remove only the merged reporting branch. Other worktrees,
remote refs, settings edits and the unmerged guidance tip remain intact. Resume Phase 3
after this separate verification checkpoint.

## Sufficient source reads, 9 October 2026

The bounded `codex/sufficient-source-reads` change starts from verified local main
`60735e1` in the clean isolated checkout under `state/routing-intent-worktree/`,
preserving the active settings-panel edits. Phase 2 adds explicit source completeness,
larger-read recovery instructions within existing bounds, and actionable source/context
limitations. UTF handling, digests, path/approval/identity checks, prompts, profiles,
sampling and loop budgets retain their existing behavior. See
[the contract and verification record](sufficient-source-reads.md).

Focused native checks passed 178 tests with two host symbolic-link skips. All four
real-cloud below-line-200 fixes passed with/without the installed Python skill;
the separately corrected oversized-file verifier passed with no mutation. Python/GUI
execution and real local-model qualification remain separate from these checks.
The unchanged Phase 1 cloud fix/copy gate passed all four cases. Final full native
regression passed **2,591 tests and 15 subtests**, with **58 optional/host skips**,
no failures/errors, in **351.16 seconds**. Compilation, dependencies and whitespace
checks passed; skipped live gates remain separately recorded.

Pre-integration refs/worktree maps, a verified complete-history bundle and content-free
settings/configuration hashes are preserved in ignored
`state/backups/sufficient-source-reads-20261009/` in the isolated checkout. Preserve prior
main at `archive/2026-10-09/main-before-sufficient-source-reads`, commit after verification,
fast-forward local main and the requested active checkout without switching its settings
branch, and remove only the merged feature branch. Other worktrees and remote refs remain
unchanged. Phases 3–6 remain separate.

## Routing intent repair, 9 October 2026

The bounded `codex/routing-intent-fix` change starts from verified local main
`7b73fe3` in an isolated checkout under `state/routing-intent-worktree/`, preserving
the active settings-panel work. Phase 1 shares route/source decisions between
preview and execution, keeps coding diagnostics and screenshots on the agent
path, and limits implicit image reuse to the current visual task. Intentional
image output and explicit skill scopes retain their supported behavior.
See [the verification and delivery record](routing-intent-fix.md).

Final focused native checks passed 272 tests, and all 120 installer/launcher
checks passed with short repository-local fixtures. All four synthetic real-cloud
fix/copy cases passed with and without the installed Python skill, and the
existing live image generation/reopen/edit gate passed. Final full regression
passed 2,564 tests and 15 subtests, with 58 optional skips and no failures/errors
in 332.38 seconds. Execution of Python and GUI behavior remain outside ORSI's available
verification tools. Other opt-in live gates are separate from passed checks.

Pre-integration refs/worktree maps and a verified complete-history bundle
containing 113 refs are preserved under ignored
`state/backups/routing-intent-fix-20261009/` in the isolated checkout. Preserve
prior main at `archive/2026-10-09/main-before-routing-intent-fix`, commit after
verification and fast-forward local main. Fast-forward the requested active
checkout without switching its settings branch or discarding its uncommitted
changes. Remove only the merged local routing branch; other worktrees and
remote refs remain unchanged. Phases 2–6 of the routing/editing plan remain separate.

## Compact notification settings, 8 October 2026

The bounded `codex/compact-notification-settings` change starts from local main
`ab04871`. General settings now places a compact sound picker/preview group and
an animated sliding notification switch at the right of their rows. The switch
matches the supplied dark-track/light-thumb reference and supports mouse, Space
and keyboard focus. Normal/minimum renders were inspected at 100% and 200% scale.
Existing sound choices, preference persistence and notification delivery remain
in place. See [the updated layout record](notification-bugfixes.md).

Focused checks passed 31 tests at 200% scaling using the suite's expected Qt
offscreen platform. An initial forced Windows-platform run passed 30 tests but
one pre-existing native-notification mock failed when its partial WinDLL stub
reached the real window-frame constructor; product code was not changed for it.
Full unrestricted Windows regression passed 2,437 tests and 15 subtests, with
58 optional skips and no failures/errors, in 376.20 seconds. Compilation and
whitespace checks passed. Live model/provider gates were not run for this
presentation-only revision. Isolated renders and test reports are retained in
`state/compact-notifications-preview/` and `state/compact-notifications-*.xml`.

Preserve prior main at `archive/2026-10-08/main-before-compact-notification-settings`,
commit the verified change, fast-forward local main and remove only the merged
feature branch. Other worktrees and remote refs remain outside the operation.

## Notification corrections, 8 October 2026

The bounded `codex/notification-bugfixes` change starts from local main `696162a`.
Automatic alerts are quiet while ORSI is active. Buffered audio preserves the
entire sound with device-start padding, and General settings places the enable,
sound and preview controls in full-width rows beneath their labels. Existing
user preferences, original OGG files and tool/inference behavior are preserved.
See [behavior and verification](notification-bugfixes.md).

Focused unrestricted checks passed 64 tests, with a final 31-test notification/
audio/settings recheck after the scalable preview icon change. Native playback
of both OGG files, foreground silence and resource cleanup passed. Normal and
minimum settings renders were inspected at 100% and 200% scaling. Final full
unrestricted regression passed 2,437 tests and 15 subtests, with 58 separately
recorded optional skips, no failures/errors, in 400.28 seconds. The first full
run and installer recheck's unchanged temporary-folder cleanup failures remain
recorded separately; its process-ownership cases and fresh full suite passed.
No live model/provider gate was run.

Preserve prior main at `archive/2026-10-08/main-before-notification-bugfixes`,
commit after verification, fast-forward local main and remove only the merged
feature branch. Other worktrees and remote refs remain outside the operation.
Restart ORSI to load the fixes.

## Desktop notifications, 8 October 2026

The bounded `codex/desktop-notifications` change starts from local main `d6c2d6b`.
ORSI alerts for completed responses, actionable tool approvals, completed images
and task errors. General settings includes an enable control and sound selection,
using the supplied `noti_1.ogg` by default, with `noti_2.ogg`, Silent and custom
local audio options. See [behavior and verification](desktop-notifications.md).

Focused unrestricted checks passed 51 tests. Both bundled OGG files played to
completion without audio errors; native shell delivery, minimized-window restore
and resource cleanup passed. Normal and compact settings renders were inspected.
Final full unrestricted Windows regression passed 2,424 tests and 15 subtests,
with 58 separately recorded skips, no failures/errors, in 391.68 seconds.
An initial unchanged installer cleanup failure passed all 60 installer checks
independently and the fresh full suite. No live model/provider gate was run.

Preserve prior main at `archive/2026-10-08/main-before-desktop-notifications`,
commit after verification, fast-forward local main and remove only the merged
feature branch. Other worktrees, remote refs, existing user preferences, model
profiles and inference policy remain outside the operation. Restart ORSI to load
the notification controls and event handling.

## Greeting reference appearance, 8 October 2026

The bounded `codex/greeting-reference-style` GUI change starts from local main
`7993af0`. Greeting shares the exact flat input style used by the Skills source
field in the user's reference, including its border, corner radius, spacing,
font and height. The original input and saving handlers remain in place. See
[the appearance and verification record](greeting-reference-style.md).

Normal and compact renders were pixel-identical to the reference control at
equal size and text. Native focused checks passed 60 tests and 13 subtests.
An initial full-suite installer file I/O failure passed all 26 installer checks
on an independent rerun. No installer or acceptance-prompt changes were made.
Final full native regression passed 2,414 tests and 15 subtests in 404.64 seconds,
with 58 separately recorded optional/host skips and no failures or errors.
No live API gate was run.

Preserve prior main at `archive/2026-10-08/main-before-greeting-reference-style`,
commit after full verification, fast-forward local main and remove only the
merged feature branch. Other worktrees and remote refs remain outside the
operation. Restart the normal launcher to load the reference appearance.

## Greeting composer appearance, 8 October 2026

The bounded `codex/greeting-composer-style` GUI change starts from local main
`db8f80c`. Greeting now uses the shared antialiased composer pill and gradient,
with matching text styling and comfortable padding. The existing input object
and saving handlers remain in place. See
[the appearance and verification record](greeting-composer-style.md).

Native focused settings/frame/personality/composer checks passed 49 tests and
eight subtests in 18.37 seconds. Final full native regression passed 2,414 tests
and 15 subtests in 442.24 seconds, with 58 separately recorded optional/host
skips and no failures/errors. A stalled initial image-viewer check passed both
its isolated rerun and the fresh full suite. Normal, compact and placeholder
renders were inspected using isolated preferences. No live API gate was run.

Preserve prior main at `archive/2026-10-08/main-before-greeting-composer-style`,
commit after verification, fast-forward local main and remove only this merged
feature branch. Other worktrees and remote refs remain outside the operation.
Restart the normal launcher to load the restyle.

## Cloud runtime work budget, 8 October 2026

The bounded `codex/cloud-runtime-budget` fix starts from local main `0ff7bff`.
Cloud turns receive 128 steps, 128 model requests and 256 calls, with matching
durable history capacity and a paused-task progress summary at a work-budget
stop. Existing metadata batches may contain seven calls, each independently
authorized and journaled. Local budgets, model profiles, sampling, routing,
context policy and mutation approvals remain in place. See
[the behavior and verification record](cloud-runtime-budget.md).

Final native focused regression passed 246 tests in 87.76 seconds. Full native
regression passed 2,414 tests and 15 subtests in 422.06 seconds, with 58 separately
recorded optional/host-dependent skips and no failures/errors. An initial
temporary Git-folder cleanup failure passed both the focused and full reruns;
installer code was not changed. No live provider gate was run.

A verified complete-history bundle containing 104 refs and ref/worktree maps
is preserved under ignored `state/backups/cloud-runtime-budget-20261008/`.
Preserve prior main at `archive/2026-10-08/main-before-cloud-runtime-budget`,
commit after verification, fast-forward local main and remove only this merged
feature branch. Other worktrees, remote refs and live runtime selection remain
outside the operation. Restart the normal main launcher to load the new budget.

## Greeting input visibility, 8 October 2026

The bounded `codex/greeting-input-visibility` GUI fix starts from local main
`d1dfcb7`. Greeting uses a prominent full-width field beneath its label in
General, preserving the existing saving behavior. Native focused checks passed
45 tests and five subtests, including actual clicks, keyboard editing and
preference restoration at normal/minimum window sizes. See
[the verification record](greeting-input-visibility.md).

Full native regression passed 2,399 tests and 15 subtests in 371.53 seconds,
with 58 separately recorded optional/host-dependent skips and no failures/errors.
Preserve prior main at
`archive/2026-10-08/main-before-greeting-input-visibility`, commit after
verification, fast-forward local main and remove only the merged feature branch.
Other worktrees and remote refs remain outside the operation.

## Embedded settings tabs, 8 October 2026

The bounded `codex/settings-embedded-tabs` GUI change starts from local main
`009510e`. A larger antialiased panel groups everyday preferences, models,
embedded Skills and Image Generation controls, and appearance. Future options
are disabled placeholders. Existing service handlers and user runtime stores
remain in place; see [the layout and verification record](settings-embedded-tabs.md).

Final native GUI/skills/frame checks passed 60 tests and 15 subtests. Full native
regression passed 2,398 tests and 15 subtests in 334.09 seconds, with 58 separately
recorded optional/host-dependent skips and no failures/errors. Synthetic normal,
compact and 2× display renders were inspected. No live model/API gate was run.
Preserve prior main at `archive/2026-10-08/main-before-settings-embedded-tabs`,
commit the verified change, fast-forward local main and remove only the merged
feature branch. Other worktrees and remote refs remain outside the operation.

## Visual-output routing, 8 October 2026

The bounded `codex/visual-output-routing` repair starts from local main `993e5dd`.
It recognizes reference sheets and other visual outputs within the creation
clause, removes the fixed adjective-length cutoff, preserves written/analysis
tasks, and resolves original images for referential creation and view changes.
The fresh-start policy and backend/model settings remain unchanged.

Final native focused checks passed 113 tests. Full native regression passed
2,388 tests and 15 subtests, with 58 separately recorded skips, in 278.33 seconds.
Stable composer reproduction, original-byte checks and qualification limits are in
[the verification record](visual-output-routing.md). No live API gate was run.
A verified complete-history bundle containing 97 refs and worktree identities
is retained under ignored `state/backups/visual-output-routing-20261008/`.
Preserve prior main at `archive/2026-10-08/main-before-visual-output-routing`,
commit after verification, fast-forward local main and remove only the merged
feature branch. Other worktrees, remote refs and live runtime state remain
untouched.

## Photograph routing and fresh startup, 8 October 2026

The bounded `codex/image-routing-fresh-start` repair starts from local main
`e5c9c89`. Photograph requests, including the screenshot's `Genereate` spelling,
reach native image generation. Startup starts an empty active session and
archives the prior conversation/image references through the existing safe
archive path, replacing the earlier generated-image resume exception.

Native focused confirmation passed 136 tests and five subtests. Full native
regression passed 2,348 tests and 15 subtests, with 58 separately recorded skips,
in 276.67 seconds. Exact-prompt SDK reproduction and archival checks are in
[the verification record](image-routing-fresh-start.md). No live model/API gate
was run. A verified complete-history bundle containing 96 refs and worktree
identities is retained under ignored `state/backups/image-routing-fresh-start-20261008/`.
Preserve prior main at `archive/2026-10-08/main-before-image-routing-fresh-start`,
commit after verification, fast-forward local main and remove only the merged
feature branch. Other active worktrees, remote refs and runtime settings remain
untouched.

## Image preview motion, 8 October 2026

The bounded `codex/image-preview-motion` change starts from local main `a982423`.
The image generation placeholder gains wider/faster drifting red and dark navy
clouds, a padded status row, a pulsing dot and a text reflection. Request behavior,
result transfer and original-image bytes are unchanged.

Native focused checks passed 36 tests. Full native regression passed 2,339 tests
and 15 subtests, with 58 separately recorded skips, in 325.30 seconds. Synthetic
rendering and verification evidence are in [the verification record](image-preview-motion.md). No live
model/API gate was run. Historical refs and worktree identities are retained
in a verified complete-history bundle under ignored
`state/backups/image-preview-motion-20261008/`. Preserve prior main at
`archive/2026-10-08/main-before-image-preview-motion`, commit after verification,
fast-forward local main and remove only the merged feature branch. Other active
worktrees, remote refs and runtime settings remain untouched.

## Composer motion polish, 8 October 2026

The bounded `codex/composer-motion-polish` change starts from local main
`fe0909f`. Image drafts display thumbnails, the plus control pulses, wheel
scrolling eases, and the image viewer and asynchronous Qt attachment picker
fade open. Local-image lag/composer collapse was investigated only; admission,
inference and composer-height behavior remain unchanged.

Final native focused checks passed 160 tests and five subtests. Final full native
regression passed 2,339 tests and 15 subtests, with 58 separately recorded skips
in 331.03 seconds. Evidence, the earlier installer I/O failure/retry, synthetic visual
checks and investigation limits are in [the verification record](composer-motion-polish.md).
No live model/API gate was run.

Refs/worktree identities and a verified complete-history bundle containing
92 refs are retained under ignored `state/backups/composer-motion-20261008/`.
Preserve prior main at `archive/2026-10-08/main-before-composer-motion-polish`,
commit after verification, fast-forward local main and remove the merged local
feature branch. Other active worktrees, remote refs and runtime settings remain
untouched.

## Skill reference count, 8 October 2026

The bounded `codex/skill-reference-count-32` change starts from local main
`69d5856`. The shared package ceiling rises from 16 to 32 Markdown references,
with byte limits, excerpts, cloud pacing, profiles and inference policies intact.
The desktop `2d-game-dev` skill is installed into the global catalog; all 20
references passed native reading and exact-byte verification, with the four
existing skills and source bytes preserved.

Unrestricted focused checks passed 338 tests; full native regression passed
2,334 tests and 15 subtests, with 58 optional skips and no failures/errors in
356.44 seconds. The restricted-run failures remain separate sandbox evidence.
No live model/API gate was run. See [the verification record](skill-reference-count-32.md).

Refs/worktree identities and a verified complete-history bundle containing
91 refs are retained under ignored `state/backups/skill-reference-count-32-20261008/`.
Preserve prior main at `archive/2026-10-08/main-before-skill-reference-count-32`,
commit the verified change, fast-forward local main and remove the merged local
feature branch. Other active worktrees and remote refs remain untouched.

## Native image generation integration, 7–8 October 2026

Eight bounded `codex/image-generation-*` subphases start from local main
`553e333`. Each was verified, committed, fast-forwarded into main and pushed
under the user's explicit eight-subphase authorization; its merged local feature
branch was removed. The port includes independent image settings, native cloud
generation, original-resolution storage, follow-up editing, a cached animated
placeholder, viewer/save presentation and cancellation/failure handling.
Application startup resumes conversations containing generated images so their
saved originals remain visible and editable.

The final full suite passed 2,332 tests and 15 subtests, with 58 separately
recorded opt-in/host-dependent skips. Actual generation, reopening, editing and
transport release passed twice. Earlier access probes and native test failures
remain recorded separately in [the image-generation record](image-generation.md).
The final acceptance repair reuses immutable Windows DLL bindings shared by
protected image reads; file identities, handles and permission checks stay fresh.

All pre-port refs were preserved in the verified complete bundle under
`state/backups/image-generation-20261007/`. Each prior integration tip is retained
at `archive/2026-10-07/main-before-image-generation-<subphase>`. Other worktrees
and their active branches remain untouched. Runtime image choices belong under
ignored state; credentials and live image data were not committed.

## Image viewer overlay integration, 7 October 2026

The bounded `codex/image-viewer-overlay` change starts from local main `9031aa6`.
The viewer fills the available screen, shows a larger source-backed image over
a blurred/dimmed capture of the chat, and uses the same composer paint, controls,
typography and stylesheet as the main chat. Preview decoding now retains portrait
detail up to a 4096 × 4096 bound. Local/cloud follow-up sends keep their existing
source-reference and draft-preservation path. Inference and model profiles are
unchanged.

The focused viewer/composer/chat/native-window group passed 96 tests and 15
subtests. Two earlier combined UI runs aborted in a native Qt copy-feedback wait;
the viewer test fixture now holds its QApplication for the whole session and
cleans up its temporary parent explicitly. The final full regression passed
2,292 tests and 15 subtests, with 58 optional gates skipped, in 357.51 seconds.
Synthetic renders were inspected at 1920 × 1080. Live model/API gates were not
rerun for this presentation change; see [the viewer record](image-viewer.md).

Before integration, refs and worktree identities were preserved in the verified
complete bundle under `state/backups/image-viewer-overlay-20261007/`. Previous
main is retained at `archive/2026-10-07/main-before-image-viewer-overlay`. The
user's standing merge-and-push instruction authorizes integration and publication.
Other worktrees and historical tips remain untouched.

## Image-only input integration, 7 October 2026

The bounded `codex/image-only-grounding` change starts from verified local main
`8ae0aa0`. Shared local/cloud attachment guidance explains that supplied visual
input is available independently of filesystem access and defines the behavior
for image-only messages. Saved text and source bytes remain unchanged; no skill,
tool, routing, sampling or profile changes accompany this prompt repair.

The original image passed three repaired GPU full-pipeline checks; fresh runs
before the repair also passed, so the original refusal was not reliably
reproduced. The new synthetic image-only GPU gate passed, including a follow-up
that retained the user's explicit task. All 145 focused regressions passed.
The full suite recorded 2,289 passed, one unchanged native state-replacement
retry assertion failure, 58 skipped and 15 subtests in 369.89 seconds. The first
117-test isolated native recheck passed the original failing test but hit a
different unchanged skill-reader directory-rename denial (116 passed, one
failed); the fresh combined recheck passed all 117 tests in 1.87 seconds.
These failures remain recorded and do not constitute a passing full suite.

Before integration, refs and worktrees were saved with a verified complete
bundle under `state/backups/image-only-grounding-20261007/`. The prior main is
retained at `archive/2026-10-07/main-before-image-only-grounding`. The user's
standing merge-and-push instruction authorizes promotion and publication of
this bounded change. Other worktrees and historical tips remain untouched.
See [image-only input](image-only-input.md) for evidence and limitations.

`C:\Users\yaboy\Desktop\orsi_test` is the active linked checkout. Its shared Git directory is
under `C:\Users\yaboy\Desktop\o.r.s.i\.git`; the original checkout remains on
`archive/conversational-main-20260921`. That archive checkout is not the current application.

`main` holds the latest locally verified integration. Use one short-lived `codex/<change>` branch
for a bounded change. After its required checks pass, commit it, fast-forward local `main`, return
the active checkout to `main`, and remove the merged branch. Avoid stacks of finished phase branches.
Remote publication is a separate operation; local integration does not imply that GitHub was updated.

On 1 October 2026, 31 historical local branch tips were preserved as lightweight tags under
`archive/2026-10-01/<original-branch-name>`, then removed from the local branch list. Tags preserve
both merged and unmerged history. The other checkout's active archive branch was retained. Local
`main` was fast-forwarded to the existing chooser source at `b2f4e3e`, without rewriting history.
This is the source starting point for baseline repair, not a claim that the audit defects were fixed.

Before cleanup, all refs were saved in the verified bundle
`state/backups/branch-hygiene-20261001/all-refs-before.bundle`. The same directory contains the
original branch map, working-tree status, and the user's exact pre-migration model configuration.
This backup is machine-local and ignored by Git. Historical tips are also recoverable through the
archive tags even without the bundle. To resume a historical tip, create a new `codex/` branch at
its tag; do not move `main` backwards or reset an active checkout to recover old work.

Source configuration defines accepted/qualified profile targets. Ignored runtime state records
which model is selected. A clean Git status must not be confused with a matching runtime baseline:
use the diagnostic snapshot for revision, effective flags, model identity and effective limits.

## User-approved UI integration, 2 October 2026

The user approved the response formatting, borderless window and fixed transparent top controls
at UI revision `0253456`, then explicitly requested integration into main and GitHub branch cleanup.
This integration includes that working UI and this record. It is user-approved promotion, not a
claim that skipped per-model live qualification gates passed. The latest UI/native-window checks
passed 45 tests and 15 subtests; the full follow-up suite recorded 833 passed, 1 intermittent Windows
history-save failure and 54 skipped, with the failing test group passing its 15-test isolated recheck.
See [window verification](frameless-window-2026-10-02.md).

Before cleanup, all Git refs were saved and verified in the ignored backup bundle
`state/backups/branch-hygiene-20261002-ui/all-refs-before.bundle`, with ref and worktree maps alongside
it. The previous main is preserved at `archive/2026-10-02/main-before-response-ui`.
Unmerged qualification work is preserved at `archive/2026-10-02/codex/live-qualification-gate`
(`a9fb566`); the older remote integration tip is preserved at
`archive/2026-10-02/remote/codex/phase-integration-test` (`ecd70d6`). These archive tags are published
before the obsolete branches are removed. Neither unmerged tip is incorporated into main.

Eight other remote phase/UI branches are ancestors of the approved working state and can be
removed after publishing main. The original archive checkout remains on its existing branch.

## User-approved tool catalog and inline styling integration, 3 October 2026

The user explicitly requested merging and pushing the current branch after reviewing the
stable tool catalog and rounded grey inline references. The integrated source revisions are
`ca82326` (tool availability), `ee2ba69` (inline styling) and `d601dc5` (native Windows font
detection and rounded backgrounds). The previous main is `1daa20a`. This integration does
not incorporate the archived qualification-gate branch or change model profiles and limits.

At `ca82326`, the repeated live matrix passed 10/10 workflows for 14B, 6/10 for 3B and 6/10
for VL 4B: 22/30 overall, so qualification remained false. The same 14B confirmation/restart
workflow passed 2/2 on the repair versus 0/2 on unchanged main. Measured total tokens increased
from 43,338 to 94,061 across those matched sessions; the larger catalog has a material context
cost. Generated Breakout code was checked for compilation, not gameplay execution. Owned
validation servers exited. Content-free diagnostics are stored locally in the ignored
`state/stable-catalog-summary.json`; raw conversations and runtime settings are not published.

The final styling checks passed 66 focused tests and 5 subtests, including the native Qt Windows
backend. The full suite recorded 844 passed, 3 failed, 54 skipped and 15 subtests passed.
The three failures were Windows access-denied errors during atomic conversation persistence;
all three passed their isolated recheck. These failures and skipped gates remain unresolved
qualification evidence. The user's explicit merge instruction authorizes this integration;
it does not turn these results into a fully qualified baseline.

## User-approved personality integration, 3 October 2026

The user explicitly requested merging and pushing personality revision `8d95e03` after reviewing
its results. The previous main is `28482ae`. The shared voice guidance and its tests are integrated
without changes to model profiles or runtime authorization. See [personality verification](personality.md)
for the full regression and repeated live smoke results, including failures and omitted qualification
gates. User-approved integration does not change those results into full qualification.

## User-approved context-efficiency integration, 3 October 2026

After testing the isolated `TEST b481941` preview, the user explicitly approved
the changes and requested merging into main and pushing. Main is fast-forwarded
from `aa0bf7c` to the tested source `b481941`, including accepted list-marker
revision `0c58c13`. The following documentation commit records that approval;
application source matches the tested candidate.

The full regression passed 923 tests and 15 subtests, with 54 legacy skips. The
required repeated live matrix passed 21/30 cells and remained unqualified.
User-approved integration does not relabel those failures or enable recovery.
Accepted model profiles, limits, sampling and runtime selection are unchanged.
See [context-efficiency measurements](context-efficiency-stages.md).

Before integration, refs were preserved in the verified ignored bundle
`state/backups/context-efficiency-integration-20261003/all-refs-before.bundle`.
Local archive tags preserve `main-before-context-efficiency`,
`accepted-working-before-context-efficiency` and `context-efficiency-tested`
under `archive/2026-10-03/`. Merged local feature branches can be removed after
publication; no unrelated active checkout or remote feature branch is changed.
The detached preview remains available with independent state. Its launcher,
runtime/model links, conversations, settings and validation artifacts are local
only; normal `ORSI.cmd` and `ORSI_TEST.cmd` launch main after integration.

## User-approved skills UI integration, 4 October 2026

After reviewing the message picker and Settings-only installer, the user explicitly
requested merging into main and pushing to GitHub. Local main fast-forwards from
`9afeaf5` to the verified feature history: `78ce269` adds per-message attachments,
`e3467f9` simplifies the picker styling, and `9d41df3` adds Settings management.
The integration record changes documentation only; application source remains
the tested candidate.

The final regression passed 1,479 tests and 15 subtests, with 58 existing skips.
Two isolated Settings audits installed the real frontend-design and handoff
sources without model requests or changes to the user's skills/model profile.
An earlier full-run Git temporary-folder cleanup failure and its passing 60-test
recheck remain recorded in [Settings verification](skill-settings.md). Existing
skipped qualification gates are not relabeled as passes.

At integration, GitHub main `3da153d` was an ancestor of local main, 14 commits
behind it. The normal main push includes those already integrated skill-runtime
commits and the approved UI work. No force push, remote branch deletion or
other worktree modification is authorized or needed.

Before integration, all refs were preserved in the verified ignored bundle
`state/backups/skill-ui-integration-20261004/all-refs-before.bundle`, with ref
and worktree maps alongside it. The merged local `codex/message-skill-picker`
branch is removed after successful publication. Historical tips remain in the
bundle and existing archive refs; other checkouts retain their current branches.

## User-approved OpenAI cloud integration, 4 October 2026

After testing the separate cloud launcher and the Luna output-budget adjustment,
the user explicitly requested merging the cloud update into main and pushing to
GitHub. This supersedes the implementation-period instruction to leave main
unchanged. Main fast-forwards from `b22b904` through tested application source
`45fccb1`; the following integration record changes documentation only.

The integration includes the pinned OpenAI Responses SDK, native strict tools,
durable stateless response/encrypted-reasoning replay, streaming and cancellation,
context/cache measurements, packaging verification, the cloud model selector and
the 16,384-token Luna output reserve. Luna remains the cloud default; normal
startup remains local where available, with automatic fallback disabled. Ignored
runtime selection, conversations, UI preferences, local models and user skills
are preserved rather than replaced by test-fixture state.

The last focused check passed 193 tests. The full suite recorded 1,700 passed,
1 failed, 49 skipped and 15 subtests passed. The Skill Settings worker timeout
also reproduced on a pre-budget-change source snapshot. The real large-write
fixture completed a 9,110-token call; its separate exact-copy assertion failed
because the model omitted the final newline. See the retained
[output-budget verification](cloud-openai-output-budget.md). User approval does
not relabel either failure or skipped gates as a pass.

Both cloud profiles remain unqualified. Phase 4.1 recorded Luna 28/30 and Sol
30 blocked due to API permission; those measurements used the old output budget.
Legacy deletion remains gated on successful qualification. This integration
does not change prompts, permissions or profile qualification flags to bypass
those limits.

GitHub main was `b22b904` before integration. All refs are preserved in the
verified ignored bundle under
`state/backups/cloud-openai-integration-20261004/`, alongside configuration
copies and the normal runtime's distribution-version inventory. The normal
runtime needs `openai==2.54.0`; its dependency plan is checked before installation,
without replacing existing satisfied dependencies or local inference packages.

Only main is published. After successful publication, the merged local
`codex/cloud-openai` branch is removed and its test checkout remains detached at
the integrated tip, preserving its independent state and test launcher. No
remote feature branches or unrelated active checkouts are changed.

## Maximum Luna output allowance, 4 October 2026

After integration, the user requested the highest supported output allowance.
The bounded `codex/cloud-max-output` change starts from local main `a4aba0c`.
Luna receives its documented 128,000-token output allowance, with matching
context reserve, a finite 30-minute deadline and expanded bounded streaming
capacity. The input allowance, Sol profile, user settings and qualification
flags are preserved. See [maximum-output verification](cloud-openai-max-output.md).

Verification passed all 247 focused checks and the full regression: 1,704 tests
and 15 subtests passed, 49 skipped, no failures. Two short live requests accepted
the 128,000-token wire setting; a real isolated Qt selector switch away/back
confirmed effective limits and resource release. This does not claim a live
128,000-token generation or successful qualification of previously blocked gates.

Configuration copies, ref/worktree maps and a verified all-ref recovery bundle
are preserved under ignored `state/backups/cloud-max-output-20261004/`. After
verification the bounded change is committed, local main fast-forwards and the
merged local feature branch is removed. Other active worktrees retain their
original tips. The earlier detached test checkout retains `a4aba0c`; test the
new allowance by restarting the normal main launcher.

## Maximum cloud input budgets, 4 October 2026

The user requested the maximum possible cloud input cap while leaving local
mode unchanged. The bounded `codex/cloud-max-input` branch starts from local
main `35eb8eb`. Both cloud profiles use their full documented 1,050,000-token
context window, with remaining space allocated to input after their unchanged
output reserves: Luna 922,000 and Sol 1,045,904, each including the existing
256-token safety margin. Local configuration and agent policy are unchanged.

Verification passed 270 focused checks and the full Windows regression: 1,709
tests and 15 subtests passed, 49 skipped, no failures. Two synthetic live Luna
requests used more than 45,000 input tokens, exceeding the former cap; the
isolated Qt selector verified cloud switching and effective limits. Owned
resources were released. Maximum-context live qualification and Sol permission
gates remain separate from these checks. See
[maximum-input verification](cloud-openai-max-input.md).

Configuration copies, ref/worktree maps and a verified all-ref recovery bundle
are preserved under ignored `state/backups/cloud-max-input-20261004/`. After
verification the change is committed, local main fast-forwards and its merged
local branch is removed. Other worktrees retain their prior heads, including
the detached older cloud test checkout. Restart the normal main launcher to
load the new budgets.

## Quiet startup and inline approvals, 4 October 2026

The user requested a new branch to remove startup/cloud warnings and replace
approval windows with Enter/Esc review in the input area. The bounded
`codex/inline-tool-approvals` change starts from local main `e5d4831`. Configured
host read access is used at startup without a warning; per-operation write and
launch authorization stays with the existing runtime. No model profile or user
runtime configuration changes are included.

The final focused run passed 268 tests and 5 subtests, with 1 existing skip.
Existing application-launch checks passed 21 tests, and native Windows UI checks
passed 47 tests and 5 subtests. The full unrestricted regression passed 1,719
tests and 15 subtests, with 49 existing skips and no failures. See
[inline approval verification](inline-tool-approvals.md). Skipped live gates
remain separate from deterministic verification.

All pre-integration refs and the worktree map are preserved in the verified
ignored bundle under `state/backups/inline-approvals-20261004/`. The previous
main is also preserved at `archive/2026-10-04/main-before-inline-tool-approvals`.
Following the repository working baseline, verification is followed by a local
commit, fast-forward of main, and removal of the merged local feature branch.
Remote refs and other active checkouts are not changed or published.

## Approval composer animation, 4 October 2026

The user requested smooth composer growth and retraction for approval review.
The bounded `codex/approval-composer-animation` follow-up starts from local main
`c5e0c53` and adds a 240 ms eased height transition with a fixed bottom edge.
Decisions remain immediate, and interrupted animations resume from the current
height. Model and runtime authorization behavior are unchanged.

Verification passed 248 focused tests and 5 subtests, with 1 existing skip;
13 native Windows animation/approval checks; and the full regression of 1,721
tests and 15 subtests, with 49 existing skips and no failures. See
[animation verification](inline-tool-approvals.md#composer-animation-follow-up).

The pre-integration refs and worktree map are preserved in a verified ignored
bundle under `state/backups/approval-animation-20261004/`. The previous main is
preserved at `archive/2026-10-04/main-before-approval-animation`. Following the
working baseline, the verified change is committed, local main fast-forwards,
and the merged feature branch is removed. Other active worktrees and remote
refs are unchanged.

## Skill badge composer layout repair, 4 October 2026

The user requested a separate branch to repair the skill badge overlapping the
composer input. The bounded `codex/skill-chip-composer-layout` fix starts from
local main `5bb7261` and places the badge in the nested message row instead of
the outer approval stack. Selection and approval behavior are unchanged.

Native focused checks passed 69 tests and 5 subtests. The first full run hit the
previously recorded Skill Settings installer worker timeout, with 1,720 passed,
1 failed, 49 skipped, and 15 subtests passed. The isolated Settings/picker
recheck passed 19 tests. The full confirmation passed 1,721 tests and 15
subtests, with 49 existing skips and no failures. The earlier intermittent
failure remains recorded in [picker verification](message-skill-picker.md).

All pre-integration refs and the worktree map are preserved in the verified
ignored bundle under `state/backups/skill-chip-layout-20261004/`; the previous
main is preserved at `archive/2026-10-04/main-before-skill-chip-layout`.
Following the working baseline, verification is followed by committing the fix,
fast-forwarding local main, and removing the merged feature branch. Remote
refs and other worktrees are unchanged.

## Skill package format, Phase 1, 5 October 2026

The user requested the first phase of supporting Markdown references, using a
very small pack suitable for local models. The bounded
`codex/skill-package-format-v1` branch starts from local main `92c3a7b`.
The change defines the package/path/limit/failure contract, supplies a 1,591-byte
integer-clamp fixture with two short references, and freezes future live prompts.
It enables no resource imports or reader tools and changes no runtime behavior.
See [format and verification](skill-package-format-v1.md).

The focused run passed 266 tests with 2 existing skips. The full unrestricted
Windows regression passed 1,724 tests and 15 subtests, with 49 existing skips and
no failures. Reference-loading live gates are deferred until implementation;
deterministic compatibility checks do not qualify local or cloud model behavior.

Refs, worktrees and a verified all-ref bundle are preserved under ignored
`state/backups/skill-package-format-20261005/`. The previous main is preserved at
`archive/2026-10-05/main-before-skill-package-format`. After verification the
bounded change is committed, main fast-forwards and the merged branch is removed.
Other active checkouts and remote refs are unchanged.

## Skill package installation, Phase 2, 5 October 2026

The user requested Phase 2 on the bounded `codex/skill-package-install-v1`
branch from local main `b6021fc`. Local folders and Git snapshots now preserve
bounded supporting Markdown; Settings previews folders/repositories with counts,
size and package names. Whole-package byte comparisons, generated ownership
inventory, rollback and removal protect unrelated content. Single-file imports
remain available. Reference reading and model injection are not enabled.
See [implementation and verification](skill-package-install-v1.md).

The broad focused suite passed 520 tests with 2 existing skips; the final
Git/package recheck passed 74. The full unrestricted Windows suite passed
1,765 tests and 15 subtests, with 49 existing skips and no failures. An isolated
Qt preview/install visual audit passed with zero model requests. Earlier native
cleanup/test-wait failures and a failed optional diagnostic probe are recorded
separately. Model acceptance prompts, profiles and runtime authority are unchanged.

Refs, worktrees and a verified all-ref bundle are preserved under ignored
`state/backups/skill-package-install-20261005/`. The previous main is preserved
at `archive/2026-10-05/main-before-skill-package-install`. After verification the
bounded change is committed, local main fast-forwards and its merged feature
branch is removed. Other active checkouts and remote refs are unchanged.

## Skill reference reader, Phase 3, 5 October 2026

The user requested Phase 3 on the bounded `codex/skill-reference-reader-v1`
branch from local main `e22d6c9`. The change adds a revocable reader, compact
resource metadata, package/content-version checks, bounded UTF-8 continuation,
a replaceable storage interface and a scoped capability adapter. Native document
access opens/enumerates through directory handles and rechecks namespace identity.
The production catalog and conversation behavior remain unchanged until Phase 4.
See [reader implementation and verification](skill-reference-reader-v1.md).

The final focused unrestricted Windows suite passed 480 tests with 2 existing
skips, including 73 new reader cases. The full unrestricted suite passed 1,838
tests and 15 subtests, with 49 existing skips and no failures. Live local/cloud reference loading
is deferred until conversation integration. Acceptance prompts, fixtures, model
profiles, user settings, routing and context policy are unchanged.

Refs, worktrees and a verified complete-history bundle are preserved under ignored
`state/backups/skill-reference-reader-20261005/`. The starting main is preserved
at `archive/2026-10-05/main-before-skill-reference-reader`. Following verification,
the bounded change is committed, local main fast-forwards and its merged feature
branch is removed. Other active checkouts and remote refs are unchanged.

## Skill references in conversations, Phase 4, 5 October 2026

The user requested Phase 4 on `codex/skill-reference-conversations-v1`, starting
from verified local main `f31a483`. Active packages now supply compact inventories
and a turn-scoped reader. Matching package/version excerpts can be reused in
follow-ups, with bounded context accounting, stale-scope revocation and filtered
provider replay. Ordinary host access and write approvals remain unchanged.
See [conversation implementation and verification](skill-reference-conversations-v1.md).

The final focused cleanup/reference/outcome check passed 69 tests, including
37 Phase 4 cases. The isolated registry/conversation recheck passed 76 tests.
Earlier full-run cleanup regressions were fixed. A later native directory-rename
failure remains recorded separately. The final full unrestricted Windows
confirmation passed 1,875 tests and 15 subtests, with 49 existing skips and no
failures, including the directory-rename case.
Live local/cloud qualification remains Phase 5. Acceptance prompts, the tiny
fixture, model profiles, sampling, runtime settings and skill selection are unchanged.

Refs, worktrees and a verified complete-history bundle are preserved under ignored
`state/backups/skill-reference-conversations-20261005/`. The starting main is
preserved at `archive/2026-10-05/main-before-skill-reference-conversations`.
After verification the bounded change is committed, local main fast-forwards
and its merged feature branch is removed. Other active checkouts and remote refs
are unchanged; this phase does not publish to GitHub.

## Skill reference qualification, Phase 5, 5 October 2026

The user requested Phase 5 and authorized reuse of their existing desktop key
file for live cloud checks. `codex/skill-reference-qualification-v1` starts from
verified local main `05221dc`. The branch adds an isolated tiny-pack live matrix,
a restricted generated-code evaluator, a fail-closed qualification checker and
the retained [qualification audit](skill-reference-qualification-v1.md).
Application behavior, accepted profiles, runtime selection and frozen prompts
are unchanged. No credential is copied or published.

Candidate `789e011` completed 100 required cells: 36 passed, 44 failed and 20
blocked. Each local model passed 6/20; Luna passed 18/20; Sol's first request
was denied by account permissions and its remaining 19 cells were not attempted.
All owned resources exited and user configuration hashes were unchanged. A
wording-check false negative for typographic apostrophes was fixed in `866efed`;
the fresh Luna subset again passed 18/20, with genuine disabled-reader fallback
failures. Original and subset evidence remain separate. The reference feature
is unqualified; this audit does not promote any model or release flag.

Initial deterministic full runs passed 1,910 and then 1,912 tests, each with
49 existing skips and 15 subtests passed. The evaluator's final focused check
passed 38 tests. A later full run recorded 1,911 passed and two unchanged native
test failures, retained in the audit. Their isolated recheck passed 117 tests;
final full confirmation passed 1,913 tests and 15 subtests with 49 existing skips
in 225.23 seconds, including both previously failing native cases.

All pre-integration refs, worktrees and a verified complete-history bundle are
preserved under ignored `state/backups/skill-reference-qualification-20261005/`.
The prior main is preserved at
`archive/2026-10-05/main-before-skill-reference-qualification`. After deterministic
verification, commit the audit, fast-forward local main and remove its merged
feature branch. Other active worktrees and remote refs remain unchanged.

## Cloud stream diagnostics, 6 October 2026

The user requested retaining safe failure reasons and displaying the specific
cloud interruption category. The bounded `codex/cloud-stream-diagnostics`
branch starts from local main `2cbfb49`. Reasons survive the adapter, agent
runtime, saved conversation, worker and chat; logs retain only fixed categories
and counters. Incomplete calls stay blocked. See the
[diagnostics and verification record](cloud-stream-diagnostics.md).

The final focused checks passed 191 tests; the other affected OpenAI contract
checks passed 103. The initial full run had one protocol-limit wording failure,
which was corrected and passed its focused recheck. Final unrestricted Windows
confirmation passed 1,917 tests and 15 subtests, with 49 existing skips and no
failures in 235.61 seconds. Live API/model qualification gates remain unrun,
separate from deterministic passes.

All pre-integration refs and the worktree map are preserved in the verified
complete-history bundle under ignored
`state/backups/cloud-stream-diagnostics-20261006/`. After verification, commit
the bounded change, fast-forward local main and remove its merged local branch.
Runtime selection and user conversations/settings are preserved; other active
worktrees and remote refs are unchanged.
The previous main is also preserved at
`archive/2026-10-06/main-before-cloud-stream-diagnostics`.

## SDK stream-error diagnostics, 6 October 2026

Following the user's reproduced failure, `codex/cloud-sdk-error-diagnostics`
starts from local main `969ddc4`. The pinned SDK raises provider stream errors
before yielding their events, which the initial diagnostic handler incorrectly
grouped with decoding failures. The bounded follow-up separates provider,
decoding and SDK schema errors and allowlists recognized provider codes. The
user's subsequent normal-app run confirms `rate_limit_exceeded` after 22
successful tool calls. No private message/body is logged and no agent API
request or transcript replay is performed. See the
[follow-up evidence](cloud-stream-diagnostics.md#sdk-provider-error-follow-up-6-october-2026).

The focused checks passed 204 tests. Full unrestricted Windows confirmation
passed 1,930 tests and 15 subtests, with 49 existing skips and no failures in
236.04 seconds. Existing live qualification gates remain unrun; the user's
reproduction is diagnostic evidence. Model limits, prompts, retry/routing and
tool execution policy are unchanged. Rate-limit pacing is separate follow-up
work rather than an unverified model-profile adjustment.

Pre-integration refs and the worktree map are preserved in the verified bundle
under ignored `state/backups/cloud-sdk-errors-20261006/`; previous main is also
preserved at `archive/2026-10-06/main-before-cloud-sdk-errors`. After verification,
commit, fast-forward local main and remove the merged local feature branch.
Other active worktrees, user settings/conversations and remote refs remain
unchanged.

## Cloud step budget, 6 October 2026

The user requested the maximum supported cloud step count while retaining 24
for local mode. `codex/cloud-max-steps` starts from verified local main
`36e2df4`. The accepted configuration now selects 32 cloud steps and 24 local
steps, including after switching modes and in the temporary skill-reference
runtime. The existing hard 32-step contracts and other budgets are unchanged.
See the [implementation and verification record](cloud-step-budget.md).

The unrestricted focused checks passed 168 tests. Full unrestricted Windows
confirmation passed 1,937 tests and 15 subtests, with 49 existing skips and no
failures in 237.32 seconds. Live API/model qualification gates remain unrun and
separate from deterministic checks.

The previous agent configuration, refs, worktree map and verified
complete-history bundle are preserved under ignored
`state/backups/cloud-max-steps-20261006/`. The previous main is also preserved at
`archive/2026-10-06/main-before-cloud-max-steps`. After verification, commit,
fast-forward local main and remove the merged local feature branch. Other
active worktrees, user runtime selection/conversations and remote refs remain
unchanged.

## Cloud rate pacing, 6 October 2026

The user's latest normal-app failure is a provider token rate limit while the
32-step cloud budget is active. `codex/cloud-rate-pacing` starts from local main
`e05aee4`. The user reports 200,000 TPM and 500 RPM; the reproduced run records
309,803 total tokens across 21 completed operations in about 44 seconds.
See the [content-free evidence and verification record](cloud-rate-pacing.md).

The bounded change adds Responses request admission using a rolling minute
ledger and numeric server capacity/reset headers. It retains capacity after
long/interrupted streams and preserves SDK retry/partial-stream behavior.
The user's bootstrap account limits stay in ignored runtime state. Accepted
model profiles, sampling, prompts, tool behavior, context and deadlines are
unchanged; cloud steps remain 32 and local 24.

Final unrestricted focused checks passed 301 tests in 26.73 seconds. Final full
unrestricted confirmation passed 1,954 tests and 15 subtests, with 49 existing
skips and no failures in 248.54 seconds. An earlier full run's unchanged Windows
folder-rename access-denied failure is retained in the audit; its 49-test
isolated recheck and final full confirmation pass. Live API/model gates remain
unrun and separate from deterministic checks. No paid API requests or key
changes were made during verification.

Pre-change refs and the worktree map are preserved in the verified bundle under
ignored `state/backups/cloud-rate-pacing-20261006/`. Preserve prior main at
`archive/2026-10-06/main-before-cloud-rate-pacing`, commit the verified bounded
change, fast-forward local main and remove its merged local branch. Other active
worktrees, user conversations/selection/keys and remote refs are unchanged.

## Working status UI review branch, 6 October 2026

The user's explicit request places the working status changes on a new branch,
`codex/working-status-ui`, from local main `ca90b4c`. See the
[implementation and verification record](working-status-ui.md). Commit the
bounded verified change and retain this branch for review; immediate
fast-forward integration and branch deletion are deferred for this request.
Local main, other worktrees and remote refs remain unchanged. Pre-change refs,
worktree map and the verified complete-history bundle are preserved under
ignored `state/backups/working-status-ui-20261006/`.

Final unrestricted focused checks passed 246 tests and 5 subtests. Final full
unrestricted confirmation passed 1,967 tests and 15 subtests, with 49 existing
skips and no failures in 297.59 seconds. Earlier intermittent native Windows
folder-rename failures and the successful five-case isolated recheck remain
in the verification record. No existing native implementation or acceptance
test was changed. Live model/API gates remain unrun and separate from these
passed checks; no paid API requests or key changes were made.

## Working status UI integration, 7 October 2026

The user now authorizes merging every new change into `main` and pushing it
to GitHub. This supersedes the UI branch's review deferral above. The verified
UI source tip is `dd596eb`, containing working status, inline highlights,
composer placeholders, control styling and per-message skill captions.
Local main starts at `ca90b4c`; fetched `origin/main` remains `92c3a7b`.
Both are ancestors of the UI tip, so integration requires no source changes.
The push includes the eleven earlier unpublished local-main commits as well
as the five UI commits and this documentation record.

The latest unrestricted full suite passed 1,974 tests and 15 subtests, with
49 skips and no failures in 220.54 seconds. This integration reuses that
verification of the unchanged source; live model/API gates remain unrun.
See [the UI verification record](working-status-ui.md).

Pre-integration refs, worktree map and a verified complete-history bundle are
preserved under ignored `state/backups/working-status-integration-20261007/`.
Preserve prior main at `archive/2026-10-07/main-before-working-status-ui`,
commit this record, fast-forward local main and push only main to origin.
Remove the merged local UI branch after successful integration. Other active
worktrees and remote feature/archive branches are outside this operation.

## Python Coder skill, 7 October 2026

The user requests an open-source synthesis matching the editorial discipline of
the O.R.S.I. flagship design package. `codex/python-coder-skill` starts from local
main `5c1e613`. The bounded change adds the authored `skills/python-coder` package,
twelve references, provenance/license notices, documentation and behavioral
artifact checks. See [the research and verification record](python-coder-skill.md).
No application runtime, provider configuration or existing installed skill is
changed. The new package is installed through the existing package installer.

Unrestricted focused checks passed 127 tests in 3.23 seconds. Full unrestricted
Windows confirmation passed 2,000 tests and 15 subtests, with 49 existing skips
and no failures in 247.00 seconds. Native package installation and all reference
continuations round-trip correctly; the published examples are exercised for
validation, failed saves, cleanup failures and structured concurrency. Live model
qualification remains unrun and separate from these passed deterministic checks.

Pre-change refs, worktree map and a verified complete-history bundle are preserved
under ignored `state/backups/python-coder-skill-20261007/`. Preserve prior main at
`archive/2026-10-07/main-before-python-coder-skill`. Commit the verified change,
fast-forward local main, and remove the merged local feature branch. The user's
earlier instruction to merge and push new changes authorizes publishing main;
do not publish or delete remote feature/archive branches or alter other worktrees.

## Explicit skill selection, 7 October 2026

`codex/explicit-skill-selection` starts from local main `8fb396c`. The user reports
an unselected follow-up acquiring a Python Coder skill and asks for explicit
selection in both local and cloud modes. The bounded change disables automatic
selection at the service default and application composition boundary. Explicit
attachments and existing conversation history retain their established behavior.
See [the implementation and verification record](explicit-skill-selection.md).

Final native focused verification passed 313 tests with no failures or skips.
Full native regression passed 2,010 tests and 15 subtests, with 49 existing skips
and no failures in 230.82 seconds. The first run's three old-default test
expectations and their explicit fixture updates are retained in the verification
record; live model/API gates remain separate from deterministic checks.

Pre-change refs, the worktree map and a verified complete-history bundle are
preserved under ignored `state/backups/explicit-skill-selection-20261007/`.
Prior main is preserved at `archive/2026-10-07/main-before-explicit-skill-selection`.
After verification, commit, fast-forward local main and remove the merged local
feature branch. The user's existing instruction to merge and push new changes
authorizes publishing main only; other active worktrees and remote feature/archive
branches are outside this operation.

## Read progress guard, 7 October 2026

`codex/version-aware-read-guard` starts from local main `d00fe59`. The reported
cloud error was a false repetition stop on a third read after two successful
edits to the same file. The bounded change uses settled native results to renew
only the affected text-read allowances after proven content changes. No-progress
calls, writes, duplicate batches, permissions and configured budgets retain their
existing limits. See [the implementation and verification record](version-aware-read-guard.md).

Pre-fix synthetic reproduction failed the seven progress expectations while
passing eleven guard checks. Focused native verification after the fix passed
136 tests with one existing host symbolic-link skip. Final full native regression
passed 2,030 tests and 15 subtests, with 49 existing skips and no failures in
241.63 seconds. The first run's unchanged installer cleanup and reader rename
errors are retained in the verification record; all 133 tests in those groups
passed their isolated native recheck. Live model/API gates remain separate from
deterministic verification. Actual game files, model profiles and user settings
are unchanged.

Pre-change refs, the worktree map and a verified complete-history bundle are
preserved under ignored `state/backups/version-aware-read-guard-20261007/`.
Prior main is preserved at `archive/2026-10-07/main-before-version-aware-read-guard`.
After verification, commit, fast-forward local main, and remove the merged local
feature branch. The user's standing merge-and-push instruction authorizes
publishing main only. Other active worktrees and remote feature/archive branches
are outside this operation.

## Attachment foundation, 7 October 2026

`codex/attachment-foundation` starts from local main `2c96700`. The user approved
phase 1 of the five-phase image/file input plan. The bounded change adds immutable
snapshot storage and durable ordered references, worker/service/inference interfaces,
local per-message admission and explicit unsupported-backend gates. Existing
production adapters and the composer + placeholder remain disabled for attachments;
extraction, actual vision and cloud uploads belong to later phases. See
[the phase 1 implementation and verification record](attachments-phase1.md).

Final focused native checks passed 160 tests in 9.21 seconds. Full native regression
passed 2,070 tests and 15 subtests, with 49 existing skips and no failures in
246.74 seconds. All 40 new attachment contract cases passed, including Windows
source/copy handle checks. Live attachment model/API qualification is deferred
to the provider phases. Dependency and Git whitespace checks passed. No user
settings, model profiles, sampling or prompt policies were changed.

Pre-change refs, worktree map and a verified complete-history bundle are preserved
under ignored `state/backups/attachment-foundation-20261007/`. Prior main is retained
at `archive/2026-10-07/main-before-attachment-foundation`. After verification, commit,
fast-forward local main and remove the merged local feature branch. The user's
standing merge-and-push instruction authorizes publishing main only; other active
worktrees and remote feature/archive branches remain outside this operation.

## Attachment composer and preparation, 7 October 2026

`codex/attachment-composer` starts from local main `b0f271b`. The user approved
phase 2 of the image/file input plan. The bounded change activates + selection,
ordered removable draft cards, image thumbnails, local file dropping and clipboard
input. A cancellable worker copies and prepares supported images/documents outside
the GUI event thread. Production attachment inference remains gated until the
provider phases; unavailable sending retains the complete draft and manual skill.
See [the phase 2 contract and verification record](attachments-phase2.md).

Final focused native checks passed 150 tests and five subtests in 13.26 seconds.
Full native regression passed 2,119 tests and 15 subtests, with 49 existing skips
and no failures in 251.16 seconds. All 49 new composer/preparation cases passed.
The initial batch test's event-loop starvation and its actual Qt-loop check are
recorded separately; acceptance prompts were unchanged. Actual composer rendering
was visually inspected. Dependencies and Git whitespace checks passed. Live
attachment model/API gates remain deferred to the provider phases; no paid API
requests were made. User settings, profiles and existing model/tool policies
were unchanged.

Pre-change refs, worktree map and a verified complete-history bundle are preserved
under ignored `state/backups/attachment-composer-20261007/`. Prior main is retained
at `archive/2026-10-07/main-before-attachment-composer`. After verification, commit,
fast-forward local main and remove the merged local feature branch. The user's
standing merge-and-push instruction authorizes publishing main only; other active
worktrees and remote feature/archive branches remain outside this operation.

## Local document input, 7 October 2026

`codex/local-document-input` starts from local main `5b74da8`. The user approved
phase 3A of the image/file input plan: local text-document input only. Both local
llama.cpp adapters now consume complete extracted documents as user source material,
with accounting, intact attachment-turn admission, follow-ups, archive restoration
and native tool continuations. Local image input and cloud input remain gated for
their later phases. See [the phase 3A verification record](attachments-phase3a.md).

Focused native checks passed 160 tests. The accepted 14B live smoke passed with
the existing production catalog, isolated read scope, actual 16,384 context and
4,096 output reserve. The first restricted-catalog continuation failure is recorded
separately; acceptance tasks, sampling and production policies were unchanged.
The owned test server exited. Dependencies and whitespace checks passed; no cloud
API requests were made. Versioned model profiles and user settings were untouched.
Final full native regression passed 2,147 tests and 15 subtests, with 50 optional
skips and no failures in 316.34 seconds. The phase's opt-in live smoke was run
separately and passed; other skipped live gates remain unqualified.

Pre-change refs, worktree map and a verified complete-history bundle are preserved
under ignored `state/backups/local-document-input-20261007/`. Prior main is retained
at `archive/2026-10-07/main-before-local-document-input`. After full verification,
commit, fast-forward local main, publish main under the user's standing authorization
and remove only the merged local feature branch. Other worktrees and remote branches
remain outside this operation.

## Attached document source grounding, 7 October 2026

`codex/attached-document-grounding` starts from local main `4e4134b`. A real attached
PDF was successfully extracted, but the 14B model searched the user's disk instead.
The bounded repair clarifies available document source text in scoped trusted policy;
plain chats, routing, tool implementations, profiles and sampling are unchanged.
Validation also exposed Windows snapshot-directory rename denials. Snapshot publication
now uses the existing state writer's short bounded tolerance, with cancellation and
immutable-byte/parent-pin protections preserved; the native handle-release fixture uses
that tolerance without accepting persistent leaked handles.
See [the failure analysis and verification](attached-document-grounding.md).

Final expanded focused checks passed 200 tests. The accepted 14B live check passed both generic
attachment reading with zero filesystem calls and explicit native file operations
with attached source. The user's actual PDF also passed an isolated read with no
filesystem calls, preserving their active conversation and prepared source bytes.
Content-free summaries retain only numeric counts/fixed outcomes, and owned servers
exited. Optional live gates and the initial full suites' Windows snapshot/fixture
rename errors are recorded separately from passed checks.
Final full native regression passed 2,157 tests and 15 subtests, with 50 optional
skips and no failures in 264.16 seconds. Dependencies and whitespace checks passed.

Pre-change refs/worktree maps and a verified history bundle are preserved under
ignored `state/backups/attached-document-grounding-20261007/`. Prior main is retained
at `archive/2026-10-07/main-before-attached-document-grounding`. After full verification,
commit, fast-forward/publish main under the standing user instruction and remove only
the merged local feature branch. Other worktrees and remote branches remain untouched.

## Local vision input, 7 October 2026

`codex/local-vision-input` starts from verified local main `b47c01f`. Phase 3B adds bounded
native image input for the explicitly selected Qwen3-VL 4B and verified matching projector,
without changing the default 14B, its sampling, manual skill activation or tool permissions.
The projector is an ignored local model resource; only its pinned identity is versioned.
See [the local image contract and qualification](attachments-phase3b.md).

GPU qualification covers visual formats, different images across turns, follow-up/archive
recall, real native tool continuation and a real 14B → vision → 14B switch. The separate CPU
image gate verifies its actual limits. Numeric diagnostics preserve no source/response bodies;
all owned model servers exited, and user selection/profile bytes were preserved by the tests.
Optional live gates and native Windows fixture failures remain separate verification evidence.

Pre-change refs, worktree maps and a verified complete-history bundle are preserved under
ignored `state/backups/local-vision-input-20261007/`. Prior main is retained at
`archive/2026-10-07/main-before-local-vision-input`. After verification, commit the bounded
change, fast-forward/publish main under the standing user authorization and remove only the
merged local feature branch. Other active worktrees and remote branches are outside this work.

Final native regression passed **2,189 tests and 15 subtests, with 52 optional skips and
no failures in 259.39 seconds**. GPU and CPU live vision gates passed separately; the
full-run Windows fixture denials, isolated successful rechecks and optional skips are
recorded in the phase contract. Dependency, compilation and whitespace checks passed.

## Native cloud attachment input, 7 October 2026

`codex/cloud-attachment-input` starts from verified local main `eebb431`. The user approved
phase 4A of the attachment plan and authorized reuse of the existing API credential. The bounded
change projects immutable references to native OpenAI image/file input, checks actual multimodal
input tokens on the worker, and preserves source input through follow-ups, restored/archive
chats and native tool continuations. Local adapters/profiles, sampling, manual skill/model
selection, step budgets and user runtime settings remain unchanged. See
[the phase 4A contract and qualification](attachments-phase4a.md).

Expanded deterministic verification passed 326 tests. Default-profile real-cloud qualification
passed seven synthetic source inputs, scanned PDF page recognition, two-image cross-turn recall,
reopening/archive recall and actual stat/continuation with the twelve-tool production catalog.
The key stayed in memory, source/response bodies stay in ignored synthetic fixture state, numeric
diagnostics omit source and credential contents, and owned transport resources closed. Final full
native regression passed 2,221 tests and 15 subtests, with 53 optional skips and no failures/errors
in 278.479 seconds. Other cloud-profile access, maximum capacities and unrelated skipped gates
are not relabeled as qualified. Compilation, dependency and whitespace checks passed.

Pre-integration refs/worktree maps and a verified complete-history bundle with 76 refs are
preserved under ignored `state/backups/cloud-attachment-input-20261007/`. Prior main is retained
at `archive/2026-10-07/main-before-cloud-attachment-input`. Commit the bounded verified change,
fast-forward local main and publish main under the user's standing merge-and-push instruction.
Remove only this merged local feature branch. Other worktrees and remote feature/archive branches
are outside this operation. Phase 4B capacity qualification and phase 5 lifecycle work remain.

## Cloud attachment capacity, 7 October 2026

`codex/cloud-attachment-capacity` starts from verified local main `150a49a`. The user approved
phase 4B and retains authorization to reuse the existing API key for cloud verification.
The bounded change measures source-bearing groups before admission, fits attachment reply
allowances to account ceilings, adds numbered native source labels and preserves composer
drafts on capacity rejection. Accepted model profiles, sampling, prompts, tool behavior,
manual skill/model selection, local attachment count/GPU behavior and user settings are unchanged.
See [the phase 4B capacity and verification record](attachments-phase4b.md).

Live capacity qualification passed 1,500 images, a 49,999,999-byte PDF and 256 files; the original
phase 4A follow-up/archive/tool-continuation gate also passed with unchanged requests. Initial
live source-order recognition failures and the numbered-label repair are retained in the record.
Skipped full-size JSON and other-profile qualification are separate from passed live gates.
Credentials remain session-only, and numeric diagnostics omit source/response/key contents.

Final full native verification passed 2,236 tests and 15 subtests, with 56 optional skips,
no failures/errors and a duration of 258.313 seconds. Expanded focused checks passed 200
tests before numbered labels and 67 after the label refinement. Compilation, dependency
consistency and whitespace checks passed. Separate live gates and skipped qualification
remain explicitly identified in the capacity record.

Before integration, all 77 pre-change refs and the worktree map were preserved in a verified
complete-history bundle under ignored `state/backups/cloud-attachment-capacity-20261007/`.
Prior main is retained at `archive/2026-10-07/main-before-cloud-attachment-capacity`. After
verification, commit the bounded change, fast-forward local main and publish main under the
standing user instruction. Remove only the merged local feature branch. Other active worktrees
and remote feature/archive branches remain outside this operation. Phase 5 remains pending.

## Attachment context and lifecycle, 7 October 2026

`codex/attachment-lifecycle` starts from verified main `b61f602`. The user approved the final
attachment implementation phase. The bounded change preserves rejected composer drafts until
durable admission, transfers snapshot ownership atomically with history, cleans up owned unsent
copies and records cloud context overflow distinctly. Existing context/prompt/routing/sampling
and tool policies, profiles, one-attachment local limit, manual skill/model selection and GPU
architecture are unchanged. See [phase 5 evidence and limitations](attachments-phase5.md).

Final native full regression passed 2,260 tests and 15 subtests, with 57 optional skips and no
failures/errors in 266.097 seconds. Expanded checks passed 291 tests; the final ownership/source
handle recheck passed 85 tests. Real cloud stop/crash/archive and production-tool gates passed.
GPU vision and actual 14B → VL → 14B switching passed with unchanged profiles/user selection and
released owned processes. The 14B document gate read attachments correctly but omitted a requested
stat call on two branch runs and the unchanged prior baseline. That model-choice limitation remains
separate from passing lifecycle checks; its acceptance prompt/policy was not altered to pass.
Compilation, dependency and whitespace checks passed. Numeric diagnostics contain no keys or
source/response content, and live credentials remain session-only.

Pre-integration refs/worktree maps and a verified complete-history bundle are preserved under
ignored `state/backups/attachment-lifecycle-20261007/`; prior main is retained at
`archive/2026-10-07/main-before-attachment-lifecycle`. Commit the verified change, fast-forward
main and publish main under the standing user authorization. Remove only the merged local
feature branch, preserving other active worktrees and remote feature/archive branches.

## Sent image previews, 7 October 2026

`codex/chat-image-previews` starts from verified main `990d401`. Image attachments
now appear inside user bubbles: one larger rounded preview or an ordered row of
miniatures, with horizontal scrolling for long rows and snapshot-backed restoration.
Background verification/decoding and a bounded cache keep large image selections
responsive. Only display, documentation and tests change; inference and user settings
retain their existing behavior. See [the preview contract and evidence](chat-image-previews.md).

Expanded focused checks passed 144 tests and five subtests; final UI/composer checks
passed 72 tests and five subtests, and the final format/cache group passed 12 tests.
The first full run's unchanged native skill-reader rename denial passed its entire
73-test isolated recheck. Final full native regression passed **2,274 tests and 15
subtests**, with **57 optional skips**, no failures/errors, in **330.37 seconds**.
Actual app rendering was visually inspected using synthetic images. Compilation,
dependencies and whitespace checks passed; live model/API gates remain separate and
were not rerun for this display change.

Pre-integration refs and worktree maps are preserved in a verified complete-history
bundle under ignored `state/backups/chat-image-previews-20261007/`. Prior main is
retained at `archive/2026-10-07/main-before-chat-image-previews`. After verification,
commit, fast-forward main, publish main under the standing user authorization and
remove only the merged local feature branch. Other worktrees and remote branches
remain untouched.

## Image viewer and follow-up composer, 7 October 2026

`codex/image-viewer-reply` starts from main `023f10c`. Clicking a miniature opens a
near-screen-size image viewer with navigation and an image follow-up composer.
Replies reuse verified original references through the established attachment/send
path, preserve existing drafts and cancel automatic sending if the viewer closes
during preparation. Local mode retains one image per message; cloud can explicitly
include the set. A trusted output-image display hook supports future cloud generation,
which remains unimplemented. See [the contract and qualification](image-viewer.md).

Expanded focused native checks passed 162 tests and five subtests; final viewer/composer
checks passed 41 tests. Actual synthetic rendering, compilation, dependency consistency
and whitespace checks passed. The initial full run recorded 2,287 passed, one unchanged
reader-fixture Windows rename denial, 57 skipped and 15 subtests in 373.36 seconds.
The first isolated reader recheck recorded 72 passed and a different rename denial;
the second passed all 73 tests. The final full rerun recorded **2,287 passed, one
unchanged registry rename failure, 57 skipped and 15 subtests** in **378.15 seconds**.
All **112 registry/reader tests passed** their final combined native recheck. Both
full-run failures remain explicit unresolved Windows verification evidence; no full
run is labeled passing, and skill-reader/registry behavior or assertions were not
changed. Live model/API gates remain separately skipped for this UI change.

Pre-integration refs/worktree maps and a verified complete-history bundle are
preserved under ignored `state/backups/image-viewer-reply-20261007/`; prior main is
retained at `archive/2026-10-07/main-before-image-viewer-reply`. Commit the bounded
change, fast-forward main, publish main under the standing user authorization and
remove only the merged local feature branch. Other active worktrees, remote branches,
user settings, accepted profiles and inference policies remain unchanged.
