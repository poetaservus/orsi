# Checks

Use plain Python assertions for [Behavior](behavior.md).
Show these four exact checks:

```python
assert clamp(-2, 0, 3) == 0
assert clamp(2, 0, 3) == 2
assert clamp(5, 0, 3) == 3
assert clamp(8, 4, 4) == 4
```

For reversed bounds, call `clamp(2, 3, 0)` in a `try` block.
Assert the caught `ValueError` message is `lower exceeds upper`.
If no exception occurs, fail with `assert False, "expected ValueError"`.
Do not execute the checks unless the user asks.
