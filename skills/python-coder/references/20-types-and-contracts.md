# 20 — Types, domain models and input contracts

Read for public APIs, type checking, external input or state invariants.

## Types describe; validation enforces

Python annotations do not validate incoming JSON, CLI values or database results.
`TypedDict` is a static shape, `cast` is a checker assertion, and `Protocol` is a
structural interface. None makes untrusted data safe. Validate once at the
boundary, then pass well-defined values through the core.

Separate missing from null, false, zero and empty. Define coercion intentionally:
accepting `"12"` as an integer may be useful for a CLI but wrong for a strict JSON
contract. `bool` is an `int` subclass; reject it explicitly where a real integer
is required. Check non-finite floats where ordering/range invariants depend on
finite values. Validate length and bounds before expensive allocation or parsing.

Use `ValueError` for an accepted kind of input with an invalid value; use
`TypeError` for the wrong kind. Follow the existing API's exception contract if
it intentionally differs. Error messages should name the field and expectation
without echoing secrets or whole sensitive payloads.

## Choose the narrowest useful abstraction

- Read-only inputs: `Mapping` or `Sequence` when those operations are required.
- Single-pass consumption: `Iterable` when indexing/length is unnecessary.
- Concrete outputs: return a real, stable type callers can use.
- Small records: dataclasses with `default_factory` for mutable members.
- JSON-like static shapes: `TypedDict`, with runtime validation separately.
- Substitutable collaborators: `Protocol`; avoid forced inheritance.
- Complex external schemas: the project's established validation library, with
  coercion, unknown-field and error policies explicitly configured.

Use generics when they preserve a relationship between inputs and outputs.
Introduce `Any` at genuinely dynamic boundaries and narrow it promptly. A broad
`Any`, `cast`, `type: ignore` or checker exclusion should have a concrete reason,
not disguise an unverified assumption. Read-only/frozen wrappers may still
contain mutable objects; immutability must include the contained representation.

## Executable boundary example

This Python 3.10+ example accepts only a real integer or ASCII decimal string and
requires a valid nonzero TCP port. It deliberately rejects boolean values,
whitespace, floats and Unicode digit spellings. That is this example's contract,
not a universal parser policy.

```python
def parse_port(value: object) -> int:
    if type(value) is int:
        port = value
    elif isinstance(value, str) and value.isascii() and value.isdecimal():
        if len(value) > 5:
            raise ValueError("port must be between 1 and 65535")
        port = int(value)
    else:
        raise TypeError("port must be an integer or ASCII decimal string")
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return port
```

Reject oversized input before conversion and preserve the documented accepted
forms. Do not generalize this parser into accepting arbitrary configuration.

## Adopt typing without unrelated churn

Use the project's configured mypy, Pyright or other checker and its Python target.
For existing code, improve changed public contracts first and preserve accepted
strictness. A blanket strict-mode migration is separate work. Prefer inference
for obvious local values, and keep signatures understandable.

Version gates matter: `Self` and `NotRequired` are in `typing` in Python 3.11+;
new generic/type-alias syntax requires 3.12+. Use compatible forms or a supported
`typing_extensions` dependency when the project's floor is lower. Do not claim
runtime type checks prove a protocol's complete method signatures.

For exception boundaries read [30](30-errors-and-resources.md); for tests of the
accepted/rejected inputs read [40](40-testing.md).
