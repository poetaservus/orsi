from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from app.capabilities.contracts import (
    Capability,
    CapabilityContext,
    CapabilityErrorCode,
    ExecutionIsolation,
    PermissionClass,
)
from app.capabilities.filesystem_stat import FilesystemStatCapability
from app.capabilities.registry import (
    CapabilityLookupError,
    CapabilityRegistration,
    CapabilityRegistry,
    CapabilityRegistryConfigurationError,
    RegistryConfigurationCode,
)


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AlphaCapability(Capability[NoArguments]):
    name = "test.alpha"
    description = "An inert capability used only by registry tests."
    arguments_model = NoArguments
    permission = PermissionClass.READ
    timeout_seconds = 1.0
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE

    def execute(self, arguments, context):
        return {"value": "alpha"}


class ZuluCapability(AlphaCapability):
    name = "test.zulu"


def registration(capability=None, *, enabled=False, visible=False):
    return CapabilityRegistration(
        capability=capability or AlphaCapability(),
        enabled=enabled,
        model_visible=visible,
    )


def test_empty_registry_is_valid_and_has_no_model_definitions():
    registry = CapabilityRegistry()

    assert registry.names == ()
    assert registry.enabled_names == ()
    assert registry.model_visible_names == ()
    assert registry.model_definitions() == ()


def test_registry_tracks_registered_enabled_and_visible_states_separately():
    registry = CapabilityRegistry(
        [
            registration(),
            registration(ZuluCapability(), enabled=True),
        ]
    )

    assert registry.names == ("test.alpha", "test.zulu")
    assert registry.enabled_names == ("test.zulu",)
    assert registry.model_visible_names == ()
    assert registry.resolve("test.zulu").name == "test.zulu"


def test_duplicate_names_fail_deterministically():
    with pytest.raises(CapabilityRegistryConfigurationError) as caught:
        CapabilityRegistry([registration(), registration()])

    assert caught.value.code == RegistryConfigurationCode.DUPLICATE_NAME
    assert str(caught.value) == "Capability name is registered more than once: test.alpha"


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("name", "invalid name"),
        ("name", "Alpha"),
        ("name", "alpha"),
        ("description", "  "),
        ("permission", "read"),
        ("timeout_seconds", 0),
        ("timeout_seconds", float("inf")),
        ("execution_isolation", "in_process_cooperative"),
        ("max_calls_per_batch", 0),
        ("max_calls_per_batch", 17),
        ("max_calls_per_batch", True),
    ],
)
def test_invalid_capability_definitions_are_rejected(attribute, value):
    capability = AlphaCapability()
    original = getattr(AlphaCapability, attribute)
    setattr(AlphaCapability, attribute, value)
    try:
        with pytest.raises(CapabilityRegistryConfigurationError) as caught:
            CapabilityRegistry([registration(capability)])
    finally:
        setattr(AlphaCapability, attribute, original)

    assert caught.value.code == RegistryConfigurationCode.INVALID_DEFINITION


def test_argument_model_must_forbid_unknown_fields():
    class PermissiveArguments(BaseModel):
        value: str = ""

    class PermissiveCapability(AlphaCapability):
        name = "test.permissive"
        arguments_model = PermissiveArguments

    with pytest.raises(CapabilityRegistryConfigurationError) as caught:
        CapabilityRegistry([registration(PermissiveCapability())])

    assert caught.value.code == RegistryConfigurationCode.INVALID_DEFINITION


def test_only_read_capabilities_can_opt_into_call_batches():
    class BatchedWriteCapability(AlphaCapability):
        name = "test.batched_write"
        permission = PermissionClass.WRITE
        max_calls_per_batch = 2

    with pytest.raises(CapabilityRegistryConfigurationError) as caught:
        CapabilityRegistry([registration(BatchedWriteCapability())])

    assert caught.value.code == RegistryConfigurationCode.INVALID_DEFINITION
    assert "batch only read-only calls" in str(caught.value)


def test_disabled_capability_cannot_be_model_visible():
    with pytest.raises(CapabilityRegistryConfigurationError) as caught:
        CapabilityRegistry([registration(visible=True)])

    assert caught.value.code == RegistryConfigurationCode.INVALID_VISIBILITY


def test_registration_states_must_be_real_booleans():
    malformed = CapabilityRegistration(AlphaCapability(), enabled="yes")

    with pytest.raises(CapabilityRegistryConfigurationError) as caught:
        CapabilityRegistry([malformed])

    assert caught.value.code == RegistryConfigurationCode.INVALID_DEFINITION


def test_unknown_and_disabled_lookups_have_stable_structured_failures():
    registry = CapabilityRegistry([registration()])

    with pytest.raises(CapabilityLookupError) as unknown:
        registry.resolve("test.missing")
    with pytest.raises(CapabilityLookupError) as disabled:
        registry.resolve("test.alpha")

    assert unknown.value.code == CapabilityErrorCode.UNKNOWN_CAPABILITY
    assert unknown.value.failure.model_dump(mode="json") == {
        "code": "unknown_capability",
        "message": "The requested capability is not registered.",
        "details": [],
    }
    assert disabled.value.code == CapabilityErrorCode.DISABLED_CAPABILITY
    assert disabled.value.failure.model_dump(mode="json") == {
        "code": "disabled_capability",
        "message": "The requested capability is currently disabled.",
        "details": [],
    }


def test_model_definitions_are_sorted_strict_and_do_not_share_mutable_state():
    registry = CapabilityRegistry(
        [
            registration(ZuluCapability(), enabled=True, visible=True),
            registration(enabled=True, visible=True),
        ]
    )

    first = registry.model_definitions()
    assert [definition.name for definition in first] == ["test.alpha", "test.zulu"]
    assert all(definition.input_schema["additionalProperties"] is False for definition in first)
    first[0].input_schema["properties"]["injected"] = {"type": "string"}

    second = registry.model_definitions()
    assert "injected" not in second[0].input_schema["properties"]


def test_filesystem_stat_can_be_registered_only_in_a_test_catalog():
    registry = CapabilityRegistry(
        [
            CapabilityRegistration(
                FilesystemStatCapability(),
                enabled=True,
                model_visible=True,
            )
        ]
    )

    definition = registry.model_definitions()[0].model_dump(mode="json")
    assert definition["name"] == "filesystem.stat"
    assert definition["input_schema"]["required"] == ["path"]
    assert definition["input_schema"]["additionalProperties"] is False


def test_production_startup_remains_disconnected_from_capabilities():
    root = Path(__file__).resolve().parents[1]
    production_entrypoints = [
        root / "app" / "main.py",
        root / "app" / "conversation" / "orchestrator.py",
        root / "app" / "conversation" / "prompt.py",
    ]

    for path in production_entrypoints:
        assert "app.capabilities" not in path.read_text(encoding="utf-8")
