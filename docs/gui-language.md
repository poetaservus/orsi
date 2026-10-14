# GUI language, 14 October 2026

Settings → Appearance → GUI Language offers Auto (system language) and the same
45 named languages as Response Language. English remains the default for missing
preferences. Auto matches the system's preferred UI languages against supported
codes, with `no` mapped to Bokmål and English as the final fallback. Native
language names remain visible in the picker. The selected code is independent
of Response Language and never becomes a model instruction.

Changes apply to existing app-owned controls immediately. Settings, profile and
login screens, question-form chrome, approval headings, tooltips, accessibility
text, notification copy and app-owned dialogs use bundled offline translations.
Drafts, cursor positions, selected options, pending approvals and unsaved image
settings keep their values. Long navigation labels wrap; image actions stack in
compact layouts. Windows dialog chrome follows the OS where native dialogs are
used. Detailed external/provider diagnostics, model/skill names and descriptions,
literal previews, paths, code, user greetings, question content and conversation
text remain literal. Conversation-owned notices retain Response Language policy.

## Preferences and lifecycle

`state/gui_language_v1.json` stores only `schema_version: 1` and `language_code`.
The store is adjacent to the active UI-preferences store, using the same profile
session and encrypted storage authority. Legacy unprofiled preferences stay in
ignored installation state. Reading a missing preference does not write a
default. A language catalog is loaded before saving; failed catalog loads or
saves leave the prior effective selection intact. Corrupt or unsupported saved
records remain preserved, with an English fallback and visible feedback.

Profile lock revokes the setting's store and clears its selection. A separate
public `login_language_v1.json` beside the profile bootstrap stores only a schema
version and a bounded mapping of public profile UUIDs to language codes. It
contains no profile paths, secrets, conversation/file contents or font assets.
It restores login wording before unlock without opening protected storage.
Corrupt public records remain preserved and never obstruct lock or unlock.
Profile switching, restart and portable copies restore the private preference.

## Translation maintenance

`app/ui/localization.py` owns one application-level Qt translator. Only explicitly
marked `UiText` values participate in live retranslation; ordinary strings are
never looked up just because they resemble interface text. Bindings retain the
English template and its parameters, and signal blocking prevents relabeling
from changing selections or writing settings. Clearing a widget also discards
its text binding. Settings/profile navigation uses stable section identities;
image preferences save item data rather than translated display labels.

The versioned `.ts` sources and compiled `.qm` catalogs live in
`app/ui/translations/`. Both Python packages and portable exports include them.
There are 737 shared source entries per catalog, including common Qt context-menu
and dialog actions. The Hungarian editorial pilot adds 38 messages in an optional
context; other catalogs retain their current wording. No translation network request occurs in the application or
the offline maintenance tool.

Use the bundled Python to run `tools/ui_translations.py --update` after changing
interface copy. This retains existing translations and marks new human-readable
copy unfinished. Complete/review the sources, then run
`tools/ui_translations.py --compile`. Validation rejects missing entries, duplicate
keys, changed placeholders and changed literal terms such as `DELETE`, `API`,
`JSON` and filenames. The essential catalog test also checks every compiled
translation against its source, so stale bundled catalogs fail verification.

English is the source language. The other 44 catalogs started as development-time
machine drafts of public interface copy. Nynorsk and Montenegrin were adapted
from Bokmål and Bosnian drafts respectively; selected core labels were revised.
Core Hungarian/Dutch labels and approval/deletion wording were also revised.
Native-language review of all draft catalogs, terminology and number agreement
remains outstanding. These are functional language choices, not a claim of
native-reviewed translation quality.

Hungarian has since received a complete contextual editorial revision. Its tone,
terminology, review status and maintenance process are recorded in
[the Hungarian pilot](hungarian-ui.md). That revision has not been applied to
other languages. Use `--language hu` to compile/update only Hungarian; compiling
it checks the separate editorial fingerprints without claiming native approval.

## Verification and branch

Work starts from clean local main `7ba2278` on `codex/gui-language`. Per the user's
request, verification is limited to essential deterministic and native GUI
checks; the feature remains on its own branch for review. No model/API live
gates or full-suite qualification are claimed. Accepted prompts, model profiles,
sampling, context, routing, tools and approval decisions are unchanged.

The first essential native run recorded 152 passed and one failure in 116.61
seconds, with no errors or skips. The failing saved-off native-write check also
fails identically in isolation on an untouched archive of starting main; its
two-second `entered.wait` assertion and acceptance prompt were not changed.
Evidence is under ignored `state/gui-language-essential-native.xml`,
`state/gui-language-write-recheck.xml` and `state/gui-language-write-baseline.xml`.

The final affected native run passes all 96 checks in 38.78 seconds, with no
failures, errors or skips (`state/gui-language-final.xml`). It covers all 45
catalogs and every compiled entry, real switches away/back, system-language
selection, save/catalog failures, unchanged drafts and response preference,
pending forms/approvals, enum persistence, content-free login caching, encrypted
profile switch/lock/cold restart, compact layouts, translated tooltips, skill
selection/removal, copy actions and portable source/compiled catalog inclusion.
Compilation and whitespace checks pass. The earlier 153-check run is not labeled
fully passing; the unchanged baseline write-timing failure remains separate.

Off-screen rendering lacks some system font fallbacks and reproduces the existing
custom-login-font failure on main. Native Windows rendering resolves Armenian,
Georgian and custom system fonts. Compact Armenian/Georgian layouts pass in
Original and Conformist. Native previews also cover Hungarian, Dutch and Russian,
under ignored `state/gui-language-preview/`. Ref/worktree inventories are retained
under `state/backups/gui-language-20261014/`. Other worktrees and remote refs remain
unchanged.
