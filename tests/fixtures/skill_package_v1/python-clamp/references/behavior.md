# Behavior

Implement `clamp(value, lower, upper)` for integers.

- Below `lower`, return `lower`.
- Above `upper`, return `upper`.
- Inside the inclusive bounds, return `value` unchanged.
- Equal bounds are valid and return that bound.
- If `lower > upper`, raise `ValueError("lower exceeds upper")`.

Check reversed bounds before clamping. Do not swap them silently.
Do not coerce inputs or add type validation; inputs are already integers.
