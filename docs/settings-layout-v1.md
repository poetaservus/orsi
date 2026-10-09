# Settings layout v1, 8 October 2026

This bounded GUI change starts from local main `9553722` on
`codex/settings-layout-v1`. The supplied settings mockup defines the presentation:
centered blue-grey panel, General/Skills/Image Generation navigation, close control,
label-and-description rows, dividers, compact selectors and an approval switch.
The panel fits the application's minimum window size and scrolls when needed.

Mode and local/cloud model selectors retain MainWindow's existing handlers, failure
reversion, worker switching and busy guards. Model details and the existing greeting
preference remain accessible under More settings. Skills and Image Generation route
to their existing managers. Image settings show an unavailable state when the
current mode lacks support; their button retains the existing busy guard.

Theme, GUI Language, Response Language and the global tool-approval toggle have no
existing configurable setting. They are explicitly disabled placeholders, with
Coming soon labels or an accessible placeholder description. No new permission,
language, theme, model, prompt, sampling, tool or context behavior is introduced.
No user runtime settings are migrated or overwritten.

Verification artifacts and synthetic renders are under ignored
`state/settings-v1-preview/`. Existing GUI-parent assertions were updated for the
new section hierarchy; acceptance prompts and runtime assertions are unchanged.

- Final focused regression: 82 tests and 5 subtests passed (33.46 seconds).
- New panel checks on Qt's native Windows backend: 4 tests passed (1.27 seconds).
- Synthetic renders inspected at 805 × 555 and 728 × 536, including both other
  sections. Placeholder boundaries, navigation, close/Escape, resize/scroll access,
  unchanged drafts/preferences, mode switching away and back, and image-settings
  persistence were checked without network or model requests.
- Compilation and whitespace checks passed.
- Initial sandboxed regression: 67 passed, 11 failed from Windows fixture access
  restrictions. Its unrestricted rerun passed all 78 existing focused tests and
  5 subtests; those sandbox failures are not treated as product failures.
- Full unrestricted regression with the offscreen Qt backend: 2,392 tests and
  15 subtests passed; 58 opt-in/host-dependent checks skipped (345.62 seconds).
  No failures or errors. The native Windows panel checks are recorded separately above.
- Live model/API gates were not run for this GUI-only change; opt-in and
  host-dependent skips remain separate from passed deterministic checks.

Local integration retains the previous main tip at
`archive/2026-10-08/main-before-settings-layout-v1`, fast-forwards main after
verification, and removes only this merged feature branch. Other worktrees and
remote refs are outside this change.

## Flat control fills, 9 October 2026

The follow-up on `codex/tool-approval-preferences` gives Preview, Install, the
GitHub/source input and the greeting input explicit solid charcoal fills.
Hover, pressed and disabled button states also use solid fills. The change is
limited to widget identities and settings styling; actions and persistence
retain their existing behavior.

The existing settings/skill-management checks passed **30 tests** in 27.67
seconds. Offscreen Qt renders at 1280 × 800 and 760 × 600 were inspected, with
uniform interior pixel samples confirming base, hover, pressed and disabled
fills. Synthetic renders and the verification script are under ignored
`state/flat-controls-preview/` and `state/flat-controls-preview.py`.
Compilation and whitespace checks passed. Live model/API gates are not run for
this styling change.

The full unrestricted Windows regression passed **2,753 tests and 15 subtests**,
with **58 optional/host skips**, no failures or errors, in 466.15 seconds.
Temporary state and caches are repository-local; the result is retained in
ignored `state/flat-controls-full.xml`. The styling follow-up remains on the
requested feature branch without advancing `main`.

### Installed skills list follow-up

The Installed skills list now shares the solid charcoal fill and neutral border
of the updated fields and actions. This adds only a widget identity and one
style selector. Existing focused settings/skill checks passed **30 tests** in
29.51 seconds. Empty, populated and disabled list renders at 1280 × 800 and
760 × 600 were inspected and their viewport fills verified as uniform. The
synthetic artifacts are under ignored `state/flat-installed-skills-preview/`.
Compilation and whitespace checks passed; live model/API gates are not run.

The first full run recorded 2,752 passed, 58 skips, 15 passed subtests, and one
unchanged Git-installer temporary-folder cleanup failure with a related teardown
error (501.56 seconds). All **60 installer tests passed unchanged** on a fresh
fixture recheck (19.38 seconds). Both results are retained separately in ignored
`state/flat-installed-skills-full.xml` and
`state/flat-installed-skills-git-recheck.xml`; no installer code or assertion
was changed for this styling task.

The final unrestricted full rerun passed **2,753 tests and 15 subtests**, with
**58 optional/host skips** and no failures or errors (528.04 seconds). Its
repository-local state/cache and separate result are retained under
`state/list-final`, `state/list-final-cache` and
`state/flat-installed-skills-full-final.xml`. This follow-up remains on the
feature branch; `main` is unchanged.

### Image Generation controls follow-up

The image model, size, quality and file format dropdowns, their popup lists,
and the Save image settings and Reset changes buttons now use solid charcoal
fills matching the other updated controls. Hover, pressed and disabled button
states also retain solid fills.

Three existing focused settings tests passed in 2.09 seconds. Offscreen renders
at 1280 × 800 and 760 × 600 were inspected; uniform interior pixel samples
verified 32 control states across both sizes. Artifacts are under ignored
`state/flat-image-controls-preview/` and `state/image-flat-focused.xml`.
The full suite was intentionally skipped at the user's request for this color
change. Live model/API gates were not run. The change stays on the requested
feature branch.
