"""Bind reviewed MCP contracts to ORSI's existing permissions and journaled executor."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock

from app.capabilities.contracts import (
    Capability, CapabilityErrorCode as Code, CapabilityExecutionError as Error,
    ExecutionIsolation, PermissionClass,
)
from app.capabilities.registry import CapabilityRegistration, CapabilityRegistry
from app.mcp.office_contracts import OFFICE_TOOLS, OfficeExposure, SaveArguments, canonical_json, office_catalog
from app.security.permissions import PermissionDecision, PermissionRule
from app.security.write_policy import HostWritePolicy


@dataclass(frozen=True, slots=True)
class OfficeResourceBinding:
    """Trusted host adapter's live identity; never supplied by the model or MCP annotations.

    A None path is only for explicitly authorized unsaved documents/metadata.
    Later live adapters must enforce session identity, snapshot coverage and scope.
    """
    resource: Path | None
    identity: str
    preview: str | None = None

    def __post_init__(self):
        if (self.resource is not None and (not isinstance(self.resource, Path) or not self.resource.is_absolute())):
            raise ValueError("Office resources must be absolute paths.")
        if not isinstance(self.identity, str) or not 1 <= len(self.identity) <= 256:
            raise ValueError("Office resource bindings require a bounded live identity.")
        if self.preview is not None and (not isinstance(self.preview, str) or len(self.preview) > 2000):
            raise ValueError("Office previews must be bounded text.")


def _exposure(connection, model):
    value = connection.exposure
    if getattr(model, "mode", None) != "cloud":
        value = OfficeExposure(**{**value.model_dump(), "backend": "local"})
    return value


class OfficeCapability(Capability):
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE
    timeout_seconds = 40.0

    def __init__(self, contract, connection, model, resource_policy, write_policy):
        self.contract, self.connection, self.model = contract, connection, model
        self.name, self.description = contract.name, contract.description
        self.arguments_model, self.permission = contract.arguments, contract.permission
        self.resource_policy, self.write_policy = resource_policy, write_policy
        self._prepared, self._lock = OrderedDict(), RLock()

    def _current_binding(self, arguments, context):
        context.cancellation.raise_if_cancelled()
        exposure = _exposure(self.connection, self.model)
        try:
            office_catalog(exposure).validate_call(self.name, arguments.model_dump(mode="json"), current=exposure)
        except ValueError:
            raise Error(Code.DISABLED_CAPABILITY, "The Office capability is not enabled for this cloud connection.") from None
        if self.resource_policy is None:
            raise Error(Code.PERMISSION_DENIED, "The live Office host resource policy is not installed.")
        binding = self.resource_policy(self.contract, arguments, context)
        if not isinstance(binding, OfficeResourceBinding):
            raise Error(Code.PERMISSION_DENIED, "The Office resource policy returned no trusted binding.")
        if binding.resource is not None:
            if self.permission == PermissionClass.WRITE:
                resolved = self.write_policy.resolve_document_file(str(binding.resource))
            elif context.host_access_policy is not None:
                resolved = context.host_access_policy.resolve_read(str(binding.resource)).resolved
            else:
                from app.security.path_policy import resolve_read_path
                resolved = resolve_read_path(str(binding.resource), portable_root=context.portable_root,
                    allowed_roots=context.allowed_read_roots).resolved
            if resolved != binding.resource:
                raise Error(Code.PERMISSION_DENIED, "The Office resource identity is not canonical.")
        if isinstance(arguments, SaveArguments) and arguments.path is not None:
            if binding.resource != self.write_policy.resolve_document_file(arguments.path):
                raise Error(Code.PERMISSION_DENIED, "Save As must be bound to its exact destination.")
        identity = sha256(canonical_json({"exposure": exposure.model_dump(mode="json"),
            "binding": binding.identity, "arguments": arguments.model_dump(mode="json")}).encode()).hexdigest()
        return exposure, binding, identity

    def _prepare(self, arguments, context):
        with self._lock:
            if context.call_id not in self._prepared:
                self._prepared[context.call_id] = self._current_binding(arguments, context)
                while len(self._prepared) > 64:
                    self._prepared.popitem(last=False)
            return self._prepared[context.call_id]

    def permission_resource(self, arguments, context):
        return self._prepare(arguments, context)[1].resource

    def approval_details(self, arguments, context):
        _, binding, identity = self._prepare(arguments, context)
        return binding.preview, identity

    def execute(self, arguments, context):
        try:
            exposure, binding, identity = self._current_binding(arguments, context)
            if (identity != context.authorized_resource_identity or
                    (str(binding.resource) if binding.resource is not None else None) != context.authorized_resource):
                raise Error(Code.PERMISSION_DENIED, "The exact approved Office target changed before execution.")
            return self.connection.call(self.contract, arguments, expected=exposure,
                                        operation=context.call_id, cancellation=context.cancellation)
        finally:
            with self._lock:
                self._prepared.pop(context.call_id, None)

    def shutdown(self):
        with self._lock:
            self._prepared.clear()
        self.connection.close()


class OfficeCapabilityRegistry(CapabilityRegistry):
    """Preserve built-ins and skill extensions; expose Office by connection state only."""
    def __init__(self, base, connection, model, *, resource_policy, write_policy):
        self.base, self.connection, self.model = base, connection, model
        self.resource_policy, self.write_policy = resource_policy, write_policy
        registrations = [CapabilityRegistration(OfficeCapability(tool, connection, model,
            resource_policy, write_policy), enabled=True, model_visible=False) for tool in OFFICE_TOOLS]
        combined = base.extended(registrations)
        super().__init__(combined._registrations)

    def model_definitions(self):
        office = (office_catalog(_exposure(self.connection, self.model)).model_definitions()
                  if self.resource_policy is not None else ())
        return tuple(sorted((*self.base.model_definitions(), *office), key=lambda definition: definition.name))

    @property
    def model_visible_names(self):
        return tuple(definition.name for definition in self.model_definitions())

    def extended(self, registrations):
        return OfficeCapabilityRegistry(self.base.extended(registrations), self.connection, self.model,
            resource_policy=self.resource_policy, write_policy=self.write_policy)


def office_permission_rules():
    return tuple(PermissionRule("office-" + tool.name, PermissionDecision.ALLOW
        if tool.permission == PermissionClass.READ else PermissionDecision.ASK,
        permission=tool.permission, capability_pattern=tool.name) for tool in OFFICE_TOOLS)
