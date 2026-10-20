"""Fixed-category completion diagnostics; no response bodies, receipt IDs or paths."""
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ReviewFailureReason = Literal['json_invalid', 'schema_invalid', 'remaining_invalid', 'goal_mismatch',
                             'size_limit', 'tool_proposal', 'evidence_invalid', 'unknown']
_REASONS = {'json_invalid', 'schema_invalid', 'remaining_invalid', 'goal_mismatch',
            'size_limit', 'tool_proposal', 'evidence_invalid', 'unknown'}
log = logging.getLogger(__name__)


class ReviewFailure(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    reason: ReviewFailureReason
    model_request: int = Field(ge=0, le=256)
    response_chars: int = Field(ge=0, le=2_000_000)


def safe_review_event(value):
    if not isinstance(value, dict):
        return None
    phase, reason = value.get('phase'), value.get('reason')
    result = {'event': 'completion_review',
              'phase': phase if isinstance(phase, str) and phase in {'accepted', 'rejected', 'exhausted'} else 'unknown',
              'reason': reason if isinstance(reason, str) and reason in _REASONS | {'none'} else 'unknown'}
    for key in ('model_request', 'response_chars', 'receipt_count', 'failure_count'):
        number = value.get(key)
        result[key] = number if type(number) is int and 0 <= number <= 2_000_000 else None
    return result


def record_review_event(phase, reason, *, model_request, response_chars, receipt_count, failure_count):
    value = safe_review_event(dict(phase=phase, reason=reason, model_request=model_request,
        response_chars=response_chars, receipt_count=receipt_count, failure_count=failure_count))
    try:
        log.info('Completion review diagnostic: %s', value, extra={'orsi_completion_review_diagnostic': value})
    except Exception:
        pass
