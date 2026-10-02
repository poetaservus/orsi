"""Registry-driven tool visibility, independent of turn wording and history."""
from __future__ import annotations


def select_turn_capabilities(
    latest_user_text: str,
    available_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Expose the enabled registry catalog for every agent turn.

    The text argument is retained for existing callers, but never filters the
    catalog. Concrete calls are validated and authorized by the runtime's
    permission gate and approval flow. Visibility does not grant execution.
    """
    if not isinstance(latest_user_text, str):
        raise TypeError("Capability routing requires the latest user text.")
    if (
        not isinstance(available_names, tuple)
        or not available_names
        or not all(isinstance(name, str) and name for name in available_names)
        or len(set(available_names)) != len(available_names)
    ):
        raise ValueError("Capability routing requires a non-empty unique catalog.")
    return available_names
