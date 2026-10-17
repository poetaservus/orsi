"""Bind reviewed MCP contracts to ORSI's existing permissions and journaled executor."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from threading import RLock

from app.capabilities.contracts import (
    Capability, CapabilityArgumentError, CapabilityErrorCode as Code, CapabilityExecutionError as Error,
    ExecutionIsolation, PermissionClass,
)
from app.capabilities.registry import CapabilityRegistration, CapabilityRegistry
from app.mcp.office_contracts import (
    OFFICE_TOOLS, OfficeExposure, SaveArguments, WordComposeArguments, canonical_json, office_catalog,
)
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
    source_resource: Path | None = None

    def __post_init__(self):
        if (self.resource is not None and (not isinstance(self.resource, Path) or not self.resource.is_absolute())):
            raise ValueError("Office resources must be absolute paths.")
        if not isinstance(self.identity, str) or not 1 <= len(self.identity) <= 256:
            raise ValueError("Office resource bindings require a bounded live identity.")
        if self.preview is not None and (not isinstance(self.preview, str) or len(self.preview) > 2000):
            raise ValueError("Office previews must be bounded text.")
        if self.source_resource is not None and (not isinstance(self.source_resource, Path) or not self.source_resource.is_absolute()):
            raise ValueError("Office source resources must be absolute paths.")


def _exposure(connection, model):
    value = connection.exposure
    if getattr(model, "mode", None) != "cloud":
        value = OfficeExposure(**{**value.model_dump(), "backend": "local"})
    return value


def _compose_branch(label):
    for branch in ("WordParagraph", "WordTable", "WordPageBreak", "WordImage", "WordColumnBreak", "WordSectionBreak"):
        if label == branch or label.startswith("function-after[") and f", {branch}]" in label:
            return branch
    return None


def _compose_error_details(raw, details):
    """Discard errors from union alternatives the supplied block kind excludes."""
    try:
        raw = WordComposeArguments.complete_pages(raw)
    except ValueError:
        pass
    blocks = raw.get("blocks", []) if isinstance(raw, dict) else []
    branches = {"paragraph": "WordParagraph", "table": "WordTable", "page_break": "WordPageBreak",
        "image": "WordImage", "column_break": "WordColumnBreak", "section_break": "WordSectionBreak"}
    focused = []
    for detail in details:
        location = detail.get("location", [])
        if (len(location) >= 3 and location[0] == "blocks" and location[1].isdecimal()
                and isinstance(blocks, list) and int(location[1]) < len(blocks)):
            block = blocks[int(location[1])]
            expected = branches.get(block.get("kind")) if isinstance(block, dict) and isinstance(block.get("kind"), str) else None
            branch = _compose_branch(location[2])
            if expected and branch and branch != expected:
                continue
        focused.append(detail)
    return focused or details


def _empty_compose_plan(raw):
    """Describe only the bounded structural failure, never document contents."""
    blocks = raw.get("blocks") if isinstance(raw, dict) else None
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 96:
        return None
    if not all(isinstance(block, dict) and (not block or
            set(block) == {"kind"} and block["kind"] == "page_break") for block in blocks):
        return None
    return {"paragraphs": 0, "tables": 0,
            "page_breaks": sum(bool(block) for block in blocks),
            "empty_blocks": sum(not block for block in blocks)}


def _compose_error_message(details, empty_plan=None):
    """Explain bounded constraints without echoing input values or unknown keys."""
    if empty_plan is not None:
        return ("Invalid Word composition arguments. blocks: received "
            f"{empty_plan['page_breaks']} page-break blocks and {empty_plan['empty_blocks']} empty blocks; "
            "no paragraphs or tables. Supply the COMPLETE document body in nonempty pages, each with paragraph/table blocks. "
            "For two pages supply two full page objects; word_compose replaces all content. No Word write was dispatched.")
    schema = WordComposeArguments.model_json_schema()
    fields = set(schema["properties"])
    fields.update(("blocks", "page_break_before"))  # Safe historical/native field names.
    for child in schema.get("$defs", {}).values():
        fields.update(child.get("properties", {}))
    rules = {
        "missing": "required field is missing",
        "extra_forbidden": "unexpected field; use the advertised schema",
        "literal_error": "use an advertised choice",
        "string_type": "must be text", "list_type": "must be a list",
        "model_type": "must be an object", "float_type": "must be a number",
        "bool_type": "must be true or false",
    }
    known = {
        "The Office payload exceeds its byte limit.",
        "Word tables need one column width per column and at most 256 cells.",
        "Word layout requires usable body space and header/footer distances inside the margins.",
        "Word table widths exceed the printable body width.",
        "The Word document exceeds its bounded content limit.",
        "Use separate Word paragraph/page-break blocks; text cannot contain control markers.",
        "Word composition requires paragraph or table content; supply the complete replacement body.",
        "Office matrices must be rectangular.", "Office matrices exceed the cell limit.",
        "Supply complete nonempty pages, without a separate blocks plan.",
        "Each planned page requires its complete nonempty paragraph/table blocks.",
        "Use complete page content; page boundaries are applied between pages.",
        "Supply exactly one complete body representation: sections, pages or blocks.",
        "Section column settings must be supplied only on sections.",
        "Each section requires bounded content and column settings.",
        "Each section requires paragraph, table or image content.",
        "Use section transitions and column breaks inside sections.",
        "The first section must start continuously.",
        "Word columns require at least 20 mm of usable width.",
        "Column breaks require a two-column section.",
        "Word image width exceeds its containing column width.",
        "Word requires nonempty sections, at most 16 sections and eight images.",
        "Pictures require meaningful nonblank alt text.",
    }
    numeric = {"greater_than", "greater_than_equal", "less_than", "less_than_equal", "multiple_of",
               "string_too_long", "string_too_short", "too_long", "too_short"}
    hints = []
    for detail in details:
        parts = [part for part in detail.get("location", []) if _compose_branch(part) is None]
        label = ".".join(part if part in fields or part.isdecimal() and len(part) <= 5 else "field"
                         for part in parts) or "arguments"
        kind, message = detail.get("type"), detail.get("message", "")
        if kind == "value_error":
            message = message.removeprefix("Value error, ")
            width = re.fullmatch(r"Word (?:image width exceeds its|table widths exceed their) containing column width; maximum ([0-9]{1,3}\.[0-9]{3}) mm\.", message)
            hint = message if message in known or width and 0 < float(width[1]) <= 420 else "does not match the advertised schema"
        elif kind == "string_pattern_mismatch":
            hint = ("use separate paragraph blocks; text cannot contain newlines, tabs or controls"
                    if (parts and parts[-1] in {"text", "header", "footer"}) or "cells" in parts
                    else "must match the advertised pattern")
        else:
            hint = message if kind in numeric else rules.get(kind, "does not match the advertised schema")
        value = f"{label}: {hint}"
        if value not in hints:
            hints.append(value)
        if len(hints) == 3:
            break
    return ("Invalid Word composition arguments. " + "; ".join(hints)[:380].rstrip(".")
            + ". No Word write was dispatched. Correct the arguments before retrying.")


class OfficeCapability(Capability):
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE
    timeout_seconds = 40.0

    def __init__(self, contract, connection, model, resource_policy, write_policy):
        self.contract, self.connection, self.model = contract, connection, model
        self.name, self.description = contract.name, contract.description
        self.arguments_model, self.permission = contract.arguments, contract.permission
        self.resource_policy, self.write_policy = resource_policy, write_policy
        self._prepared, self._lock = OrderedDict(), RLock()
        if self.name == "office.word_compose" and callable(getattr(connection, "tool_timeout", None)):
            # Execution rechecks binding and mutation authority (two controls),
            # then waits for the verified tool receipt and bounded shutdown.
            self.timeout_seconds = max(self.timeout_seconds,
                connection.tool_timeout(contract) + 2 * connection.call_timeout + 10.0)

    def validate_arguments(self, raw_arguments):
        from app.inference.word_plan_diagnostics import record_word_plan
        if self.name == "office.word_compose":
            record_word_plan("validation_input", raw_arguments)
        try:
            plan = super().validate_arguments(raw_arguments)
            if self.name == "office.word_compose":
                record_word_plan("validated_plan", plan.model_dump(mode="json"))
            return plan
        except CapabilityArgumentError as exc:
            if self.name != "office.word_compose":
                raise
            record_word_plan("validation_rejected", raw_arguments)
            details = _compose_error_details(raw_arguments, exc.failure.details)
            empty_plan = _empty_compose_plan(raw_arguments)
            message = _compose_error_message(details, empty_plan)
            # This message is generated from allowlisted fields/rules above;
            # raw Pydantic errors can contain private keys and are never logged.
            from app.inference.word_plan_diagnostics import log as diagnostic_log
            diagnostic_log.info("word_compose validation_feedback=%s", message)
            raise CapabilityArgumentError(exc.failure.model_copy(update={
                "message": message,
                "details": details + ([{"word_plan_shape": empty_plan}] if empty_plan is not None else []),
            })) from None

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
        if self.permission == PermissionClass.WRITE and binding.source_resource is not None:
            if self.write_policy.resolve_document_file(str(binding.source_resource)) != binding.source_resource:
                raise Error(Code.PERMISSION_DENIED, "The Office source resource identity is not canonical.")
        if self.connection.live and self.permission == PermissionClass.WRITE:
            mutation = self.connection.prepare_mutation(self.contract, arguments, context)
            binding = OfficeResourceBinding(binding.resource,
                sha256(canonical_json([binding.identity, mutation["digest"]]).encode()).hexdigest(),
                mutation["preview"], binding.source_resource)
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
            if self.name == "office.image_register":
                return self.connection.register_image(arguments, binding.resource, context.cancellation, context.session_id)
            if self.name == "office.read" and arguments.target == "assets":
                return self.connection.discover_picture_sources(arguments, context)
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
        if self.connection.live:
            from app.mcp.office_excel import live_tools
            allowed = live_tools(_exposure(self.connection, self.model).applications)
            office = tuple(tool for tool in office if tool.name in allowed)
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
