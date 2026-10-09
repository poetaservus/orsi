# 95 — Final quality review and definition of done

Read before completing substantial Python work. Scale this review to the actual
change; do not turn it into an unrelated security audit or tool migration.

## 1. Requirements and preservation

- Map each requested behavior to an implementation and observable check.
- Confirm the launch path, input/output contract and expected deliverable.
- Preserve unrelated functionality, public APIs, user state and stored formats.
- Identify material assumptions without presenting them as user requirements.
- Find stubs, fake responses, missing imports/assets and unfinished handlers.

A generated file alone is not a complete application. A summary of a feature
list is not an implementation. A successful mocked call is not a real effect.

## 2. Correctness at the boundary

Inspect empty, invalid, missing, repeated and exceptional inputs that matter.
Check ordering, units, encodings and finite numeric invariants. Ensure accepted
forms are neither accidentally rejected nor broadened without a reason.
Annotations must agree with runtime behavior; static typing cannot replace
validation of external input.

## 3. State, failure and ownership

Check when state changes and whether failure can leave it inconsistent. Test
partial progress, failed persistence and ambiguous external outcomes where
relevant. Retries need classification, idempotency and bounded budgets.

Identify the owner of each file, connection, lock, process, task, thread and timer.
Ensure normal completion, failure, cancellation and shutdown release them or
explicitly transfer ownership. Verify cancellation rather than merely hiding a
busy indicator. Avoid leaked tasks and event-loop/UI blocking.

## 4. Compatibility and maintainability

Match Python syntax/APIs, dependency versions, frameworks and platform promises
to the configured environment. Check imports, dependency declarations, entry
points and package data. Keep public interfaces understandable and avoid a broad
unrelated reformat or abstraction migration.

Review untrusted input, subprocess arguments, path boundaries, secret handling
and logging only where the change exposes them. Check primary documentation for
uncertain APIs. Do not ship examples that assume packages or methods exist.

## 5. Evidence

Use the repository's required tests, lint, typing, build and native gates when
supported by the host's actual tools. In O.R.S.I., source inspection and saved-byte
checks cannot establish Python, import, test or GUI execution; explicitly report
those unavailable gates as unrun. Do not infer a defect or make another speculative
edit merely because execution is unavailable. Behavioral tests should cover the
relevant defect, not restate the implementation. Confirm that replacing the work
with a no-op would fail the acceptance check. Distinguish deterministic unit/
integration results from live provider calls, external services, native UI, media
and untested platforms.

For performance requests, compare representative before/after measurements with
the same result contract. Do not claim speed from clever-looking code.

## Bounded correction cycle

Collect related defects, fix them as a coherent batch, and run focused confirmation
plus required broader gates. Stop when criteria are satisfied. If a blocking
defect remains, repair and recheck that defect; do not mechanically repeat every
inspection or change unrelated policy to make acceptance pass.

## Completion standard

The work is ready when:

- the requested behavior is implemented and usable in the target environment;
- relevant error, empty, interruption and shutdown paths are accounted for;
- existing contracts/data are preserved or a requested migration is explicit;
- required checks pass, with unrun gates and limitations accurately identified;
- the artifact includes needed run/configuration information;
- claims about effects, compatibility and performance are supported by evidence.

Report the result and meaningful validation plainly. Say what remains unavailable
if a missing asset/service prevents verification. Do not manufacture success,
dump private diagnostics, or imply skipped gates passed.
