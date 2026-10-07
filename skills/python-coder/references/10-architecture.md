# 10 — Architecture, maintainability and refactoring

Read when module boundaries, coupling or changing legacy code affect the task.

## Size architecture to the problem

| Situation | Suitable starting point |
| --- | --- |
| One bounded transformation | A function and direct tests |
| Small script or CLI | Parsing, core operation, output/exit boundary |
| Stateful application | A state owner plus focused behavior modules |
| Several external integrations | Core operations behind narrow adapters |
| Reusable package | Deliberate public API, private internals and packaging |

These are choices, not mandatory layers. A repository/service/factory for every
class hides behavior instead of clarifying it. Add a boundary when ownership,
variation, testing or reuse justifies the cost. Some duplication is cheaper than
the wrong abstraction; centralize logic early when divergence causes real bugs.

## Keep dependencies understandable

Place domain decisions where they can be tested without a UI or network. Let
adapters convert external input into domain values and translate results back.
Inject collaborators with behavior the caller actually needs; a constructor
argument or callable often suffices. Use a `Protocol` where multiple independent
implementations or substitutability is useful, not for every object.

Prefer composition when behavior varies independently. Inheritance is reasonable
for a framework contract or a real substitutable type; avoid deep hierarchies
that couple unrelated lifecycles. Avoid global registries and hidden service
locators unless the existing architecture needs them.

Data models describe data and invariants. Do not use a dataclass as a substitute
for every behavior-rich object. Keep serialization at an explicit boundary and
avoid exposing an ORM entity or mutable internal structure as a public contract.

## Make lifecycle visible

Every connection, task, worker, timer, file and subprocess needs an owner, an
acquisition point and a release point. The component creating a resource should
release it or explicitly transfer responsibility. A returned generator can keep
resources open; its consumer must be able to close or exhaust it predictably.

Avoid calling startup code during module import. Compose dependencies at the
application boundary. Reusable libraries should not configure the root logger or
start a global event loop for their caller.

## Refactor while preserving evidence

1. Identify the behavior being preserved and the observable defect or pain point.
2. Add characterization tests around valuable untested behavior if necessary.
3. Move one responsibility at a time; avoid simultaneous semantic changes.
4. Compare API signatures, exceptions, ordering, stored schemas and side effects.
5. Run focused tests after the move, then the repository's required checks.

Do not encode a known defect as a new required behavior simply to protect it.
Separate deliberate bug fixes from behavior-preserving moves so the difference
is reviewable. Avoid reformatting an entire project during a local repair.

## Recognize common traps

- A helper with many boolean options often hides separate operations.
- A function doing parsing, I/O, retries, formatting and UI updates has conflicting
  reasons to change; separate the behavior that actually needs isolation.
- A broad `utils.py` becomes an ownership gap; place helpers with their domain.
- Import cycles suggest inverted responsibility, not a need for random delayed
  imports. Delayed imports can still be appropriate for expensive optional features.
- Every test requiring the entire application suggests boundaries are too coupled.
- Private implementation details do not need to become public merely for testing.

Docstrings should explain contracts, units, failure behavior or non-obvious
decisions. Comments explain why; they should not narrate each obvious statement.
Use the repository's style consistently rather than imposing a preferred format.

For models and interfaces read [20](20-types-and-contracts.md); for cleanup read
[30](30-errors-and-resources.md); for tests read [40](40-testing.md).
