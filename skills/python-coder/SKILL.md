---
name: python-coder
description: >
  Design, implement, debug, refactor, test, and review Python scripts, packages,
  command-line tools, services, and desktop applications. Use for substantive
  Python coding work, typing, pytest, asyncio, packaging, data integrity, and
  performance problems. Routes to focused references for the task and existing
  stack. Do not activate for merely running a command, prompt refinement, or
  unrelated frontend design.
license: CC-BY-SA-4.0
metadata:
  version: "1.0.0"
  author: O.R.S.I.
---

# Python Coder — O.R.S.I. Flagship

Deliver Python that works in the user's actual environment, remains understandable,
and behaves correctly when inputs, dependencies, or operations fail. Complete the
requested work; code that merely resembles a solution is not enough.

## Priority order

1. User intent, repository instructions, and existing behavior to preserve.
2. Correctness, data integrity, and explicit input/output contracts.
3. Compatibility with the supported Python versions, platforms, and dependencies.
4. Reliability, resource ownership, and meaningful verification.
5. Clear interfaces and maintainable implementation.
6. Measured performance where the task needs it.

Runtime permissions and core instructions remain binding. This package supplies
guidance, not executable tools or permission to install, publish, or mutate data.

## Establish the working contract

Inspect the relevant source, tests, configuration, dependency files and launch
path before editing. Identify the actual interpreter and Python floor; the
project's environment, formatter, type checker and test commands; the requested
outcome; and what must remain compatible. Use the existing stack unless the task
calls for a change. Do not impose uv, async, a web framework, strict typing or a
multi-layer architecture on every request.

For a clear task, proceed. Ask only about a missing decision that materially
changes the result. Choose routine implementation details yourself. Keep changes
bounded, preserve user data/settings, and separate requirements from assumptions.

## Read references progressively

Start with the most relevant reference. Load additional documents only when a
specific decision needs them; do not read the entire package by default.

| Task or decision | Read |
| --- | --- |
| Substantial new work, uncertain contract, compatibility | [00-foundations](references/00-foundations.md) |
| Architecture, module boundaries, legacy refactoring | [10-architecture](references/10-architecture.md) |
| Domain models, public interfaces, input validation, typing | [20-types-and-contracts](references/20-types-and-contracts.md) |
| Exceptions, files, transactions, cleanup, retry behavior | [30-errors-and-resources](references/30-errors-and-resources.md) |
| Regression, pytest, fixtures, mocks, behavioral tests | [40-testing](references/40-testing.md) |
| Concurrency, asyncio, background workers, cancellation | [50-concurrency](references/50-concurrency.md) |
| Dependency environment, pyproject, distribution | [60-packaging-and-tooling](references/60-packaging-and-tooling.md) |
| Untrusted input, subprocesses, storage, credentials | [70-security-and-data](references/70-security-and-data.md) |
| Slow code, excessive memory, unstable timing | [80-performance-and-debugging](references/80-performance-and-debugging.md) |
| CLI, API, PyQt/PySide, runnable application delivery | [90-applications](references/90-applications.md) |
| Substantial implementation or review ready to finish | [95-review](references/95-review.md) |
| Source selection, adaptation decisions and licenses | [99-sources-and-license](references/99-sources-and-license.md) |

Examples: a small bug needs 80 and 40; a new package needs 00, 60 and 40;
a cancellation bug needs 50 and 40; a GUI application needs 90, then 30/50 as its
work requires; an API input boundary needs 20 and 70. Finish substantial work with
95. These are starting routes, not a demand to load everything in each row.

Use the host's reference reader when supplied. In O.R.S.I., request the exact
`references/...md` inventory path through `skill.read_reference`; use the returned
continuation offset if the required section is incomplete. On other hosts, read
the corresponding local file with available file tools. Do not guess unread
reference content. If unavailable, use this entry point for ordinary work and
identify the missing material only when the task depends on it. Never bypass the
reader boundary or claim a whole document was read from an incomplete excerpt.

## Implement the whole requested behavior

Use the simplest design that supports the contract. Keep core decisions testable
apart from files, network, clocks and UI when that separation has real value.
Annotate meaningful interfaces, validate external data, name failure outcomes,
and give resources a clear owner. Match syntax and APIs to the supported version.

Cover the normal path and relevant empty, invalid, error, repeated-action and
shutdown states. Preserve state on failure. For desktop and async applications,
keep the event loop responsive and stop owned work predictably. For external
operations, bound time and concurrency and retry only with safe semantics.

Do not leave requested functionality as stubs, fake responses, TODOs or pseudocode.
Do not invent packages or APIs. Check installed versions or primary documentation
when compatibility is uncertain. Dependencies need a concrete benefit, compatible
license/version, and a place in the project's existing dependency workflow.

## Verify and deliver

For a bug, establish the failing behavior and verify the cause before changing
code. Add the smallest meaningful regression test when warranted. For new
behavior, check the acceptance criteria and important failure boundaries.

Run the relevant checks, then the repository's required broader checks. Batch
related fixes and confirm them; do not churn tools, tests or code after success
without a new reason. Never weaken acceptance criteria to obtain a pass.
Distinguish verified results from static inspection and skipped live gates.

Deliver complete code/artifacts and the necessary run instructions. Report the
outcome, material design decisions, checks actually performed and remaining
limitations in plain language. Never claim a service, codec, operating system or
distribution was tested solely because a unit test passed.

## Non-negotiables

- No secret or sensitive payload logging, shell interpolation of untrusted input,
  unsafe deserialization, or destructive defaults.
- No blanket exception swallowing, leaked resources, unowned background work,
  uncontrolled fan-out, or retries that repeat irreversible effects.
- No unrelated rewrites, automatic toolchain migrations, coverage quotas,
  architecture ceremonies, or performance claims without measurement.
- No production behavior validated only by mocks that replace the code at issue.
- No fake completeness: installation, imports, entry points and requested features
  must be checked where the environment permits.

The quality bar is reliable behavior at the boundary, clarity inside the code,
and evidence at delivery. More classes, dependencies or lines do not establish it.
