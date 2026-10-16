"""Fixed, bounded structural evidence across Word composition boundaries.

No input text, keys, paths, IDs, hashes or exception strings enter these logs.
The same summaries on consecutive retries reveal omissions without retaining
the proposal or conversation. Oversize/malformed inputs are sampled, never
serialized. This module deliberately has no Office/provider dependencies.
"""
import json
import logging


log = logging.getLogger(__name__)
_STAGES = frozenset({"provider_wire", "decoded_arguments", "validation_input",
    "validated_plan", "validation_rejected", "approval_serialized", "approval_plan", "dispatch_serialized"})
_LIMIT = 1_000_000


def word_plan_shape(value):
    def length(text):
        return min(len(text), _LIMIT) if isinstance(text, str) else 0

    value = value if isinstance(value, dict) else {}
    blocks = value.get("blocks")
    blocks = blocks if isinstance(blocks, list) else []
    pages = value.get("pages")
    if isinstance(pages, list):
        blocks = []
        for page in pages[:96]:
            content = page.get("blocks") if isinstance(page, dict) else None
            if not isinstance(content, list):
                continue
            blocks.extend(content[:96])
    sampled = blocks[:96]
    kinds, lengths, tables = [], [], []
    base_format = value.get("format")
    base_alignment = base_format.get("alignment") if isinstance(base_format, dict) else None
    justified = 0
    for block in sampled:
        block = block if isinstance(block, dict) else {}
        kind = block.get("kind")
        # Missing optional paragraph/table discriminators use the domain default.
        if kind is None:
            kind = "paragraph" if "text" in block else "table" if "cells" in block else "other" if block else "empty"
        if not isinstance(kind, str) or kind not in {"paragraph", "table", "page_break", "empty"}:
            kind = "other"
        kinds.append(kind)
        block_format = block.get("format")
        alignment = block_format.get("alignment") if isinstance(block_format, dict) else None
        justified += (alignment or base_alignment) == "justify"
        size = length(block.get("text"))
        if kind == "table":
            rows = block.get("cells")
            rows = rows if isinstance(rows, list) else []
            widths = [min(len(row), 256) if isinstance(row, list) else 0 for row in rows[:256]]
            size = min(sum(length(cell) for row in rows[:256] if isinstance(row, list)
                           for cell in row[:256]), _LIMIT)
            tables.append({"rows": min(len(rows), 257), "columns": max(widths, default=0),
                           "cells": sum(widths), "text_chars": size})
        lengths.append(size)
    return {"blocks": min(len(blocks), 97), "sampled_blocks": len(sampled),
        "planned_pages": min(len(pages), 97) if isinstance(pages, list) else
            1 + kinds.count("page_break") + sum(isinstance(b, dict) and b.get("page_break_before") is True for b in sampled),
        "kinds": kinds, "paragraphs": kinds.count("paragraph"), "tables": kinds.count("table"),
        "page_breaks": kinds.count("page_break"), "empty_blocks": kinds.count("empty"),
        "block_text_chars": lengths, "body_text_chars": min(sum(lengths), _LIMIT),
        "table_shapes": tables, "header_chars": length(value.get("header")),
        "footer_chars": length(value.get("footer")),
        "justified_blocks": justified,
        "page_break_before": sum(isinstance(b, dict) and b.get("page_break_before") is True for b in sampled)}


def record_word_plan(stage, value):
    if stage not in _STAGES:
        raise ValueError("Unknown Word diagnostic stage.")
    shape = word_plan_shape(value)
    log.info("word_compose stage=%s shape=%s", stage, json.dumps(shape, separators=(",", ":")),
             extra={"orsi_word_diagnostic": {"stage": stage, "shape": shape}})
    return shape


def safe_word_event(value):
    """Persist only known structure, independently of logging text/extras."""
    if not isinstance(value, dict) or not isinstance(value.get("stage"), str) or value["stage"] not in _STAGES:
        return None
    source = value.get("shape")
    if not isinstance(source, dict):
        return None
    shape = {}
    for key in ("blocks", "sampled_blocks", "planned_pages", "paragraphs", "tables", "page_breaks", "empty_blocks",
                "body_text_chars", "header_chars", "footer_chars", "justified_blocks", "page_break_before"):
        number = source.get(key)
        if type(number) is int and 0 <= number <= _LIMIT:
            shape[key] = number
    kinds = source.get("kinds")
    if isinstance(kinds, list):
        shape["kinds"] = [kind if isinstance(kind, str) and kind in {"paragraph", "table", "page_break", "empty", "other"}
                          else "other" for kind in kinds[:96]]
    lengths = source.get("block_text_chars")
    if isinstance(lengths, list):
        shape["block_text_chars"] = [min(number, _LIMIT) if type(number) is int and number >= 0 else 0 for number in lengths[:96]]
    tables = source.get("table_shapes")
    if isinstance(tables, list):
        shape["table_shapes"] = [{key: min(table[key], _LIMIT) for key in ("rows", "columns", "cells", "text_chars")
            if type(table.get(key)) is int and table[key] >= 0} for table in tables[:96] if isinstance(table, dict)]
    return {"event": "word_compose_structure", "stage": value["stage"], "shape": shape}
