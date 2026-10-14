# Hungarian interface wording, 14 October 2026

This pilot revises Hungarian only, on `codex/gui-language`. All 737 existing
entries were examined against the application code; 38 previously unmarked
status, count, elapsed-time and operation-review messages are now included, for 775 entries.
Other language catalogs and their existing wording are unchanged. No online
translation service was used for this revision.

The catalog is **editorially revised, with native-speaker approval pending**.
The editor was Codex, not an independent human translator. Compilation,
fingerprint checks and UI tests establish integrity and behavior; they do not
certify native fluency. The separate review record is
[`localization/hu-review.json`](localization/hu-review.json).

## Voice and terminology

Use concise, informal singular address (tegezés): “Add meg”, “Válaszd ki”,
“Próbáld újra”. Do not mix it with “Adja meg”, “Válassza ki” or “Ön”. Ordinary
buttons name an action: “Mentés”, “Bezárás”, “Alkalmaz”. When the assistant asks
permission to execute an operation, use a permission question such as
“Másolhatom a fájlt?” or “Futtathatom a parancsot?”. Error messages state what
happened and, where the source provides one, the next step.

| Concept | Hungarian | Meaning and constraints |
| --- | --- | --- |
| GUI language | Felület nyelve | Independent of the model's response language. |
| Response language | Válaszok nyelve | Applies to the next model response. |
| Skill | Képesség | A packaged assistant instruction set, not a personal talent or a plugin. |
| Agent speaker | Asszisztens | In runtime status, Agent means “Eszközhasználat”. |
| Reasoning | Gondolkodás | Reasoning level: “Gondolkodás szintje”. |
| Profile | Profil | Keep distinct from the application and its portable copies. |
| Runtime | Futtatókörnyezet | Never “futási idő”, which means duration. |
| Portable node | Hordozható példány | A complete runnable copy, not a network junction. Actual generated disk names remain literal. |
| Credential | Hozzáférési adat | API keys and access, refresh or login tokens. |
| API key | API-kulcs | Keep the acronym and use the Hungarian hyphen. |
| Recovery key | Helyreállítási kulcs | Can unlock the profile. Never imply a separate password-reset service. |
| Backup retention | Mentések megőrzése | Duration/number of retained backups; never a person's “korhatár”. |
| Managed backups | Az alkalmazás által kezelt biztonsági mentések | In the count field, “Megtartott mentések”. Independent backups are excluded. |
| Export outside profile | Exportálás a profilon kívülre | Creates a separate copy; does not export a different profile or remove the source. |
| Exact diff | A pontos módosítások | Shows proposed text changes, before execution. |
| Approval | Jóváhagyás | Permission to execute the displayed operation. |
| Review acknowledgement | Ellenőrzés befejezése | Does not execute, retry or certify an uncertain operation. |

After numerals Hungarian uses singular units: “2 képesség”, “21 hivatkozás”,
“30 nap”. Keep named placeholders intact; never translate paths, user-written
text, model names, identifiers, commands or literal `DELETE` confirmation text.
Translate the verb *enter* normally, but preserve the `Enter` keyboard key.
Avoid guessing whether a dynamic name takes “a” or “az”; rewrite the sentence
around a label or quotation instead of introducing “a(z)”.

## Context and editorial review

Hungarian TS entries include source locations and translator notes. Critical
notes explain backup zero values, exports outside protection, destructive
conversation resets, recovery-key invalidation, uncertain operations and
placeholders containing already translated phrases. Inspect full rendered
sentences, not isolated fragments. The interrupted-operation banner uses the
same accusative singular noun after every numeric count.

The `OrsiUIExtras` context marks only application-owned text previously inserted
as English literals: encryption status, skill/reference units, the source label,
the automatic response-language option, GPU acceleration, elapsed time and
operation-review details. Its Hungarian translations remain bound
during live switching. Other languages have no entries in this optional context,
so their existing English fallback is preserved. User data remains literal.

The maintenance tool validates complete coverage for an optional context once a
catalog contains it. `--update` preserves source locations, translator notes and
unfinished state. It does not opt other catalogs into the pilot context.

## Revision and review process

1. Read the English source and its call site to establish the action and actual
   effect. Rewrite directly in Hungarian using this guide.
2. Review complete screens and composed sentences with real counts and synthetic
   paths. Check login, settings, skill previews, images, backups and approvals.
3. Record source and translation fingerprints in the Hungarian review record.
   Compilation rejects a stale record; changing text requires a fresh editorial
   check and updated fingerprints. A matching fingerprint is not a fluency score.
4. A fluent/native reviewer should inspect tone, terminology and every warning
   in context. Record their identity, date and explicit approval separately.
   Until that happens the native-review status stays pending. Do not infer it
   from automated tests, generated translations or this editorial record.
5. Only after assessing the Hungarian pilot should this workflow be extended to
   other languages. Their current draft status is unchanged.

Use the repository's bundled Python:

```powershell
.\runtime\python\python.exe tools/ui_translations.py --language hu --update
.\runtime\python\python.exe tools/ui_translations.py --language hu --compile
```

After reviewing an edit, recompute the record's `entry_count`, `source_sha256`
and `translation_sha256` with `tools.ui_translations.review_fingerprints`.
Do not change native-review status to approved without an actual review; a later
copy edit invalidates that approval and must return it to pending.

Verification remains limited to essential deterministic and native UI checks.
No model/API calls, full-suite qualification or independent native-language
approval are part of this pilot.

## Pilot results

The final essential native run passed **71 checks in 26.61 seconds**, with no
failures, errors or skips. It covers catalog/source agreement, stale-review
detection, retained translator notes, unfinished-state handling, live switching,
literal data, numeric grammar, profile lock/unlock, compact fixed-width controls,
skill previews, elapsed time and unchanged approval decisions. Evidence is in
ignored `state/hungarian-essential.xml`. All other language catalogs compare
unchanged against starting commit `b87c29b`.

Of the original 737 Hungarian messages, 537 were rewritten and 200 retained after
examination. The 38 new messages bring the pilot to 775 entries. Thirty-one native
screen states were captured at wide and compact sizes, with representative
screens visually inspected. Button and checkbox caption measurements report no
remaining overflows in those states. Earlier clipped quota/lock buttons and the
review-acknowledgement sentence were shortened in Hungarian. No general layout
change was needed.

The isolated encrypted-profile preview initially encountered the sandbox's
Windows lease restriction; it completed with native file-lock access. Fixture
setup corrections are separate from product verification. The final native
screens, layout measurements and searchable before/after review page are under
ignored `state/hungarian-review/`. The feature remains on `codex/gui-language`;
other worktrees, user settings, model/API behavior and remote refs are unchanged.
