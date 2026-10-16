"""Office v1 contracts. Importing this module cannot connect or execute tools."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
Color = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
_WORD_TEXT_PATTERN = r"^[^\x00-\x1F]*$"
WordText = Annotated[str, Field(max_length=4_096, pattern=_WORD_TEXT_PATTERN)]
WordWidth = Annotated[float, Field(ge=5, le=400)]
WordMargin = Annotated[float, Field(ge=5, le=80)]
Matrix = Annotated[list[Annotated[list[Cell], Field(min_length=1, max_length=MAX_CELLS)]],
                   Field(min_length=1, max_length=MAX_CELLS)]
TextMatrix = Annotated[list[Annotated[list[Annotated[str, Field(max_length=4_096)]],
                                   Field(min_length=1, max_length=MAX_CELLS)]],
                       Field(min_length=1, max_length=MAX_CELLS)]
WordTextMatrix = Annotated[list[Annotated[list[WordText], Field(min_length=1, max_length=256)]],
                           Field(min_length=1, max_length=256)]
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
    fill_color: Color | Literal["none"] | None = None

    @model_validator(mode="after")
    def check_change(self):
        if self.values is not None and self.formulas is not None:
            raise ValueError("Literal values and formulas require separate changes.")
        if all(getattr(self, field) is None for field in
               ("values", "formulas", "number_format", "bold", "italic", "fill_color")):
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


class WordFormat(OfficeModel):
    font: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[^\x00-\x1F\x7F<>]+$")
    size: float | None = Field(default=None, ge=6, le=72, multiple_of=.5)
    color: Color | None = None
    bold: bool | None = None
    italic: bool | None = None
    alignment: Literal["left", "center", "right", "justify"] | None = None
    space_before: float | None = Field(default=None, ge=0, le=72)
    space_after: float | None = Field(default=None, ge=0, le=72)
    line_multiple: float | None = Field(default=None, ge=1, le=2)
    keep_with_next: bool | None = None


class WordParagraph(OfficeModel):
    kind: Literal["paragraph"] = "paragraph"
    text: WordText
    style: Literal["Normal", "Heading 1", "Heading 2", "Title", "Subtitle"] = "Normal"
    format: WordFormat | None = None
    page_break_before: bool = False


class WordTable(OfficeModel):
    kind: Literal["table"] = "table"
    cells: WordTextMatrix = Field(description="Rectangular; at most 256 cells in total.")
    widths_mm: list[WordWidth] = Field(min_length=1, max_length=16)
    header: bool = True
    header_fill: Color = "#E8EDF2"
    border_color: Color = "#CBD5E1"
    format: WordFormat | None = None

    @model_validator(mode="after")
    def check_table(self):
        if _matrix_cells(self.cells) > 256 or len(self.widths_mm) != len(self.cells[0]):
            raise ValueError("Word tables need one column width per column and at most 256 cells.")
        return self


class WordPageBreak(OfficeModel):
    # A missing discriminator previously made {} a schema-valid page break.
    # On the strict provider wire this also admitted {"kind": null}.
    kind: Literal["page_break"]


class WordPageLayout(OfficeModel):
    width_mm: float = Field(default=210, ge=100, le=420)
    height_mm: float = Field(default=297, ge=100, le=420)
    margins_mm: list[WordMargin] = Field(default_factory=lambda: [20, 20, 20, 20],
        min_length=4, max_length=4, description="Top, right, bottom, left; millimetres.")
    header_mm: float = Field(default=10, ge=0, le=50)
    footer_mm: float = Field(default=10, ge=0, le=50)

    @model_validator(mode="after")
    def check_area(self):
        top, right, bottom, left = self.margins_mm
        if (any(not 5 <= margin <= 80 for margin in self.margins_mm)
                or self.width_mm - left - right < 40 or self.height_mm - top - bottom < 40
                or self.header_mm >= top or self.footer_mm >= bottom):
            raise ValueError("Word layout requires usable body space and header/footer distances inside the margins.")
        return self


class WordComposeArguments(OfficeModel):
    session: Identifier
    snapshot: Identifier
    blocks: list[WordParagraph | WordTable | WordPageBreak] = Field(min_length=1, max_length=96)
    layout: WordPageLayout = Field(default_factory=WordPageLayout)
    format: WordFormat = Field(default_factory=WordFormat)
    header: str = Field(default="", max_length=512, pattern=_WORD_TEXT_PATTERN)
    footer: str = Field(default="", max_length=512, pattern=_WORD_TEXT_PATTERN)
    page_numbers: Literal["none", "page", "page_of_total"] = "page_of_total"

    @field_validator("blocks")
    @classmethod
    def normalize_page_breaks(cls, blocks):
        # Breaks delimit content pages. Boundary/repeated delimiters have no
        # content to separate; normalize the typed plan before approval/hash
        # binding, compilation and readback use it. Invalid blocks still fail
        # their own schema validation before reaching this step.
        normalized = []
        for block in blocks:
            if isinstance(block, WordPageBreak) and (
                    not normalized or isinstance(normalized[-1], WordPageBreak)):
                continue
            normalized.append(block)
        if normalized and isinstance(normalized[-1], WordPageBreak):
            normalized.pop()
        if not normalized:
            raise ValueError("Word composition requires paragraph or table content; supply the complete replacement body.")
        return normalized

    @model_validator(mode="after")
    def check_document(self):
        text = [self.header, self.footer]
        usable = self.layout.width_mm - self.layout.margins_mm[1] - self.layout.margins_mm[3]
        cells = 0
        for block in self.blocks:
            if isinstance(block, WordParagraph):
                text.append(block.text)
            elif isinstance(block, WordTable):
                text.extend(value for row in block.cells for value in row)
                cells += _matrix_cells(block.cells)
                if sum(block.widths_mm) > usable + .05:
                    raise ValueError("Word table widths exceed the printable body width.")
        if (cells > 512 or sum(isinstance(block, WordTable) for block in self.blocks) > 32
                or sum(len(value) for value in text) > 24000):
            raise ValueError("The Word document exceeds its bounded content limit.")
        if any(any(ord(char) < 32 for char in value) for value in text):
            raise ValueError("Use separate Word paragraph/page-break blocks; text cannot contain control markers.")
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


class ExcelSource(OfficeModel):
    snapshot: Identifier
    sheet: str = Field(min_length=1, max_length=128)
    range: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def check_range(self):
        excel_range_shape(self.range)
        return self


class ExcelChart(OfficeModel):
    kind: Literal["chart"]
    sheet: str = Field(min_length=1, max_length=128)
    name: Identifier
    geometry: Geometry
    source: ExcelSource
    chart_type: Literal["column", "bar", "line", "line_markers", "area", "pie", "doughnut", "scatter", "stacked_column"]
    title: str = Field(default="", max_length=256)
    legend: bool = True
    colors: list[Color] = Field(default_factory=list, max_length=8)


class ExcelShape(OfficeModel):
    kind: Literal["shape"]
    sheet: str = Field(min_length=1, max_length=128)
    name: Identifier
    geometry: Geometry
    shape_type: Literal["rectangle", "rounded_rectangle", "oval", "chevron", "up_arrow", "down_arrow"] = "rounded_rectangle"
    text: str | None = Field(default=None, max_length=4096)
    link: ExcelSource | None = None
    fill_color: Color | Literal["none"] = "#E7EEF5"
    line_color: Color | Literal["none"] = "none"
    font_color: Color = "#172B4D"
    font_size: float = Field(default=20, ge=6, le=100)
    bold: bool = False

    @model_validator(mode="after")
    def check_link(self):
        if self.link is not None and (self.text is not None or excel_range_shape(self.link.range) != (1, 1)):
            raise ValueError("A linked shape requires one source cell and no static text.")
        return self


class ExcelPivot(OfficeModel):
    kind: Literal["pivot"]
    sheet: str = Field(min_length=1, max_length=128)
    name: Identifier
    destination: str = Field(min_length=1, max_length=256)
    source: ExcelSource
    rows: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(min_length=1, max_length=4)
    value_field: str = Field(min_length=1, max_length=128)
    aggregate: Literal["sum", "count", "average", "min", "max"] = "sum"
    number_format: str = Field(default="#,##0.00", min_length=1, max_length=128)

    @model_validator(mode="after")
    def check_destination(self):
        excel_range_shape(self.destination)
        if len(set(self.rows)) != len(self.rows) or self.value_field in self.rows:
            raise ValueError("Pivot row fields and value field must be distinct.")
        return self


class ExcelSlicer(OfficeModel):
    kind: Literal["slicer"]
    sheet: str = Field(min_length=1, max_length=128)
    name: Identifier
    geometry: Geometry
    source: ExcelSource
    field: str = Field(min_length=1, max_length=128)
    caption: str = Field(default="", max_length=128)
    columns: int = Field(default=1, ge=1, le=4)
    style: Literal["light", "dark"] = "light"


class ExcelEditArguments(EditArguments):
    changes: list[ExcelChange] = Field(default_factory=list, max_length=MAX_CHANGES)
    objects: list[ExcelChart | ExcelShape | ExcelPivot | ExcelSlicer] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def check_cells(self):
        if not self.changes and not self.objects:
            raise ValueError("An Excel patch must contain changes or objects.")
        addresses = [c.range for c in self.changes] + [o.destination for o in self.objects if isinstance(o, ExcelPivot)]
        if sum(rows * columns for rows, columns in (excel_range_shape(a) for a in addresses)) + len(self.objects) > MAX_CELLS:
            raise ValueError("The Excel patch exceeds the cell limit.")
        return self


class WordEditArguments(EditArguments):
    changes: list[WordChange] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def check_cells(self):
        if sum(_matrix_cells(c.cells) for c in self.changes) > 64:
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
                       "target to read the full used range. SheetName!objects discovers chart/shape/slicer metadata and exact PivotTable output rectangles. Explicit SheetName!A1:B2 and selection are also supported. "
                       "Results are pages, not the whole target: repeat the same session/target with cursor until null. "
                       "Used-range items pack row segments into typed matrices; labels identify their exact cell ranges. "
                       "Never derive whole-sheet KPIs from a preview or unfinished page sequence. "
                       "Word: document, text:start:end, styles, tables or table:index; authoring reads complete report content/layout for word_compose, "
                       "layout returns native page count; render:first:last returns up to three actual page images for visual inspection. PowerPoint: slides or slide:index.",
                       ReadArguments, ReadResult, PermissionClass.READ),
    OfficeToolContract("office.excel_edit", "Apply a bounded Excel patch against a complete matching cell snapshot. "
                       "Use this exact tool name. Existing sheets only. Supports values, local formulas, number_format, bold, italic and fill_color (#RRGGBB/none). "
                       "Use linked formulas for dashboards, not static totals. SUMPRODUCT, NUMBERVALUE and GETPIVOTDATA are supported. "
                       "Overlapping ranges may combine disjoint fields or identical assignments; conflicting assignments fail. "
                       "objects creates up to 8 uniquely named native charts, shapes (optional linked cell), PivotTables and slicers. "
                       "Geometry is in worksheet points. Read destination A1 for drawing-sheet identity; read every pivot destination cell (blank reserved rectangle) and every source range completely. "
                       "Each source carries its own read snapshot. Charts use header/label columns; slicer source is an existing local PivotTable's full output rectangle. "
                       "Pivot reserve needs at least 2*(source rows-1)*row-field count+8 rows and row-field count+1 columns; no more than 1000 cells per patch. "
                       "Objects are created, not overwritten; revert removes only unchanged owned objects and restores the reserved pivot cells (read them again first). "
                       "No defined names, external data or references. Editing is not saving.",
                       ExcelEditArguments, EditResult, PermissionClass.WRITE, "excel"),
    OfficeToolContract("office.word_edit", "One fully read Word action per patch: replace_text or insert_after in a uniform body run (4096 UTF-16 units); "
                       "apply_style to a complete paragraph using a discovered style; edit_table replaces the exact matrix of a discovered simple fixed-layout table (64 cells). "
                       "Finish cursor pages. No structural markers, merged cells, fields or tracked changes. Preserves direct formatting; save separately. Read again before revert; Save As creates a new .docx.",
                       WordEditArguments, EditResult, PermissionClass.WRITE, "word"),
    OfficeToolContract("office.word_compose", "Replace ALL attached report body/header/footer content with native paragraphs, heading styles, editable tables and page breaks. "
                       "Read target=authoring completely first, including blanks; approval and owned recovery apply. "
                       "Set typography, spacing, millimetre layout, headers/footers and page numbers. No text boxes. "
                       "Use separate paragraph blocks; no newlines, tabs or controls in text/cells/header/footer. "
                       "Supply the full body; break-only plans cannot edit pagination. "
                       "Rectangular tables need one width per column; total widths must fit page width minus left/right margins (default 170 mm). "
                       "Header/footer distances must be below top/bottom margins. "
                       "After editing, read target=layout for actual page count and target=render:1:3 (up to three pages per call); inspect every page and correct layout, then save separately.",
                       WordComposeArguments, EditResult, PermissionClass.WRITE, "word"),
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
