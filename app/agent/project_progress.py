"""Renew project checks only after a proven, settled change inside that project."""
from __future__ import annotations

import os
import re

from app.agent.feedback import call_fingerprint
from app.agent.repair_loop import RepairLoopTracker


def _path(value):
    return os.path.normcase(os.path.normpath(value)) if isinstance(value, str) and value else None


class ProjectProgressTracker:
    def __init__(self):
        self._checks = {}
        self._reads = {}
        self._digests = {}
        # Repair obligations and read renewal use the same admission decision.
        self.repair_loop = RepairLoopTracker()

    def renew_source(self, path, repeated):
        path = _path(path)
        if path:
            for fingerprint, target in self._reads.items():
                if target == path:
                    repeated.pop(fingerprint, None)

    def observe(self, call, result, repeated, *, step=0):
        feedback = self.repair_loop.observe(call, result, step=step)
        if not result.success or not isinstance(result.output, dict):
            return feedback
        output = result.output
        if call.capability in {"project.verify", "project.inspect"}:
            project = _path(output.get("project_path"))
            if project:
                self._checks[call_fingerprint(call)] = project
                if self.repair_loop.refresh_project == os.path.normcase(os.path.abspath(project)):
                    for fingerprint, path in self._reads.items():
                        try:
                            if os.path.commonpath((path, project)) == project:
                                repeated.pop(fingerprint, None)
                        except ValueError:
                            pass
            return feedback
        if call.capability not in {"filesystem.read_text", "filesystem.edit_text", "filesystem.write_text"}:
            return
        path, digest = _path(output.get("path")), output.get("sha256")
        if path and call.capability == "filesystem.read_text":
            self._reads[call_fingerprint(call)] = path
        if not path or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            return
        previous = self._digests.get(path)
        self._digests[path] = digest
        changed = (call.capability == "filesystem.edit_text" and previous != digest or
            call.capability == "filesystem.write_text" and (output.get("operation") == "created" or
                previous is not None and previous != digest))
        if not changed:
            return
        self.renew_source(path, repeated)
        for fingerprint, project in self._checks.items():
            try:
                if os.path.commonpath((path, project)) == project:
                    repeated.pop(fingerprint, None)
            except ValueError:
                pass  # Different drives cannot belong to the same project.
        for project in set(self._checks.values()):
            try:
                if os.path.commonpath((path, project)) == project:
                    self.repair_loop.source_changed(os.path.normcase(os.path.abspath(project)))
            except ValueError:
                pass
