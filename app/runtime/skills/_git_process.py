"""Compatibility module identity for the shared Windows process owner."""
import sys
from app.runtime import owned_process

sys.modules[__name__] = owned_process
