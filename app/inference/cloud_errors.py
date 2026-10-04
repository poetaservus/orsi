"""Shared provider-independent cloud failure contract."""
from enum import StrEnum

from app.inference.engine import InferenceUnavailable


class CloudErrorCode(StrEnum):
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    QUOTA = "quota"
    RATE_LIMIT = "rate_limit"
    CONNECTION = "connection"
    TIMEOUT = "timeout"
    CONTEXT_OVERFLOW = "context_overflow"
    BAD_REQUEST = "bad_request"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    TOOLS_NOT_READY = "tools_not_ready"
    CLOSED = "closed"


class CloudInferenceError(InferenceUnavailable):
    def __init__(
        self,
        message: str,
        *,
        allow_local_fallback: bool = False,
        retryable: bool = False,
        code: CloudErrorCode | None = None,
    ):
        super().__init__(message)
        self.allow_local_fallback = allow_local_fallback
        self.retryable = retryable
        self.code = code
