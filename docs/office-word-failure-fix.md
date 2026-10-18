# Word guidance and regression fixtures, 18 October 2026

This bounded fix starts from clean local main `6ece427` on
`codex/word-failure-fix`. It addresses the three Word failures recorded in the
[deep test audit](deep-test-audit-2026-10-18.md).

The compose description again explains usable column width, the default 170 mm
body, table/image fit and header/footer distances below their corresponding
margins. Existing authoring-read, correction, approval, recovery and separate-save
requirements remain explicit. Native validation and execution are unchanged.

The text-control regression previously submitted historical `pages` to the live
`sections` schema, so its negative cases could pass on the wrong envelope error.
It now first validates a clean current plan, then checks the precise pattern
rejection for header, footer, paragraph and table-cell text. Existing numeric
bounds remain asserted. The break-only regression retains schema/provider
refusals and checks the actual complete-replacement warning instead of obsolete
uppercase wording.

The correction fixture previously exhausted its three scripted responses when
the finalization guard requested missing review/save evidence. It now returns
honest unverified workflow evidence and handles that reminder. Assertions prove
one corrected dispatch, one approval, retained success evidence and an explicit
incomplete outcome; identical invalid retries still stop without dispatch or
approval. Separate existing completion cases verify that reviewed/saved work can
complete and that unverified work or a failed closing response cannot.

Only focused checks ran: the original selection reproduced three failures and
one pass; the final selection passes **8 tests**, with zero failures or skips.
Six in-memory mutations were detected: removal of each of the four text patterns,
missing layout guidance and bypass of Word finalization. These checks changed no
repository source on disk. Evidence is under ignored `state/word-failure-fix/`:
`baseline.xml`, `final.xml`, `value-proof.json` and `office-contract.json`.

The offline Office contract verifier passes with the accepted manifest unchanged.
The largest projection is 22,493 bytes / 8,026 reserve tokens, within the existing
22,500 / 8,100 ceilings. No budget increase is made.

No full suite, native Word gate or live-model acceptance was run for this
description/fixture fix. The earlier localization/routing findings and the two
unexplained native failures remain unresolved here; this focused pass does not
qualify the wider suite. User documents and settings are untouched.

Prior main is preserved at
`archive/2026-10-18/main-before-word-failure-fix`. Integrate by fast-forwarding local
main and removing only this merged feature branch; no remote operation is made.
