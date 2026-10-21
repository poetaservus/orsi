"""Local, content-free correlation scoped to one conversation turn.

Capture these values before crossing a transport thread boundary. Provider IDs,
prompts, document identities and selected profiles never participate in them.
"""
from contextvars import ContextVar
import re
from uuid import uuid4


_TURN = ContextVar("orsi_diagnostic_turn", default=None)
_REQUEST_PHASE = ContextVar("orsi_diagnostic_request_phase", default="reply")
_LOCAL_ID = re.compile(r"[0-9a-f]{32}\Z")
_PHASES = frozenset({"reply", "completion_review", "image_generation"})


def safe_local_id(value):
    return value if isinstance(value, str) and _LOCAL_ID.fullmatch(value) else None


def safe_phase(value):
    return value if isinstance(value, str) and value in _PHASES else "unknown"


def begin_turn():
    return _TURN.set(uuid4().hex)


def end_turn(token):
    _TURN.reset(token)


def current_turn_id():
    return safe_local_id(_TURN.get())


def current_request_phase():
    return safe_phase(_REQUEST_PHASE.get())


def run_in_turn(turn_id, callback, request_phase="reply"):
    """Carry only validated diagnostic labels across an owned thread boundary."""
    turn_token = _TURN.set(safe_local_id(turn_id))
    phase_token = _REQUEST_PHASE.set(safe_phase(request_phase))
    try:
        return callback()
    finally:
        _REQUEST_PHASE.reset(phase_token)
        _TURN.reset(turn_token)


def new_request_id():
    return uuid4().hex
