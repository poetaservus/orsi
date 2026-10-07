# 00 — Working contract and Python foundations

Read for new work or when the environment and acceptance criteria are unclear.

## Inspect before choosing

Locate the entry point and the smallest source path relevant to the request. Read
nearby tests and repository instructions. Check `pyproject.toml`, lockfiles,
requirements, CI and the interpreter used by the actual launch command. A system
`python` may differ from a bundled runtime or activated environment. Establish:

- supported Python versions and platforms, not just the development machine;
- installed dependencies, optional features and external services;
- observed versus requested behavior, plus input/output examples;
- important compatibility promises and data/settings to preserve;
- the project's existing validation commands.

For a bug, use a minimal reproduction and retain the acceptance input unchanged.
For a new feature, derive a few observable completion criteria from the user
request. Do not turn an unspecified aesthetic or implementation choice into a
hard requirement. For review-only requests, inspect and report; implementation
should follow the user's authorized scope.

## Define the boundaries

For a function, specify accepted input shapes, output, mutation, exceptions and
empty cases. For an application, specify startup, main interactions, persistence,
failure recovery and shutdown. If a service provides a real-world capability,
separate a successful request from a completed effect. A timeout can leave the
external result unknown; avoid claiming failure proves nothing happened.

Preserve existing public APIs and stored formats unless migration is requested.
If a schema change is necessary, define compatibility and recovery before writing
new data. Changes to working user settings need preservation, not a guessed reset.

## Use Python deliberately

Prefer readable control flow over dense cleverness. Use the standard library when
it meets the requirement without fragile reimplementation. Use `pathlib` for
convenient path composition; existing valid `os.path` usage does not require a
migration. Comprehensions fit simple transformations; loops fit branching and
side effects. Choose generators for genuinely streamed data, not by reflex.

Avoid mutable defaults and accidental shared class state. Understand iterator
consumption, shallow copies and aliasing before changing collections. Make units,
time zones, encodings and ordering explicit when they affect the result. Use a
monotonic clock for durations/deadlines and timezone-aware timestamps for events.
Do not use binary floats for exact monetary invariants; preserve a suitable
existing decimal/integer representation.

## Compatibility is a contract

Do not upgrade the Python floor merely to shorten syntax. Built-in collection
annotations require Python 3.9+, union `X | None` requires 3.10+, and
`asyncio.TaskGroup`/`asyncio.timeout` require 3.11+. Choose compatible alternatives
or an explicitly accepted upgrade. Feature availability is distinct from whether
the target dependencies and distribution support it.

Avoid import-time file writes, network calls and process startup. Keep reusable
modules importable; put application startup behind an explicit entry point.
Configuration is loaded at a deliberate boundary with defined precedence and
validation, not scattered through business logic.

## Decision rule

Fix the actual requirement with the smallest coherent change. If an assumption
affects interoperability, data loss or external behavior, expose it. Otherwise
choose a practical default and continue. Ask the user about product decisions,
not routine variable names, file splitting or testing mechanics.

For architecture read [10](10-architecture.md); for external inputs read
[20](20-types-and-contracts.md); for final delivery read [95](95-review.md).
