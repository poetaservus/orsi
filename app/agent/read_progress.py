"""Renew text-read repetition allowances only after a settled file change."""
from __future__ import annotations

import os
import re

from app.agent.feedback import call_fingerprint
from app.capabilities.contracts import CapabilityResult
from app.inference.protocol import ModelCapabilityCall


class ReadProgressTracker:
    def __init__(self):
        self._reads: dict[str, tuple[str, str | None]] = {}

    def observe(self, call: ModelCapabilityCall, result: CapabilityResult,
                repeated: dict[str, int]) -> None:
        if not result.success or result.output is None:
            return
        if call.capability not in {"filesystem.read_text", "filesystem.edit_text", "filesystem.write_text"}:
            return
        path = result.output.get("path")
        if not isinstance(path, str) or not path:
            return
        # Native tools already return resolved paths. Match them lexically without
        # performing any new filesystem reads or permission checks here.
        path = os.path.normcase(path)
        digest = result.output.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            digest = None
        if call.capability == "filesystem.read_text":
            self._reads[call_fingerprint(call)] = (path, digest)
            return
        if digest is None:
            return
        for fingerprint, (read_path, previous_digest) in self._reads.items():
            if read_path != path:
                continue
            # Successful exact edits reject no-ops even when the prior read was
            # truncated. A whole-file write needs a known old digest to prove change.
            changed = (previous_digest != digest if previous_digest is not None
                       else call.capability == "filesystem.edit_text")
            if changed:
                repeated.pop(fingerprint, None)
            self._reads[fingerprint] = (path, digest)
