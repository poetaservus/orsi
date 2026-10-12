"""Renew project checks only after a proven, settled change inside that project."""
from __future__ import annotations

import os
import re

from app.agent.feedback import call_fingerprint, canonical_json


def _path(value):
    return os.path.normcase(os.path.normpath(value)) if isinstance(value, str) and value else None


class ProjectProgressTracker:
    def __init__(self):
        self._checks = {}
        self._reads = {}
        self._digests = {}
        self._inspected = set()
        self._revisions = {}
        self._diagnoses = {}

    @staticmethod
    def _failure_scope(output):
        # Ignore pixels, measured values and changing error strings. A new
        # unresolved assertion is useful evidence; flicker is not progress.
        failures = [{key:check.get(key) for key in ('action','target','label','expectation','failure_kind')}
            for check in output.get('checks', []) if isinstance(check,dict) and check.get('passed') is False]
        problems = sorted({p.get('kind') for p in output.get('problems', [])
            if isinstance(p,dict) and isinstance(p.get('kind'),str)})
        return canonical_json({'checks':failures,'problems':problems}) if failures or problems else None

    def renew_source(self, path, repeated):
        path = _path(path)
        if path:
            for fingerprint, target in self._reads.items():
                if target == path:
                    repeated.pop(fingerprint, None)

    def observe(self, call, result, repeated):
        if not result.success or not isinstance(result.output, dict):
            return
        output = result.output
        if call.capability in {"project.verify", "project.inspect"}:
            project = _path(output.get("project_path"))
            if project:
                self._checks[call_fingerprint(call)] = project
                snapshot = output.get("screenshot_sha256")
                if (call.capability == "project.inspect" and output.get("inspection_complete") is True
                        and isinstance(snapshot, str) and re.fullmatch(r"[0-9a-f]{64}", snapshot)
                        ):
                    revision = self._revisions.get(project, 0)
                    scenario = canonical_json({key:call.arguments.get(key) for key in ('kind','url','width','height','steps')})
                    failure = self._failure_scope(output)
                    key = (project, revision)
                    diagnoses = self._diagnoses.setdefault(key, [])
                    self._inspected.add((project, revision, scenario, failure))
                    # One initial reassessment and one newly exposed failure per
                    # settled project revision. Scenario changes alone cannot
                    # renew reads, and different pixels never enter this key.
                    if diagnoses and (len(diagnoses) >= 2 or failure is None or failure in diagnoses):
                        return
                    diagnoses.append(failure)
                    for fingerprint, path in self._reads.items():
                        try:
                            if os.path.commonpath((path, project)) == project:
                                repeated.pop(fingerprint, None)
                        except ValueError:
                            pass
            return
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
                    self._revisions[project] = self._revisions.get(project,0)+1
            except ValueError:
                pass
