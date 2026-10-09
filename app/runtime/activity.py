"""Transient UI activity; file operations may show names, never file contents."""
import logging
from pathlib import PureWindowsPath


log = logging.getLogger(__name__)

_CAPABILITY_ACTIVITY = {
    "skill.read_reference": "Reading skill references…",
    "filesystem.stat": "Checking files…",
    "filesystem.find": "Finding files…",
    "filesystem.list": "Reading folder contents…",
    "filesystem.read_text": "Reading files…",
    "filesystem.search": "Searching file contents…",
    "filesystem.mkdir": "Creating a folder…",
    "filesystem.write_text": "Writing files…",
    "filesystem.edit_text": "Editing files…",
    "filesystem.copy": "Copying files…",
    "filesystem.move": "Moving files…",
    "filesystem.trash": "Moving files to the Recycle Bin…",
    "application.launch": "Opening an application…",
}


def capability_activity(name, arguments=None):
    # Read/source tools keep generic labels. Only mutation paths contribute names;
    # text, diffs, and other arguments must never enter the status or logs.
    arguments = arguments or {}
    if name in {"filesystem.copy", "filesystem.move"}:
        source = _display_path(arguments.get("source_path"))
        destination = _display_path(arguments.get("destination_path"))
        if source is not None and destination is not None:
            verb = "Copying" if name == "filesystem.copy" else "Moving"
            renamed = f" as {destination.name}" if source.name != destination.name else ""
            return (f"{verb} {source.name} from {source.parent.name or source.parent} "
                    f"to {destination.parent.name or destination.parent}{renamed}…")
    verbs = {
        "filesystem.mkdir": "Creating folder",
        "filesystem.write_text": "Writing",
        "filesystem.edit_text": "Editing",
        "filesystem.trash": "Recycling",
    }
    if name in verbs:
        path = _display_path(arguments.get("path"))
        if path is not None:
            return f"{verbs[name]} {path.name or path}…"
    return _CAPABILITY_ACTIVITY.get(name, "Running a tool…")


def _display_path(value):
    if isinstance(value, str) and value:
        return PureWindowsPath(value.translate(str.maketrans({
            character: " " for character in "\r\n\t\u2028\u2029"})))
    return None


def report_activity(observer, text):
    if observer is not None:
        try:
            observer(text)
        except Exception:
            # UI observers must never interrupt a request or tool settlement.
            log.warning("An activity display update failed.")
