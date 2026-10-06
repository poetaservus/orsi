"""Presentation-only activity updates, with no arguments or private content."""
import logging


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


def capability_activity(name):
    return _CAPABILITY_ACTIVITY.get(name, "Running a tool…")


def report_activity(observer, text):
    if observer is not None:
        try:
            observer(text)
        except Exception:
            # UI observers must never interrupt a request or tool settlement.
            log.warning("An activity display update failed.")
