# Visual verification and useful rechecks

This change starts from local main `3a79fdb` on
`codex/visual-verification-recovery`.

Project build/test/inspection calls receive a fresh repetition allowance after
a settled exact text edit inside their project, or a whole-file write with
evidence of changed bytes (a known prior digest or a newly created file).
Failed, denied, unknown and unchanged writes, reads, and changes to another
project do not renew that allowance. Duplicate calls in one batch and repeated
checks without further progress retain their existing stops. Approvals and
overall operation/request budgets remain in force.

The inspector validates a bounded PNG and returns its dimensions and digest.
The runtime verifies that exact inspector-owned screenshot and supplies its
pixels to a vision-capable local model or the cloud Responses adapter after the
paired tool results. The image is marked as untrusted tool evidence, without
granting permissions or changing the user's request. Pixel data is transient;
durable tool receipts retain the path/digest. Text-only models receive an
explicit visual-verification limitation. Changed or redirected screenshots are
not admitted. Cloud image requests use native image parts and the existing
provider token-count admission; base64 is not counted as source text. Cloud
fallback cannot silently send an image-bearing request to a text-only model.

Browser-only `wait` steps support a selector becoming visible, hidden, attached
or detached, or an explicit delay, bounded to 15 seconds per step and the
existing overall inspection deadline. Use a readiness wait for an intro before
`in_view` on the affected section. The inspector checks the target after
application scroll handlers run and again at capture time. `model_loaded`
waits for a defined model-viewer with a loaded model. Bounded model readiness,
viewport evidence and current Vite error overlays appear in the receipt.
Readiness and successful automated checks do not establish correct 3D pixels;
visual status remains `requires_review`.

When fresh source proves a rejected patch is already present, recovery directs
the model to diagnose the remaining behavior using project checks and visual
evidence. No-change edits remain rejected, with their existing finite recovery
allowance. This does not change sampling, accepted profiles, routing, user
configuration or acceptance prompts.

## Verification

The necessary native regression run recorded **312 passed, one symlink skip,
and four existing failures** in 66.60 seconds. All four failures reproduced on
an untouched archive of local main: the catalog configuration assertion omits
`shell_run_enabled`, and three older local-image fixtures supply invalid
completion reviews. They were left unchanged. Sandbox-denied Windows pinned
file handles were separately resolved by running the relevant native tests
unrestricted; those denials are not product failures.

Coverage includes actual Chromium intro scroll locks, capture of the requested
section, failed model readiness, current Vite error overlays, screenshot bytes
in local native messages and real OpenAI SDK requests over a mock HTTP
transport, source recovery, process release, approvals, cross-project isolation,
and unchanged no-progress/duplicate-call stops. Reports are ignored under
`state/visual-recovery-*.xml`. After the screenshot validation and recovery
coverage refinements, the final affected run passed **93 tests**, with the
same single symlink skip, in 43.41 seconds. Across both scoped runs, **314
distinct tests passed**. Compilation and whitespace checks passed.

A read-only inspection of the website's existing `dist` also ran and released
its temporary server. Its automated readiness checks passed, but direct
screenshot review showed the branding surface without a visible 3D object.
This is evidence that readiness alone cannot establish visual correctness;
the existing build is not qualification of the latest website source. No
website source or dependencies were changed. Historical missing-package
captures are not treated as the current cause.

Full-suite, live provider inference and local GPU model gates were not run,
per the request for only necessary tests. No credential was used. The SDK
transport tests use synthetic credentials and mocked HTTP.
