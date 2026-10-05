"""Conversation-owned authority; bodies stay out of prompts and diagnostics."""
from copy import copy

from app.capabilities.contracts import PermissionClass
from app.capabilities.registry import CapabilityRegistration
from app.capabilities.skill_read_reference import SkillReadReferenceCapability
from app.runtime.skills.reference_reader import SkillReferenceReader, ReferenceReadError
from app.runtime.skills.reference_storage import FilesystemReferenceStorage
from app.security.permissions import PermissionGate, PermissionRule, PermissionDecision


class ConversationSkillReferences:
    def __init__(self, *, enabled=True):
        if type(enabled) is not bool:
            raise TypeError("Skill reference access requires an explicit boolean.")
        self.enabled = enabled
        self.reader = SkillReferenceReader(FilesystemReferenceStorage())
        self.binding = None
        self.status = None
        self._expected = None
        self._blocked_key = None

    def finish(self):
        self.reader.deactivate()
        self.binding = None
        self.status = None

    def reset(self):
        self.finish()
        self._expected = None
        self._blocked_key = None

    def prepare(self, skill, *, tools_enabled, cancellation):
        self.finish()
        if skill is None:
            self.reset()
            return
        key = (skill.name, skill.root_path)
        known = self._expected is not None and self._expected[0] == key and self._expected[3]
        required = "references/" in skill.instructions or known
        if not tools_enabled or not self.enabled:
            self.reset()
            self.status = "tools_disabled" if required else None
            return
        if self._blocked_key == key:
            self.status = "stale"
            return
        self._blocked_key = None
        try:
            binding = self.reader.activate(skill, cancellation)
        except ReferenceReadError as error:
            self._blocked_key = key
            self.status = error.code.value
            return
        if (self._expected is not None and self._expected[0] == key
                and self._expected[1:3] != (binding.package_id, binding.version)):
            self.reader.deactivate()
            self._blocked_key = key
            self.status = "stale"
            return
        self._expected = (key, binding.package_id, binding.version, bool(binding.resources))
        if binding.resources:
            self.binding = binding
        else:
            self.reader.deactivate()
            self.status = "missing" if required else None

    @property
    def scope(self):
        return (self.binding.package_id, self.binding.version) if self.binding is not None else None

    def prompt_payload(self, *, available):
        if available and self.binding is not None:
            return {"available": True, "package_id": self.binding.package_id,
                    "version": self.binding.version, "paths": [r.path for r in self.binding.resources]}
        if self.binding is not None or self.status is not None:
            return {"available": False, "reason": self.status or "tools_disabled"}
        return None

    def continuation_error(self, cancellation):
        if self.binding is None:
            return None
        try:
            if not self.enabled:
                self.reader.deactivate()
            self.reader.validate(self.binding, cancellation)
        except ReferenceReadError as error:
            self._blocked_key = self._expected[0] if self._expected is not None else None
            self.status = error.code.value
            return "The active skill references are unavailable or changed. Refresh the skill before retrying."
        return None

    def scoped_runtime(self, base, *, session_id, turn_id):
        if base is None or self.binding is None:
            return None
        tool = SkillReadReferenceCapability(self.reader, self.binding, session_id=session_id, turn_id=turn_id)
        # Share executor, approvals, model and limits; never mutate the production
        # catalog/policy or shut down this short-lived view independently.
        runtime = copy(base)
        runtime.registry = base.registry.extended((CapabilityRegistration(tool, enabled=True, model_visible=True),))
        runtime.permission_gate = PermissionGate((*base.permission_gate.rules,
            PermissionRule("active-skill-reference-read", PermissionDecision.ALLOW,
                           permission=PermissionClass.READ, capability_pattern=tool.name)))
        return runtime
