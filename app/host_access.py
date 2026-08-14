"""Application-facing host-access policy surface.

Production entry points depend on this narrow facade rather than capability implementation
modules. The capability runtime remains the sole place that executes or authorizes calls.
"""

from app.capabilities.host_access import (
    CLOUD_FILE_CONTENT_WARNING,
    FULL_LOCAL_LIST_READ_WARNING,
    FULL_LOCAL_READ_WARNING,
    HostAccessPolicy,
    HostReadScope,
)

__all__ = [
    "CLOUD_FILE_CONTENT_WARNING",
    "FULL_LOCAL_LIST_READ_WARNING",
    "FULL_LOCAL_READ_WARNING",
    "HostAccessPolicy",
    "HostReadScope",
]
