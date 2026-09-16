# O.R.S.I roadmap

Updated: 2026-09-16

## Product direction

O.R.S.I is being developed as a local-first Windows assistant that remains useful for ordinary
conversation while gaining computer capabilities one bounded, auditable permission class at a
time. The application must keep a safe chat fallback throughout development.

## Delivered

### Conversation and inference foundation

- Local GGUF and OpenAI-compatible cloud inference paths.
- Text conversation persistence and a bounded model context.
- General conversation that does not invoke filesystem tools unnecessarily.
- In-memory-only cloud credentials and a safe chat fallback when agent startup fails.
- Cloud provider compatibility now supports configurable safe headers, optional strict tool metadata,
  optional `tool_choice`, provider naming in the selector, visible Cloud-mode failures without
  forced local fallback, and detailed provider-unavailable messages.

### Capability runtime foundation

- Strict capability contracts, registry, permission gate, cancellation path, bounded executor,
  and crash journal.
- Provider-native capability calls and a bounded agent loop.
- Deterministic tool routing, stable errors, and result round-tripping.

### Read-only filesystem milestones

- `filesystem.stat` for bounded metadata about one requested file or directory.
- `filesystem.list` for deterministic pages of directory entry names and coarse types.
- Portable-root scope by default, with an explicitly acknowledged full-local scope on supported
  Windows drives.
- Network paths, device namespaces, file contents, mutations, execution, and background search
  remain outside the granted authority.

### GUI v2 desktop baseline

- Dark v2 image-backed shell with a thin top instrumentation bar, top-left controls, and persistent
  version / execution mode / context-window status text.
- Centered transcript area with quiet assistant text, rounded user bubbles, code blocks, copy action,
  and retained stop/send states.
- Bottom composer pill matched to the v2 mockup, with Qt-native send button rendering and padded hover
  behavior after reverting the custom hover artifact.
- September 15 polish adds bundled Saira Regular typography, a smaller composer/input/send-button
  scale, clearer placeholder contrast, slimmer/darker user bubbles, and an invisible bottom blur
  lens that softens transcript text behind the composer without drawing a visible panel.
- Responsive wide and compact layouts, with focused UI coverage and rendered previews for the
  composer, hover states, typography, blur, and user-bubble refinements.

### Natural-language resolver and planner loop

- Planner-first capability loop restored so natural-language file/folder requests can progress through
  capability calls instead of collapsing into chat-only disclaimers.
- Active filesystem targets are retained for follow-ups such as listing a previously found folder,
  confirming an action, or fixing a previously read file.
- Bounded filename disambiguation handles exact-name/stem/extension variants inside the requested
  directory only; it does not fuzzy-match, recurse, index, or search the whole host.
- Manual resolver/planner acceptance is complete for the five `ORSI_TEST` workflows: named Desktop
  folder listing, `there` follow-up listing, creating a folder inside the named Desktop folder,
  creating a folder directly on Desktop, and reading the extensionless `atiflix css` request as the
  exact same-folder text file.

## Current release lane

The active development line is `codex/phase-9-target-resolver`. It carries the accepted Phase 10
mutation checkpoints, Phase 9 search, the target resolver, the planner-loop repair, bounded filename
disambiguation, GUI v2 polish, accepted manual resolver-workflow hardening, and the first cloud
provider-compatibility pass. The branch is
published to GitHub and tracks `origin/codex/phase-9-target-resolver`. It is still a development
line: it is not merged, release-promoted, or ready to change the version beyond `v0.4.0-dev` until
fresh-runtime packaging and release gates are closed.

## Next milestones

1. Run a fresh-runtime packaging check and packaged GUI smoke check before any release promotion.
2. Stabilize cloud-side provider profiles for OpenAI-compatible APIs before adding native
   non-OpenAI adapter families.
3. Keep `v0.4.0-dev` until packaging/release evidence is recorded and the next version milestone is
   explicitly approved.
4. Improve interruption behavior and malformed conversation recovery after the current branch is
   accepted.

## Release rule

No new capability is enabled by default merely because its implementation exists. Each capability
must pass its focused policy, failure, cancellation, lifecycle, integration, and manual UI checks
before it can enter the default product path.
