"""Fixed-category context recovery diagnostics without request or exception contents."""
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.inference.attachments import AttachmentError


ContextRecoveryStage = Literal['schema_reserve', 'budget', 'projection', 'compaction']
_STAGES = {'schema_reserve', 'budget', 'projection', 'compaction'}
_EXCEPTIONS = {'attribute_error', 'type_error', 'value_error', 'attachment_error', 'other'}
log = logging.getLogger(__name__)


class ContextRecoveryFailure(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    stage: ContextRecoveryStage
    reason: Literal['unexpected_exception'] = 'unexpected_exception'
    exception_category: Literal['attribute_error', 'type_error', 'value_error', 'attachment_error', 'other']


def context_recovery_failure(stage: ContextRecoveryStage, exc: Exception) -> ContextRecoveryFailure:
    # Never inspect exception strings, arguments, causes, traceback or class names.
    category = ('attachment_error' if isinstance(exc, AttachmentError) else
                'attribute_error' if isinstance(exc, AttributeError) else
                'type_error' if isinstance(exc, TypeError) else
                'value_error' if isinstance(exc, ValueError) else 'other')
    return ContextRecoveryFailure(stage=stage, exception_category=category)


def safe_context_event(value):
    if not isinstance(value, dict):
        return None
    stage, reason, category = value.get('stage'), value.get('reason'), value.get('exception_category')
    return {'event': 'context_recovery',
        'stage': stage if isinstance(stage, str) and stage in _STAGES else 'unknown',
        'reason': reason if isinstance(reason, str) and reason == 'unexpected_exception' else 'unknown',
        'exception_category': category if isinstance(category, str) and category in _EXCEPTIONS else 'unknown'}


def record_context_failure(failure: ContextRecoveryFailure):
    value = safe_context_event(failure.model_dump(mode='json'))
    try:
        log.error('Context recovery diagnostic', extra={'orsi_context_recovery_diagnostic': value})
    except Exception:
        pass
