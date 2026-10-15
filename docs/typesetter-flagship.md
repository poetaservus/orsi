# Typesetter Flagship: research and package

Research date: 16 October 2026. Starting local main: `0dfe35b`.
Bounded branch: `codex/typesetter-flagship`.

## Result and scope

`skills/typesetter-flagship` is an optional MIT instruction package for Word
document creation, editing, typesetting, preservation, and visual review. It
uses the user's frontend-flagship and analyst-flagship architecture: priority
order, three dials, a document contract, focused references, and bounded review.
It does not install itself, modify prompts/routing/model settings, or extend
the Word connector. Runtime preferences and installed user skills are preserved.

## Research comparison

The comparison inspected primary repository source and actual license files,
not registry descriptions alone. Revisions and links are retained in the
package's [sources and license](../skills/typesetter-flagship/references/99-sources-and-license.md).
This is a source inspection, not a performance benchmark of upstream engines.

| Candidate | Verified status at inspected revision | Useful contribution | Adoption decision |
| --- | --- | --- | --- |
| [MiniMax minimax-docx](https://github.com/MiniMax-AI/skills/tree/60aaae52bb2af8162732751a4332f62a5fef518b/skills/minimax-docx) | MIT skill license | Create/edit/template separation, typography and validation references | Synthesize decisions; do not require its .NET engine or fixed recipes |
| [office-docx](https://github.com/arih04x/office-skills/tree/0fb34f48e26eb934b1cdd012b8d080b1e2105087/office-docx) | MIT repository license | Semantic structures, style/template dependencies, structural and rendered checks | Keep principles; strengthen split-run preservation and capability checks |
| [BrandDocs brand-docx](https://github.com/ferdinandobons/brand-docs/tree/97a6e384cb0664cd44ba8113c0b80c9761700670/skills/brand-docx) | MIT repository license | Template shell and role preservation, preflight, graded QA evidence | Use preservation approach; no compulsory permanent brand-profile system |
| [Anthropic docx](https://github.com/anthropics/skills/blob/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/docx/LICENSE.txt) | Proprietary source-available license | Commonly cited baseline, but not a permissive source | Exclude copied/adapted material |
| [Neko-Yukari docx-design-skill](https://github.com/Neko-Yukari/docx-design-skill/tree/e652ada3f79fe1a375a03a46c6f405d9229b294e) | README claims MIT; LICENSE absent from inspected tree | Advertises Python design themes, formula and language handling | Exclude reuse pending verified terms/provenance |

The current `openai/skills` tree was also checked at
`49f948faa9258a0c61caceaf225e179651397431`: the historically cited
`skills/.curated/doc` package was absent. Third-party mirrors were not treated
as an authoritative current OpenAI package or incorporated into this skill.

## Design decisions

The three dials are `design_variance`, `editorial_depth`, and `visual_density`.
Separating editorial depth from design freedom prevents a visual redesign from
silently becoming a rewrite. The priority order puts truth, preservation, and
editability ahead of visual novelty. The entry point remains useful without
loading all references; each technical decision routes to a focused document.

Anti-slop addresses generic blue headings, excessive bullets/bold, boilerplate,
invented exhibits, and weak hierarchy. Anti-premium-slop addresses reflex dark
and gold covers, ornamental counters, oversized type with tiny gray body detail,
empty divider pages, repeated callouts, fake authority labels, and slide-like
page stacks. The positive guidance permits expressive typography, vivid color,
images, and unusual composition when they serve the actual brief. It does not
impose monochrome minimalism, font bans, page-density percentages, or fixed themes.

The technical guidance covers semantic styles, direct-format overrides, actual
lists/tables/fields, split-run editing, section and header linkage, pagination,
language coverage, accessibility, template fidelity, and real saved-artifact QA.
Evidence categories distinguish structural validation, content readback,
rendered layout, evaluated fields, and persistence.

## Actual Orsi capability boundary

The inspected live Word connector supports bounded replacement, insertion
within a paragraph, five discovered paragraph styles, existing qualified table
text replacement, and separate saving. It does not expose a complete page
layout or document-generation engine. `apply_style` preserves direct formatting;
`insert_after` does not create paragraphs; `edit_table` does not create tables
or alter geometry. The skill makes these limits explicit and requires checking
current tools before promising fonts, sections, headers, figures, or rendering.

A future independently permitted file-generation route can implement broader
typesetting, but the instruction package does not create that capability or
bypass live-host guards. This avoids claiming a finished designed document from
a partial text/style patch.

## Packaging and evaluation

The portable package consists only of `SKILL.md` and twelve Markdown references,
including import-retained license notices and eight fixed behavioral briefs.
There are no scripts/assets/dependencies requiring unsupported package features.
Import the directory through Orsi's existing skill import workflow; import does
not require copying another flagship package or changing runtime settings.

Checks must establish frontmatter, local links, package budgets, native isolated
installation, complete reference retrieval/continuation, and the existing
regression suite. Behavioral briefs cover compact decision work, formatting
preservation, expressive design, multi-page tables, templates/fields, revisions,
limited live tools, and absent renderers. They require actual host/model artifact
runs before behavioral quality can be claimed.

## Verification record

- Skill-creator frontmatter/name/scaffold validation passed.
- Local package links and Orsi limits passed: entry point **8,533 bytes**;
  **12 references, 39,131 bytes combined**, each below 16 KiB.
- Isolated native Windows installation and idempotent reimport passed. All
  references round-tripped byte-for-byte through **84 bounded pages**, using
  512-byte/12-line reads. Actual installed user skills were not changed.
- The affected parser/package/import/reader/conversation/Python-package selection
  passed **249 tests in 22.13 seconds**, without skips or failures. Both package
  and test checks used workspace-local temporary storage and unrestricted native
  Windows handle access.
- The first focused invocation named a nonexistent test module and collected
  no tests. Its invocation error remains recorded separately; the corrected
  selection above is the passing result.
- The existing full suite on Qt's Windows backend and a fresh repository-local
  `--basetemp` completed with **4,226 passed, 48 failed, 67 skipped**, and
  **15 passing subtests**, in **1,605.49 seconds**. It is **not a clean full run**.
  Two existing test-only Qt activation deprecation warnings remain.

The full-run failures are:

- **47 baseline translation coverage failures**: 45 catalog cases and two
  Hungarian review cases. The English isolated probe reproduces
  `Translation coverage differs: en/OrsiUI`; source-set comparison identifies
  missing `Edit`, with no extra source strings. Application, tools, tests,
  configuration, and project metadata are byte-equivalent to starting `main`
  in Git. The validator reads those application sources, not the new Markdown
  package. This unrelated catalog repair is outside the bounded change.
- **One installer CLI I/O failure**:
  `test_cli_and_main_import_no_inference_ui_or_startup_in_fresh_process`.
  It passed unchanged in its isolated recheck (**1 passed in 0.58 seconds**).
  The intervening installer-module recheck recorded **58 passed, 2 failed**;
  its failing preview and portable-launcher cases then passed unchanged together
  (**2 passed in 1.11 seconds**). All use synthetic single-file frontend fixtures,
  not Typesetter. The intermittent I/O cause remains unresolved; these rechecks
  do not convert the original full run into a pass.

The **67 skips** are separate evidence: **59 opt-in provider/model/Office/UI
gates** and **8 unavailable symbolic-link cases**. No skipped live gate is
claimed passed. Full-run and isolated-recheck logs/XML are retained separately.

The portable ZIP was checked against all 13 source files byte-for-byte. Unzip
`state/artifacts/typesetter-flagship-1.0.0.zip`, then import its contained directory;
direct ZIP import is not claimed. Evidence is retained under ignored
`state/backups/typesetter-flagship-20261016/` and `state/typesetter-flagship-*.log/xml`.

Live provider/model document generation, actual Word visual output, field
refresh, and accessibility checker runs were **not performed**. The eight
behavioral briefs are evaluation specifications, not passing behavioral results.

## Local integration and recovery

Prior main is preserved at `archive/2026-10-16/main-before-typesetter-flagship`.
After the package checks and recorded regression, commit this bounded Markdown
change, fast-forward local main, and remove only its merged feature branch.
Keep all other worktrees, historical/unmerged refs, installed skills, and remote
branches unchanged. No remote publication is part of this request.
