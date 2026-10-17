"""Word's narrower save choices, without changing the shared Office wire contract."""
from typing import Literal

from pydantic import Field

from app.mcp.office_contracts import OFFICE_TOOLS, SaveArguments


class WordSaveArguments(SaveArguments):
    path: str | None = Field(default=None, min_length=1, max_length=32_767,
        description="Null saves in place. Save As requires a new absolute .docx path; never repeat the current path.")
    overwrite: Literal[False] = Field(default=False,
        description="Always false. Word supports saving in place, not replacing another existing file.")


def word_save_definition():
    contract = next(tool for tool in OFFICE_TOOLS if tool.name == "office.save")
    return contract.definition().model_copy(update={
        "description": "Save the attached Word document. Use its office.attach session with path=null and overwrite=false to save in place. "
            "For Save As only, supply a new absolute .docx destination. No snapshot, document or recovery fields.",
        "input_schema": WordSaveArguments.model_json_schema(),
    })


def word_save_error_message(details):
    """Explain only allowlisted rules, never echo unknown keys or supplied values."""
    rules = []
    for detail in details:
        location, kind = detail.get("location", []), detail.get("type")
        field = location[0] if location else None
        if field == "session":
            rule = "session must be the unchanged identifier returned by office.attach"
        elif field == "path":
            rule = "path must be null for saving in place, or nonempty text for Save As"
        elif field == "overwrite" or (not location and kind == "value_error" and
                detail.get("message") == "Value error, Overwrite applies only to an explicit Save As destination."):
            rule = "overwrite must be false for Word"
        elif kind == "extra_forbidden":
            rule = "only session, path and overwrite are accepted; omit edit/snapshot fields"
        else:
            rule = "use the advertised save argument types"
        if rule not in rules:
            rules.append(rule)
    return ("Invalid Word save arguments: " + "; ".join(rules[:3]) +
        ". To save the attached document use its session, path=null, overwrite=false. "
        "No save was dispatched; retain completed edits and correct only the save request.")[:500]
