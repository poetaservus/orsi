# O.R.S.I roadmap

Updated: 2026-08-15

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

### Approved desktop GUI baseline

- Dark image-backed shell with a fixed left rail and an opaque centered conversation panel.
- Main-chat context-window meter and retained settings popover.
- Centered compact composer, assistant responses, user bubbles, code blocks, copy action, and
  stop/send states.
- Responsive wide and compact layouts, including centered headers and balanced message padding in
  small windows.
- Automated geometry and behavior coverage plus native Windows visual checks.

## Current release lane

The approved GUI is integrated with the current read-only filesystem build and is ready for review
as the default interface. The integration must retain the capability gates, permission boundaries,
and chat fallback already in place.

## Next milestones

1. Merge and smoke-test the approved GUI integration on the main development line.
2. Improve interruption behavior for in-progress local generation and blocking cloud requests.
3. Add safe recovery for malformed conversation state and decide whether stored messages should be
   replayed visually on launch.
4. Design `filesystem.read` as the next separately gated capability, with strict content, size,
   encoding, path, and cloud-disclosure limits.
5. Add mutating filesystem and process capabilities only after their permission, confirmation,
   audit, recovery, and cancellation contracts pass independently.

## Release rule

No new capability is enabled by default merely because its implementation exists. Each capability
must pass its focused policy, failure, cancellation, lifecycle, integration, and manual UI checks
before it can enter the default product path.
