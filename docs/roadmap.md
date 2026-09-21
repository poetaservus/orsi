# O.R.S.I roadmap

Updated: 2026-09-21

## Product direction

O.R.S.I remains a local-first Windows assistant that supports ordinary conversation and adds
computer capabilities through strict schemas, deterministic policy, explicit approvals, bounded
execution, and an auditable lifecycle. A safe chat fallback must remain available when capability
startup fails.

## Delivered

- Local GGUF/llama-server and OpenAI-compatible cloud inference behind a shared interface.
- Model-first native tool selection with a constrained fallback for providers without native calls.
- A bounded sequential agent loop with cancellation, protocol repair, result feedback, and context
  limits.
- One validated capability registry and production catalog.
- Read-only metadata, exact-name find, directory listing, bounded text read, and literal text search.
- Exact approval-controlled folder creation, text writing, copying, moving, Recycle-Bin trashing,
  and allowlisted application launch.
- Portable-root read access and per-launch acknowledged full-local read access.
- Separate permission, write-policy, execution, native-platform, crash-journal, settings, startup,
  inference, conversation, and GUI boundaries.
- GUI v2 with unchanged visual design, extracted approval and worker components, local/cloud
  selection, context status, stop controls, and cloud/privacy disclosures.
- Removal of the unreachable legacy regex resolver. Production routing is now schema-driven; only a
  narrow same-folder extension/name recovery remains.
- Current deterministic validation: 575 passed, 17 opt-in live tests skipped. The bundled-model
  filesystem-stat smoke and the real-model off-screen GUI workflow also pass when explicitly run.

## Next milestones

1. Run a fresh portable-runtime build and visible packaged GUI smoke check before release promotion.
2. Manually accept `application.launch` on a host with a standard Blender installation.
3. Add preserve-and-recover behavior for malformed conversation JSON without overwriting evidence.
4. Improve backend cancellation where the provider exposes a reliable abort primitive.
5. Add provider profiles for additional OpenAI-compatible APIs before introducing unrelated native
   provider families.
6. Split remaining large modules only when a feature or maintenance change exposes a coherent
   boundary; avoid abstraction added solely to reduce line counts.

## Release rule

The version remains `v0.4.0-dev` until packaging and manual release gates are explicitly accepted.
No new capability is enabled merely because an implementation exists. Every capability must retain
schema, denial, authorization, approval, execution, cancellation, recovery, integration, and
appropriate manual-UI evidence before release.
