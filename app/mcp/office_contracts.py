"""Office v1 contracts. Importing this module cannot connect or execute tools."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.capabilities.contracts import PermissionClass
from app.inference.contracts import ModelCapabilityDefinition


CONTRACT_VERSION = 1
MAX_ARGUMENT_BYTES = 32_768
MAX_RESULT_BYTES = 16_384
MAX_CELLS = 1_000
MAX_CHANGES = 16
APPLICATIONS = ("excel", "word", "powerpoint")
OfficeApplication = Literal["excel", "word", "powerpoint"]
Identifier = Annotated[str, Field(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")]
Cell = Annotated[str, Field(max_length=4_096)] | int | float | bool | None
Matrix = Annotated[list[Annotated[list[Cell], Field(min_length=1, max_length=MAX_CELLS)]],
                   Field(min_length=1, max_length=MAX_CELLS)]
TextMatrix = Annotated[list[Annotated[list[Annotated[str, Field(max_length=4_096)]],
                                   Field(min_length=1, max_length=MAX_CELLS)]],
                       Field(min_length=1, max_length=MAX_CELLS)]
_A1_RANGE = re.compile(r"^\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})(?::\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6}))?$")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))


def _matrix_cells(matrix) -> int:
    if matrix is None:
        return 0
    if len({len(row) for row in matrix}) != 1:
        raise ValueError("Office matrices must be rectangular.")
    count = sum(len(row) for row in matrix)
    if count > MAX_CELLS:
        raise ValueError("Office matrices exceed the cell limit.")
    return count


def excel_range_shape(address: str) -> tuple[int, int]:
    """Allow only bounded rectangular A1 addresses; never whole columns or code."""
    match = _A1_RANGE.fullmatch(address)
    if match is None:
        raise ValueError("Excel changes require a rectangular A1 address.")
    start_column, start_row, end_column, end_row = match.groups()

    def column_number(name):
        number = 0
        for character in name.upper():
            number = number * 26 + ord(character) - ord("A") + 1
        return number

    left, top = column_number(start_column), int(start_row)
    right, bottom = column_number(end_column or start_column), int(end_row or start_row)
    if not (1 <= left <= right <= 16_384 and 1 <= top <= bottom <= 1_048_576):
        raise ValueError("The Excel range is reversed or outside worksheet bounds.")
    rows, columns = bottom - top + 1, right - left + 1
    if rows * columns > MAX_CELLS:
        raise ValueError("The Excel target exceeds the cell limit.")
    return rows, columns


class OfficeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True,
                              allow_inf_nan=False, hide_input_in_errors=True)
    byte_limit: ClassVar[int] = MAX_ARGUMENT_BYTES

    @model_validator(mode="after")
    def check_size(self):
        if len(canonical_json(self.model_dump(mode="json")).encode("utf-8")) > self.byte_limit:
            raise ValueError("The Office payload exceeds its byte limit.")
        return self


class DocumentsArguments(OfficeModel):
    application: OfficeApplication | None = None
    cursor: Identifier | None = None
    limit: int = Field(default=20, ge=1, le=50)


class AttachArguments(OfficeModel):
    application: OfficeApplication
    document: Identifier


class ReadArguments(OfficeModel):
    session: Identifier
    target: str = Field(default="selection", min_length=1, max_length=256)
    cursor: Identifier | None = None
    max_items: int = Field(default=100, ge=1, le=MAX_CELLS)
    max_chars: int = Field(default=4_096, ge=1, le=8_192)


class ExcelChange(OfficeModel):
    sheet: str = Field(min_length=1, max_length=128)
    range: str = Field(min_length=1, max_length=256)
    values: Matrix | None = None
    formulas: TextMatrix | None = None
    number_format: str | None = Field(default=None, min_length=1, max_length=128)
    bold: bool | None = None
    italic: bool | None = None

    @model_validator(mode="after")
    def check_change(self):
        if self.values is not None and self.formulas is not None:
            raise ValueError("Literal values and formulas require separate changes.")
        if all(getattr(self, field) is None for field in
               ("values", "formulas", "number_format", "bold", "italic")):
            raise ValueError("An Excel change must specify an operation.")
        shape = excel_range_shape(self.range)
        for matrix in (self.values, self.formulas):
            _matrix_cells(matrix)
            if matrix is not None and (len(matrix), len(matrix[0])) != shape:
                raise ValueError("Excel payload dimensions must match the exact target range.")
        return self


class WordChange(OfficeModel):
    target: Identifier
    action: Literal["replace_text", "insert_after", "apply_style", "edit_table"]
    text: str | None = Field(default=None, max_length=4_096)
    style: str | None = Field(default=None, min_length=1, max_length=128)
    cells: TextMatrix | None = None

    @model_validator(mode="after")
    def check_change(self):
        required = {"replace_text": "text", "insert_after": "text",
                    "apply_style": "style", "edit_table": "cells"}[self.action]
        if {name for name in ("text", "style", "cells") if getattr(self, name) is not None} != {required}:
            raise ValueError("A Word change must contain only its action's payload.")
        _matrix_cells(self.cells)
        return self


class Geometry(OfficeModel):
    left: float = Field(ge=0, le=100_000)
    top: float = Field(ge=0, le=100_000)
    width: float = Field(gt=0, le=100_000)
    height: float = Field(gt=0, le=100_000)


class PowerPointChange(OfficeModel):
    action: Literal["set_text", "add_slide", "position"]
    target: Identifier | None = None
    text: str | None = Field(default=None, max_length=4_096)
    layout: Literal["title", "title_content", "blank"] | None = None
    geometry: Geometry | None = None

    @model_validator(mode="after")
    def check_change(self):
        required = {"set_text": {"target", "text"}, "add_slide": {"layout"},
                    "position": {"target", "geometry"}}[self.action]
        if {name for name in ("target", "text", "layout", "geometry")
                if getattr(self, name) is not None} != required:
            raise ValueError("A PowerPoint change must contain only its action's payload.")
        return self


class EditArguments(OfficeModel):
    session: Identifier
    snapshot: Identifier


class ExcelEditArguments(EditArguments):
    changes: list[ExcelChange] = Field(min_length=1, max_length=MAX_CHANGES)

    @model_validator(mode="after")
    def check_cells(self):
        if sum(rows * columns for rows, columns in
               (excel_range_shape(c.range) for c in self.changes)) > MAX_CELLS:
            raise ValueError("The Excel patch exceeds the cell limit.")
        return self


class WordEditArguments(EditArguments):
    changes: list[WordChange] = Field(min_length=1, max_length=MAX_CHANGES)

    @model_validator(mode="after")
    def check_cells(self):
        if sum(_matrix_cells(c.cells) for c in self.changes) > MAX_CELLS:
            raise ValueError("The Word patch exceeds the cell limit.")
        return self


class PowerPointEditArguments(EditArguments):
    changes: list[PowerPointChange] = Field(min_length=1, max_length=MAX_CHANGES)


class SaveArguments(OfficeModel):
    session: Identifier
    path: str | None = Field(default=None, min_length=1, max_length=32_767)
    overwrite: bool = False

    @model_validator(mode="after")
    def check_overwrite(self):
        if self.path is None and self.overwrite:
            raise ValueError("Overwrite applies only to an explicit Save As destination.")
        return self


class RevertArguments(EditArguments):
    recovery: Identifier


class OfficeResult(OfficeModel):
    byte_limit: ClassVar[int] = MAX_RESULT_BYTES


class Document(OfficeModel):
    document: Identifier
    application: OfficeApplication
    title: str = Field(min_length=1, max_length=256)
    dirty: bool
    has_path: bool
    read_only: bool


class DocumentsResult(OfficeResult):
    documents: list[Document] = Field(max_length=50)
    cursor: Identifier | None = None


class AttachResult(OfficeResult):
    session: Identifier
    document: Document


class ReadItem(OfficeModel):
    target: Identifier
    label: str = Field(max_length=256)
    text: str | None = Field(default=None, max_length=8_192)
    values: Matrix | None = None
    formulas: TextMatrix | None = None
    style: str | None = Field(default=None, max_length=128)
    geometry: Geometry | None = None

    @model_validator(mode="after")
    def check_cells(self):
        _matrix_cells(self.values)
        _matrix_cells(self.formulas)
        return self


class ReadResult(OfficeResult):
    session: Identifier
    application: OfficeApplication
    snapshot: Identifier
    items: list[ReadItem] = Field(max_length=MAX_CELLS)
    cursor: Identifier | None = None

    @model_validator(mode="after")
    def check_cells(self):
        if sum(max(_matrix_cells(i.values), _matrix_cells(i.formulas)) for i in self.items) > MAX_CELLS:
            raise ValueError("The Office read exceeds the cell limit.")
        return self


class EditResult(OfficeResult):
    session: Identifier
    operation: Identifier
    outcome: Literal["applied", "unchanged"]
    affected_items: int = Field(ge=0, le=MAX_CELLS)
    recovery: Identifier | None = None

    @model_validator(mode="after")
    def check_outcome(self):
        if (self.outcome == "unchanged") != (self.affected_items == 0):
            raise ValueError("The edit outcome and affected count disagree.")
        return self


class SaveResult(OfficeResult):
    session: Identifier
    operation: Identifier
    saved: bool

    @model_validator(mode="after")
    def check_saved(self):
        if not self.saved:
            raise ValueError("A successful save receipt must confirm saving.")
        return self


@dataclass(frozen=True, slots=True)
class OfficeToolContract:
    name: str
    description: str
    arguments: type[OfficeModel]
    result: type[OfficeResult]
    permission: PermissionClass
    application: OfficeApplication | None = None

    def definition(self) -> ModelCapabilityDefinition:
        return ModelCapabilityDefinition(name=self.name, description=self.description,
                                         input_schema=self.arguments.model_json_schema())

    def validate_result(self, arguments: OfficeModel, value: dict) -> OfficeResult:
        """Validate bridge output against both the contract and the actual request.

        The adapter must additionally verify live identity, policy, snapshot scope,
        and execution evidence. A schema-valid receipt alone proves no side effect.
        """
        if not isinstance(arguments, self.arguments) or type(value) is not dict:
            raise ValueError("Office result validation requires this tool's arguments and a JSON object.")
        if len(canonical_json(value).encode("utf-8")) > MAX_RESULT_BYTES:
            raise ValueError("The Office result exceeds its byte limit.")
        result = self.result.model_validate(value)
        if hasattr(arguments, "session") and result.session != arguments.session:
            raise ValueError("The Office result belongs to another session.")
        if isinstance(arguments, DocumentsArguments):
            if len(result.documents) > arguments.limit or (
                arguments.application is not None and
                any(document.application != arguments.application for document in result.documents)
            ):
                raise ValueError("The document result exceeds the requested scope.")
        if isinstance(arguments, AttachArguments):
            if (result.document.document != arguments.document or
                    result.document.application != arguments.application):
                raise ValueError("The attachment result belongs to another document.")
        if isinstance(arguments, ReadArguments):
            count = sum(max(1, _matrix_cells(item.values), _matrix_cells(item.formulas))
                        for item in result.items)
            characters = sum(len(item.text or "") + sum(len(cell) for matrix in
                (item.values, item.formulas) if matrix is not None for row in matrix
                for cell in row if isinstance(cell, str)) for item in result.items)
            if count > arguments.max_items or characters > arguments.max_chars:
                raise ValueError("The Office read exceeds the requested item or character limit.")
        return result


OFFICE_TOOLS = tuple(sorted((
    OfficeToolContract("office.documents", "List open Office documents; metadata only.",
                       DocumentsArguments, DocumentsResult, PermissionClass.READ),
    OfficeToolContract("office.attach", "Attach to an exact open document without launching or saving.",
                       AttachArguments, AttachResult, PermissionClass.READ),
    OfficeToolContract("office.read", "Read a bounded target; returns an edit snapshot. Excel: start workbook-wide requests "
                       "with target=workbook for worksheet names and used extents, then use each returned SheetName!used "
                       "target to read the full used range. Explicit SheetName!A1:B2 and selection are also supported. "
                       "Results are pages, not the whole target: repeat the same session/target with cursor until null. "
                       "Used-range items pack row segments into typed matrices; labels identify their exact cell ranges. "
                       "Never derive whole-sheet KPIs from a preview or unfinished page sequence. "
                       "Word: document or text:start:end. PowerPoint: slides or slide:index.",
                       ReadArguments, ReadResult, PermissionClass.READ),
    OfficeToolContract("office.excel_edit", "Apply a bounded Excel patch against a complete matching cell snapshot. "
                       "Use this exact tool name. Existing sheets only; no worksheet creation. Supports values, "
                       "formulas referencing cells in this workbook (including other sheets), number_format, bold and italic. "
                       "Use linked formulas for dashboards, not static totals. SUMPRODUCT and NUMBERVALUE are supported. "
                       "Overlapping ranges may combine disjoint fields or identical assignments; conflicting assignments fail. "
                       "No fills, defined names or external references. Read every target cell first. Editing is not saving.",
                       ExcelEditArguments, EditResult, PermissionClass.WRITE, "excel"),
    OfficeToolContract("office.word_edit", "Apply bounded Word text, style or table edits against a snapshot.",
                       WordEditArguments, EditResult, PermissionClass.WRITE, "word"),
    OfficeToolContract("office.powerpoint_edit", "Edit slide text, layout or positions against a snapshot.",
                       PowerPointEditArguments, EditResult, PermissionClass.WRITE, "powerpoint"),
    OfficeToolContract("office.save", "Save the attached document; optional explicit Save As destination.",
                       SaveArguments, SaveResult, PermissionClass.WRITE),
    OfficeToolContract("office.revert", "Restore an owned edit only when its current target still matches.",
                       RevertArguments, EditResult, PermissionClass.WRITE),
), key=lambda tool: tool.name))


class OfficeExposure(OfficeModel):
    backend: Literal["local", "cloud"] = "local"
    enabled: bool = False
    ready: bool = False
    generation: int = Field(default=0, ge=0)
    applications: tuple[OfficeApplication, ...] = APPLICATIONS

    @model_validator(mode="after")
    def check_exposure(self):
        if len(set(self.applications)) != len(self.applications):
            raise ValueError("Office applications must not be duplicated.")
        if self.ready and self.generation == 0:
            raise ValueError("A ready Office connection needs a generation.")
        return self

    @property
    def eligible(self) -> bool:
        return self.backend == "cloud" and self.enabled and self.ready and bool(self.applications)


@dataclass(frozen=True, slots=True)
class OfficeCatalogSnapshot:
    exposure: OfficeExposure
    tools: tuple[OfficeToolContract, ...]
    schema_digest: str
    _definitions_json: str

    def model_definitions(self) -> tuple[ModelCapabilityDefinition, ...]:
        # Each reader receives fresh schemas; no caller can mutate the snapshot.
        return tuple(ModelCapabilityDefinition.model_validate(value)
                     for value in json.loads(self._definitions_json))

    def validate_call(self, name: str, arguments: dict, *, current: OfficeExposure) -> OfficeModel:
        if current != self.exposure or not current.eligible:
            raise ValueError("Office exposure changed; obtain a fresh turn catalog.")
        contract = next((tool for tool in self.tools if tool.name == name), None)
        if contract is None:
            raise ValueError("The Office tool is not enabled in this turn catalog.")
        if type(arguments) is not dict:
            raise ValueError("Office arguments must be a JSON object.")
        if len(canonical_json(arguments).encode("utf-8")) > MAX_ARGUMENT_BYTES:
            raise ValueError("The Office arguments exceed their byte limit.")
        result = contract.arguments.model_validate(arguments)
        application = getattr(result, "application", None)
        if application is not None and application not in current.applications:
            raise ValueError("The Office application is not enabled in this turn catalog.")
        return result


def office_catalog(exposure: OfficeExposure) -> OfficeCatalogSnapshot:
    if not isinstance(exposure, OfficeExposure):
        raise TypeError("Office catalogs require validated exposure state.")
    tools = tuple(tool for tool in OFFICE_TOOLS
                  if exposure.eligible and (tool.application is None or tool.application in exposure.applications))
    definitions = canonical_json([tool.definition().model_dump(mode="json") for tool in tools])
    return OfficeCatalogSnapshot(exposure, tools, sha256(definitions.encode()).hexdigest(), definitions)


def office_manifest() -> dict:
    """Content-free accepted contract identities; no transport or settings writes."""
    return {
        "schema_version": CONTRACT_VERSION,
        "transport": "stdio",
        "cloud_only": True,
        "max_argument_bytes": MAX_ARGUMENT_BYTES,
        "max_result_bytes": MAX_RESULT_BYTES,
        "max_changes": MAX_CHANGES,
        "max_cells": MAX_CELLS,
        "tools": [{"name": tool.name, "application": tool.application,
                   "permission": tool.permission.value,
                   "input_schema_sha256": sha256(canonical_json(tool.arguments.model_json_schema()).encode()).hexdigest(),
                   "output_schema_sha256": sha256(canonical_json(tool.result.model_json_schema()).encode()).hexdigest()}
                  for tool in OFFICE_TOOLS],
    }
