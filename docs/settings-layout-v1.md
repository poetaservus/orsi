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
