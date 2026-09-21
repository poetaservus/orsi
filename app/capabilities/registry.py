from __future__ import annotations

import math
import re
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from pydantic import BaseModel

from app.capabilities.contracts import (
    Capability,
    CapabilityErrorCode,
    CapabilityFailure,
    ExecutionIsolation,
    PermissionClass,
)
from app.inference.contracts import ModelCapabilityDefinition


_CAPABILITY_NAME = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
)


class RegistryConfigurationCode(StrEnum):
    DUPLICATE_NAME = "duplicate_name"
    INVALID_DEFINITION = "invalid_definition"
    INVALID_VISIBILITY = "invalid_visibility"


class CapabilityRegistryConfigurationError(ValueError):
    def __init__(self, code: RegistryConfigurationCode, message: str):
        super().__init__(message)
        self.code = code


class CapabilityLookupError(LookupError):
    def __init__(self, failure: CapabilityFailure):
        super().__init__(failure.message)
        self.failure = failure

    @property
    def code(self) -> CapabilityErrorCode:
        return self.failure.code


@dataclass(frozen=True, slots=True)
class CapabilityRegistration:
    capability: Capability
    enabled: bool = False
    model_visible: bool = False


class CapabilityRegistry:
    """Immutable catalog separating registration, enablement, and visibility."""

    def __init__(self, registrations: Iterable[CapabilityRegistration] = ()):
        validated: list[CapabilityRegistration] = []
        by_name: dict[str, CapabilityRegistration] = {}
        for registration in registrations:
            self._validate_registration(registration)
            name = registration.capability.name
            if name in by_name:
                raise CapabilityRegistryConfigurationError(
                    RegistryConfigurationCode.DUPLICATE_NAME,
                    f"Capability name is registered more than once: {name}",
                )
            by_name[name] = registration
            validated.append(registration)

        validated.sort(key=lambda item: item.capability.name)
        self._registrations = tuple(validated)
        self._by_name: Mapping[str, CapabilityRegistration] = MappingProxyType(
            {item.capability.name: item for item in validated}
        )

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(item.capability.name for item in self._registrations)

    @property
    def enabled_names(self) -> tuple[str, ...]:
        return tuple(
            item.capability.name for item in self._registrations if item.enabled
        )

    @property
    def model_visible_names(self) -> tuple[str, ...]:
        return tuple(
            item.capability.name
            for item in self._registrations
            if item.enabled and item.model_visible
        )

    def resolve(self, name: str) -> Capability:
        registration = self._by_name.get(str(name))
        if registration is None:
            raise CapabilityLookupError(
                CapabilityFailure(
                    code=CapabilityErrorCode.UNKNOWN_CAPABILITY,
                    message="The requested capability is not registered.",
                )
            )
        if not registration.enabled:
            raise CapabilityLookupError(
                CapabilityFailure(
                    code=CapabilityErrorCode.DISABLED_CAPABILITY,
                    message="The requested capability is currently disabled.",
                )
            )
        return registration.capability

    def model_definitions(self) -> tuple[ModelCapabilityDefinition, ...]:
        return tuple(
            ModelCapabilityDefinition(
                name=registration.capability.name,
                description=registration.capability.description,
                input_schema=deepcopy(
                    registration.capability.arguments_model.model_json_schema()
                ),
            )
            for registration in self._registrations
            if registration.enabled and registration.model_visible
        )

    @staticmethod
    def _validate_registration(registration: CapabilityRegistration) -> None:
        if not isinstance(registration, CapabilityRegistration):
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_DEFINITION,
                "Registry entries must be CapabilityRegistration objects.",
            )
        if type(registration.enabled) is not bool or type(registration.model_visible) is not bool:
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_DEFINITION,
                "Capability enabled and model-visible states must be booleans.",
            )
        capability = registration.capability
        if not isinstance(capability, Capability):
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_DEFINITION,
                "A registered implementation must implement Capability.",
            )

        name = getattr(capability, "name", None)
        if (
            not isinstance(name, str)
            or len(name) > 128
            or _CAPABILITY_NAME.fullmatch(name) is None
        ):
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_DEFINITION,
                "Capability names must use lowercase namespace.name syntax.",
            )

        description = getattr(capability, "description", None)
        if (
            not isinstance(description, str)
            or not description.strip()
            or len(description) > 2_000
        ):
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_DEFINITION,
                f"Capability {name} must have a bounded non-empty description.",
            )

        arguments_model = getattr(capability, "arguments_model", None)
        if (
            not isinstance(arguments_model, type)
            or not issubclass(arguments_model, BaseModel)
        ):
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_DEFINITION,
                f"Capability {name} must declare a Pydantic argument model.",
            )
        schema = arguments_model.model_json_schema()
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_DEFINITION,
                f"Capability {name} arguments must forbid unknown object fields.",
            )

        if not isinstance(getattr(capability, "permission", None), PermissionClass):
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_DEFINITION,
                f"Capability {name} must declare a valid permission class.",
            )

        timeout = getattr(capability, "timeout_seconds", None)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
            or timeout > 3_600
        ):
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_DEFINITION,
                f"Capability {name} must declare a timeout between 0 and 3600 seconds.",
            )

        if not isinstance(
            getattr(capability, "execution_isolation", None),
            ExecutionIsolation,
        ):
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_DEFINITION,
                f"Capability {name} must declare a valid execution isolation mode.",
            )

        batch_limit = getattr(capability, "max_calls_per_batch", None)
        if (
            isinstance(batch_limit, bool)
            or not isinstance(batch_limit, int)
            or not 1 <= batch_limit <= 16
        ):
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_DEFINITION,
                f"Capability {name} must declare a batch-call limit between 1 and 16.",
            )
        if batch_limit > 1 and capability.permission != PermissionClass.READ:
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_DEFINITION,
                f"Capability {name} may batch only read-only calls.",
            )

        if registration.model_visible and not registration.enabled:
            raise CapabilityRegistryConfigurationError(
                RegistryConfigurationCode.INVALID_VISIBILITY,
                f"Capability {name} cannot be model-visible while disabled.",
            )
