# Conformist

Select **Settings → Appearance → Theme → Conformist**.

Conformist is the familiar dark AI-chat look: a flat `#171717` background,
charcoal `#262626` composer and controls, `#303030` user bubbles, soft white text,
and one `#3b82f6` blue accent. Composer, bubble and settings gradient stops use
identical opaque colors, with a transparent composer highlight, so the surfaces
remain flat. The existing rounding, layout and animations are retained.

The unmodified DM Sans variable font is bundled from the official
[Google Fonts repository](https://github.com/google/fonts/tree/5b35b7208dd4100571326fdf37f030b32a524232/ofl/dmsans).
Qt identifies its optical family as **DM Sans 14pt**. It loads from memory without
an OS font installation or internet connection. Code keeps its existing font
and syntax palette.

The [Lucide outline icons](https://github.com/lucide-icons/lucide/tree/dab294f313897bacaa968b725b3259fa37c17bd1/icons)
use a consistent neutral stroke. New message uses square-pen, Settings uses
sliders, attachments use a paperclip, and Send uses a white upward arrow on a
flat blue rounded square. Stop, microphone, folder, copy and check share the set.
Icon hit targets, enabled/disabled state and actions remain unchanged.

The full DM Sans OFL and Lucide/Feather notices are bundled with the assets and
travel with exported/imported themes through the optional `licenses` manifest
array. **Export current theme…** creates an editable `my-conformist` copy. Public
portable exports and Python package data include the manifest, font, icons and
licenses. Pinned upstream revisions, source URLs and hashes are recorded in
`app/ui/assets/themes/conformist/SOURCES.md`.

## Essential verification, 14 October 2026

`codex/conformist-theme` starts from clean main `356482e`. The user's saved theme
choice and other preferences remain untouched. The theme is added as an option
available to every profile; missing bundled assets leave Original/Ocean available.

Final native Windows verification passed **124 tests**, with no failures, errors
or skips, in **44.32 seconds**, using repository-local temporary storage and an
unrestricted shell for real Windows handles. The focused set covers Conformist,
the theme system, export/import and licenses, portable packaging, settings,
question/composer presentation, inline approvals and notifications. DM Sans
wrapping was checked at 760 × 600 and 1280 × 900, including a real switch away
and back and released application-font ownership. Compilation and Git whitespace
checks passed. Native chat/Appearance previews were visually inspected.

Evidence is retained in ignored `state/conformist-verified.xml` and
`state/conformist-preview/`. All displayed content and test profiles are synthetic.
No provider credential was read or used. The full repository suite and live
inference gates were not run under the user's standing essential-test scope.

An earlier visual investigation mistook syntax-colored code under the existing
composer blur for background leakage. The final implementation leaves the blur
and all response/animation code unchanged; tests verify that live transcript
blur still responds to content. An initial blur test needed Qt's queued layout
and viewport updates to settle; the earlier failing results are retained in
`state/conformist-essential.xml` and `state/conformist-paint.xml`.
After normalizing one upstream OFL trailing space without changing its wording,
all **10 export/portable-package checks passed** again in **20.00 seconds**;
results are retained in `state/conformist-license-final.xml`.

Pre-integration refs/worktree inventories are retained under ignored
`state/backups/conformist-theme-20261014/`; prior main is preserved as
`archive/2026-10-14/main-before-conformist-theme`. Commit, fast-forward local main
and remove only the merged feature branch. Other worktrees, historical/unmerged
tips, private runtime state and remote refs remain intact. No remote publication
is part of this task.
