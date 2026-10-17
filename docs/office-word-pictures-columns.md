# Native Word pictures and section flow

Started on `codex/word-pictures-columns` from clean local `main` `528c9e8`.
The complete-body composition and settled-read recovery corrections remain in
place. Only focused checks are authorized; the full repository suite is not run.
Private settings, accepted model profiles, core prompts, routing, sampling,
context policy and retry limits are unchanged. No remote operation is authorized.

## Contract and native structure

`office.word_compose` advertises a complete `sections` replacement. Each section
contains nonempty native content, one or two equal text columns, explicit
`column_spacing_mm`, and a `continuous` or `new_page` start. The first section
starts continuously. A one-column title/figure section can precede flowing
two-column text and a return to full-width text. `column_break` advances a text
column. Historical `pages` still impose page starts, and historical `blocks`
retain their deterministic page-break normalization. These representations
cannot compete in one call. They normalize before approval to one bounded typed
block sequence with explicit section transitions; empty/break-only sections fail.
The advertisement requires explicit section start/count/spacing and paragraph/
table kind discriminators. Oversized pictures receive the calculated numeric
column-width limit in privacy-safe validation feedback.
Historical provider evidence replays against its original pages/blocks schema,
without changing original provider bytes or granting new execution authority.

Tables and inline pictures must fit their containing text column, accounting for
the gap and page margins. Pictures also must fit the available page height.
WordprocessingML `sectPr`, `cols`, native column breaks and section start types
provide actual text flow. Columns are not simulated with tables, tabs or boxes.
Headings, body text, captions, credits and table cells remain editable. Primary
running identification is consistent across sections; PAGE/NUMPAGES numbering
continues. Saving remains a separate approved operation.

## Immutable picture assets and access

`office.image_register` is a read capability for the selected Word session. Its
`path` is an authorized local PNG/JPEG file or an `attachment:` reference returned
by `office.read` target `assets`. Only admitted image references in that exact
conversation are discoverable. The attachment store verifies its original
immutable reference and bytes; private profile storage does not become a general
filesystem permission. Local files use the existing host read policy and pinned
bounded snapshot stream. No remote URL, arbitrary fetching or rendered-page
reference is accepted as an insertion source.

Registration returns an opaque asset plus format, pixel dimensions and byte
count. Image bytes travel only through bounded private bridge chunks. The bridge
stages immutable bytes scoped to the Word session; the model submits no image
bytes. Image blocks specify the asset, width, meaningful alt text, and optional
editable caption/credit paragraphs. Native embedded media, relationships and
inline DrawingML retain aspect ratio. Approval binds content digests, placement,
sizing and the complete pre-write document identity. Native readback independently
checks the embedded bytes, objects, alt text and dimensions. Changing a source
file after approval cannot substitute its bytes into the staged asset.

Initial limits are eight assets/pictures, 256 KiB per image, 2048 pixels per side,
four million decoded pixels per image, and one MiB total media. The media limit
counts every picture placement, including repeated uses of one asset. Complete
native snapshots are limited to two MiB, 16 sections, 32 tables, 512 cells and 32,768
native text positions; composition retains its 96-block/24,000-character bounds.
Only ordinary inline PNG/JPEG pictures are supported. Standard Word local-DPI
metadata is preserved; floating/legacy drawings, remote links, cropped/effected
pictures, running-matter pictures, unknown picture extensions and unsupported
binary dependencies are refused before writing. Unsupported content is never
discarded to make a snapshot pass.

## Capture, verification and recovery

Complete capture retains the native package graph, media and section properties.
Media identity is content based, and relationship numbering is normalized.
Regenerated drawing editing IDs are bookkeeping; actual image bytes, geometry,
alt text, relationships, document text, formatting and section settings remain
guarded. PAGE/NUMPAGES caches retain their existing normalization.
Word also recalculates dormant `docGrid` line pitch during section import. Only
that pitch in default/no-grid mode is bookkeeping; the grid mode and all active
grid pitch remain guarded. Active document grids are explicitly outside complete
report authoring, and are refused before writing. Microsoft's
[grid enumeration](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.docgridvalues?view=openxml-3.0.1)
identifies default mode as no document grid. Native section restoration retains
already matching page properties instead of unnecessarily resetting them.
Single-column layout views report zero gap, avoiding Word's undefined-spacing
sentinel; two-column views report the actual native gap.

Running matter is captured from that same complete package, avoiding repeated
large package exports for every header/footer. Authoring cursor reads slice the
retained immutable view, checking the complete native document before and after
each read. Foreign changes still fail. This avoids re-exporting every section
dependency for each small text fragment, without increasing ordinary read limits.
Ordinary `document` cursor reads capture at most four new paragraph targets per
call, retaining their original snapshots and native anchors. A complete bounded
package fingerprint before and after each page guards changes anywhere in the
document, including text not yet read. Earlier observed fragments and retained
anchors remain checked; smaller page batches do not relax foreign-change checks.

Native Word retains a primary empty header after a many-to-one section import.
Verification accepts only its ordinary empty paragraph with zero fields,
hyperlinks or drawing objects; it does not ignore residual header content.
Replacement strips obsolete media and running-matter dependencies before import.
Owned recovery restores the captured section layouts and native running stories,
then checks complete identity. Exact approvals, uncertain-write blocking,
identical-call safeguards, unchanged receipts and no automatic replay remain.

Complex native print export/rasterization receives a bounded 30-second deadline
only for `read render:first:last`. Ordinary reads retain ten seconds; full-body
composition retains its existing 60 seconds. Explicit host/test deadlines remain
authoritative. Model request budgets and retries are unchanged.

## Budget and diagnostics

The accepted manifest contains ten tools. Full Responses projection measures
22,045 UTF-8 bytes and 7,829 offline reserve tokens, versus baseline
19,945/7,081: an increase of 2,100 bytes and 748 tokens. Catalog ceilings are
22,500/8,100; these are catalog measurements, not model context limits or billed
tokens. Disabled/local exposure remains empty.

Persisted diagnostics allow only fixed stages/categories, content lengths,
block/section/image counts, column settings, image dimensions and byte counts.
They exclude document text, image bytes, source filenames/paths, opaque asset
identities, credentials and private conversation contents. Intended DOCX/PNG
artifacts are separate from diagnostic persistence.
Read timeouts additionally retain only the allowlisted target kind and numeric
read bounds, so an unknown later read can be distinguished from print rendering.

## Focused evidence and acceptance

The final focused selection in `state/word-pictures-final-integration.xml` passes
258 checks, with two opt-in native gates skipped there. The one-column display
regression added afterward passes in `state/word-pictures-final-display.xml`
(27 picture-module checks, two native skips), with the active-grid capture guard
also passing in `state/word-pictures-final-guards.xml`: 259 distinct focused
checks pass.
The strengthened direct native gate passes in
`state/word-pictures-linked-grid-identity.xml` (39.564 seconds). It qualifies real
Word section/column properties, a pre-existing native PNG, mixed two/one-column
sections and inherited running identification, PNG/JPEG insertion, aspect ratio,
alt text, editable captions and table, save/reopen and exact restoration. The
final production bridge gate passes in `state/word-pictures-final-native-bridge.xml`
and additionally
qualifies local and conversation-attachment registration, source substitution
after approval, unchanged composition, owned recovery, refusal after foreign
changes, embedded original bytes in the saved DOCX and owned-process release.
Its strengthened ordinary paragraph-cursor qualification also passes in
`state/word-pictures-native-body-read.xml` (118.250 seconds): four new targets per
page, approximately 1.1–2.6 seconds per paragraph page, no failed calls. The
repeated-placement media-limit regression also passes before compilation.
All three native fixture pages were rendered and visually inspected. This
synthetic native plan is not evidence of live model generation.

No original illustrated-document acceptance prompt was found in available
fixtures/helpers. `tests/fixtures/word_illustrated_prompt.txt` freezes a new
fixture before live testing. Its normalized SHA-256 is
`ad77c48b6feeff058f43e2184436bbd4e9f857253c219f69bc2052a7c142e32b`.
Only unique output/document and original-illustration paths are substituted.
The two source diagrams are original labelled synthetic illustrations, not stock
photographs or externally sourced measurements. The helper uses the configured
GPT-6 Luna, actual Responses decoding, HybridInferenceEngine, ConversationService,
agent/executor, production Office bridge, ASK approval and native readback.
It seeds no response, plan or synthetic Office state. Existing authorized
credentials stay in memory. Desktop/report.docx is never overwritten.

The first authorized attempt makes 17 model requests and embeds two pictures,
but omits the table/full-width title section, later hits a ten-second read
deadline and does not save. The exact failed read target was not retained;
attributing it to rendering was an initial assumption, not established evidence.
The second attempt makes ten requests and dispatches no write: an oversized
repeated-image plan, then repeated 82-mm pictures in 81-mm columns. Explicit
section/discriminator fields, a default 81-mm example and numeric width feedback
address the demonstrated contract ambiguity without changing the fixture.
The third attempt makes 16 requests, writes two pictures and a 5-by-4 table, but
chooses two one-column sections and later hits another ten-second read deadline.
Structural diagnostics show no provider content/sections lost through decoding,
approval or dispatch. That run is incomplete and unsaved. Earlier read target
uncertainty led to the separate native paragraph-read regression and correction.

The last unchanged-fixture attempt (`word-illustrated-live-bounded-reads-20261017`)
makes 33 configured-model requests. Its settled evidence records two successful
native compositions, an editable text correction, successful paragraph cursor
reads, both complete five-page render batches, and an approved successful save.
There is no read timeout. Invalid table/save requests and an identical layout
read are refused as designed. The provider ends with `IncompleteResponseError`;
the run remains failed acceptance, not a clean completed model turn.

The saved live DOCX is independently reopened read-only and every one of its
five pages rendered and visually inspected. Content-free package/native records
are `saved-package-inspection.json` and `saved-native-inspection.json` beside the
fixture. They confirm section columns 1/2/1, native start types 0/0/2, an 8.01-mm
body gap, one column break, two 78-mm pictures with nonblank alt text, exact
original embedded PNG bytes, one editable table, PAGE/NUMPAGES in every section,
identification/page labels on every page, no floating shapes and no table width
overflow. Reopening/inspection leaves saved bytes unchanged. Native Word counts
1,890 words against the frozen 1,300–1,600-word request. Visual review also finds
a largely empty fourth page and dense table wrapping. These are explicit live
quality failures; the artifact is evidence/sample output, not an accepted final
report. No manual rewrite or further model rerun hides them. The original
Desktop/report.docx remains unchanged and owned Word/bridge processes release.

Earlier native failures are retained separately: single-column spacing COM
rejection, continuous-header linking failures, regenerated drawing bookkeeping,
empty-header verification and slow repeated capture. These were product/harness
investigation results, not passes. Sandbox process/handle stalls and secondary
Windows RPC teardown diagnostics are environment evidence, separate from those
product failures. The stronger pre-existing-section fixture additionally exposed
dormant grid-pitch identity churn; its earlier failed XML records are retained.
An experimental grid setter was removed because it changed active settings.
The final identity correction is limited to no-grid pitch, with an active-grid
regression. A restricted-shell repeat of stdio read recovery stalled at worker
shutdown; the unchanged focused selection passes in an unrestricted shell.
One existing fixture assertion is corrected from INVALID_ARGUMENTS to the prior
read-recovery implementation's INVALID_OUTPUT for an unexpected ValueError; no
production taxonomy is changed. No full suite or local model is run.
