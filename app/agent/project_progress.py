"""Renew project checks only after a proven, settled change inside that project."""
from __future__ import annotations

import os
import re

from app.agent.feedback import call_fingerprint


def _path(value):
    return os.path.normcase(os.path.normpath(value)) if isinstance(value, str) and value else None


class ProjectProgressTracker:
    def __init__(self):
        self._checks = {}
        self._digests = {}

    def observe(self, call, result, repeated):
        if not result.success or not isinstance(result.output, dict):
            return
        output = result.output
        if call.capability in {"project.verify", "project.inspect"}:
            project = _path(output.get("project_path"))
            if project:
                self._checks[call_fingerprint(call)] = project
            return
        if call.capability not in {"filesystem.read_text", "filesystem.edit_text", "filesystem.write_text"}:
            return
        path, digest = _path(output.get("path")), output.get("sha256")
        if not path or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            return
        previous = self._digests.get(path)
        self._digests[path] = digest
        changed = (call.capability == "filesystem.edit_text" or
            call.capability == "filesystem.write_text" and (output.get("operation") == "created" or
                previous is not None and previous != digest))
        if not changed:
            return
        for fingerprint, project in self._checks.items():
            try:
                if os.path.commonpath((path, project)) == project:
                    repeated.pop(fingerprint, None)
            except ValueError:
                pass  # Different drives cannot belong to the same project.
