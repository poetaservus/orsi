# Larger settings with embedded tabs, 8 October 2026

GUI-only change from local main `009510e` on `codex/settings-embedded-tabs`.
The settings panel grows from 886 × 611 to a preferred 1120 × 740 logical
pixels, with 34-pixel title, 20-pixel navigation/section headings, 18-pixel
setting names and 14-pixel descriptions/controls. It uses an antialiased
rounded gradient and border. Smaller application windows constrain its size
and scroll page content; the top-edge drag strip, close-button separation and
existing cog/close animations remain available.

The navigation now contains five tabs:

- General: the existing greeting preference, response-language and approval
  placeholders, future notifications and the existing readiness status.
- Models: existing mode and local/cloud model selectors, with effective model
  details. Selectors retain their original switch handlers and busy guards.
- Skills: embedded source selection, review, installation, installed list and
  confirmed removal through the existing worker/service transaction.
- Image Generation: embedded image model, size, quality and format selectors,
  with Save image settings and Reset changes. The existing handler persists
  choices. Unsupported sessions disable controls and explain availability.
- Appearance: theme and interface-language placeholders, plus future text size,
  reduced motion and high contrast.

Transparent background is another future image preference. Every future control
is disabled, marked Coming soon, and has an accessible placeholder description.
No backend setting is created for a placeholder. Runtime settings, inference,
accepted profiles, routing, prompts, sampling, context and tool policy are outside
this change.

Skill and image preferences stay in their tabs without opening another settings
window. Switching tabs or hiding Settings preserves pending changes and previews.
Skills refresh the existing message picker after installation/removal. While an
embedded skill worker owns an operation, conflicting send/session/model actions
are disabled. Application close waits for completion and joins that owned worker
before service shutdown. A hidden panel can finish its operation safely. Existing
standalone dialog interfaces remain compatibility shells around the shared pages.

## Verification

- Expanded focused regression: 88 tests and five subtests passed in 52.61 seconds.
- Final native Windows GUI/skills/frame group: 60 tests and 15 subtests passed in
  43.79 seconds. It includes compact preview geometry after the long-source fix.
- Synthetic visuals inspected at normal and 2× display scaling, including all
  five sections, expanded skill preview and scrolled compact 760 × 600 layout.
  Render/test services use isolated stores and make no inference requests.
- Compilation, dependency consistency and whitespace checks passed.
- Full unrestricted native Windows regression: 2,398 tests and 15 subtests
  passed in 334.09 seconds, with no failures/errors. The 58 skipped opt-in live
  model/cloud and host-dependent symlink gates remain separate from passed tests.
- Live model/API gates are separate and were not run for this GUI-only work.

Ignored verification artifacts live under `state/settings-embedded-preview/`,
`state/pytest-embedded-native.xml` and `state/pytest-settings-embedded-full.xml`.
Local integration preserves prior main at
`archive/2026-10-08/main-before-settings-embedded-tabs`, fast-forwards main after
verification, and removes only this merged feature branch. Other worktrees and
remote refs remain outside the operation.
