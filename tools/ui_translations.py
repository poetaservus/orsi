"""Extract, validate and compile the offline interface catalogs (no network).

Run with the bundled Python. `--update` merges new English sources into the TS
files, preserving translated entries; `--compile` validates and invokes Qt's
bundled lrelease. Runtime users never need these build tools.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import copy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import string
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
CATALOGS = ROOT / "app/ui/translations"
REVIEW_RECORDS = ROOT / "docs/localization"

# Source phrases supplied through stable identifiers, data tables or helpers.
EXTRA_SOURCES = (
    "General", "Models", "Skills", "Image Generation", "Appearance", "Personal profile",
    "Text size", "Reduced motion", "High contrast", "Transparent background",
    "Storage", "Cloud access", "Backups", "Security", "Data", "Local", "Cloud", "Locked",
    "Exact diff", "File content", "Manage profile", "Lock", "New profile…", "Select existing…",
    "Use current unencrypted storage", "Local computer", "Portable drive", "Portable",
    "Ask whenever cloud is selected", "Allow explicitly saved encrypted credentials",
    "Ask whenever Cloud is selected", "Use saved encrypted credentials", "API key", "Login token",
    "Access token", "Refresh token", "Apply policy", "Save credential", "Delete saved key",
    "auto", "low", "medium", "high", "You", "Agent", "Saved.", "Not available",
    "OK", "Save", "Cancel", "Close", "Yes", "No", "Apply", "Reset",
    "None", "Low", "Medium", "High", "Extra High", "Max", "Reasoning",
    "Attach images or files", "Folder (placeholder)",
    "Image model", "Image size", "Quality", "File format", "Restore", "Maximize",
    "Generating image…", "Image generation finished", "Preview unavailable",
    "Checking skill…", "Installing…", "Removing…", "The skill operation could not be completed. Try again.",
    "copies", "days", "Managed backups", "Backup days", "Recovery key (optional)", "Delete profile permanently",
)

# App catalogs also cover the common Qt-owned actions. Other OS dialog chrome
# follows Windows; app-provided titles/prompts always follow the GUI selection.
QT_SOURCES = {
    "QPlatformTheme": ("OK", "Save", "Cancel", "Close", "Yes", "No", "Apply", "Reset",
    "None", "Low", "Medium", "High", "Extra High", "Max", "Reasoning",
    "Attach images or files", "Folder (placeholder)", "Open",
                       "&Yes", "&No", "&Open", "&Save", "&Cancel", "&Close"),
    "QLineEdit": ("&Undo", "&Redo", "Cu&t", "&Copy", "&Paste", "Delete", "Select All"),
    "QWidgetTextControl": ("&Undo", "&Redo", "Cu&t", "&Copy", "&Paste", "Delete", "Select All"),
    "QFileDialog": ("Look in:", "File &name:", "Files of type:", "Directory:", "&Open", "&Save",
                    "&Cancel", "Open", "Save As", "Choose", "Cancel", "File", "Folder",
                    "Show ", "Back", "Parent Directory", "Create New Folder", "List View", "Detail View",
                    "All Files (*)", "Name", "Size", "Type", "Date Modified", "Computer"),
}


@lru_cache(maxsize=1)
def sources():
    result = {"OrsiUI": set(EXTRA_SOURCES)}
    for path in (ROOT / "app/ui").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name in {"ui_text", "ApprovalSpec", "_button", "CopyButton", "_destination", "secret"} and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value:
                        result["OrsiUI"].add(arg.value)
                if name == "_perform" and len(node.args) > 1:
                    result["OrsiUI"].update(literal_choices(node.args[1]))
                if name == "folder_field":
                    for index in (1, 3):
                        if len(node.args) > index:
                            result["OrsiUI"].update(literal_choices(node.args[index]))
                if name == "combo" and node.args and isinstance(node.args[0], (ast.Tuple, ast.List)):
                    for pair in node.args[0].elts:
                        if isinstance(pair, (ast.Tuple, ast.List)) and isinstance(pair.elts[0], ast.Constant):
                            result["OrsiUI"].add(pair.elts[0].value)
            if path.name == "notifications.py" and isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == "EVENTS" for t in node.targets):
                    for pair in node.value.values:
                        result["OrsiUI"].update(item.value for item in pair.elts)
    tree = ast.parse((ROOT / "app/vault/profiles.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "public_error")
    for node in ast.walk(function):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            result["OrsiUI"].add(node.value.value)
    tree = ast.parse((ROOT / "app/vault/migration.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "CATEGORIES" for target in node.targets):
            result["OrsiUI"].update(value.value for value in node.value.values if isinstance(value, ast.Constant))
    result["OrsiUI"].update(value.removesuffix("…") for value in tuple(result["OrsiUI"]) if value.endswith("…"))
    result.update({context: set(values) for context, values in QT_SOURCES.items()})
    return {key: sorted(item for item in value if item) for key, value in result.items()}


def literal_choices(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return literal_choices(node.body) | literal_choices(node.orelse)
    return set()


@lru_cache(maxsize=1)
def optional_sources():
    """Pilot context: require complete coverage once a locale opts in.

    Absent locales keep their existing English output for these previously
    unmarked UI strings. Updating one pilot never rewrites other catalogs.
    """
    values = set()
    for path in (ROOT / "app/ui").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "ui_extra" and node.args:
                values.update(literal_choices(node.args[0]))
    return {"OrsiUIExtras": sorted(values)}


def structural(text):
    return not re.search(r"[\w]", re.sub(r"<[^>]+>|\{[^{}]+\}", "", text))


def fields(text):
    return Counter(field for _, field, _, _ in string.Formatter().parse(text) if field is not None)


PRESERVED_TERMS = ("DELETE", "O.R.S.I", "API", "JSON", "theme.json", "SKILL.md", "ORSI.cmd", "noti_1", "noti_2")


def catalog(code):
    return ET.parse(CATALOGS / f"{code}.ts")


def review_fingerprints(tree):
    entries = sorted((context.findtext("name"), message.findtext("source"), message.findtext("translation"))
                     for context in tree.getroot().findall("context") for message in context.findall("message"))
    def digest(values):
        return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"entry_count": len(entries), "source_sha256": digest([(context, source) for context, source, _ in entries]),
            "translation_sha256": digest(entries)}


def validate_review(code, tree):
    path = REVIEW_RECORDS / f"{code}-review.json"
    if not path.exists():
        return
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema_version") != 1 or record.get("language") != code:
        raise ValueError(f"Invalid editorial review record: {code}")
    if any(record.get(key) != value for key, value in review_fingerprints(tree).items()):
        raise ValueError(f"Editorial review is stale: {code}; review the changed copy and update its record before compiling")


def validate(code):
    tree = catalog(code)
    found = {}
    for context in tree.getroot().findall("context"):
        name = context.findtext("name")
        entries = found.setdefault(name, {})
        for message in context.findall("message"):
            source = message.findtext("source")
            translated = message.find("translation")
            if source in entries:
                raise ValueError(f"Duplicate translation: {code}/{name}/{source}")
            if translated is None or translated.get("type") in {"unfinished", "obsolete"} or not translated.text:
                raise ValueError(f"Unfinished translation: {code}/{name}/{source}")
            if fields(source) != fields(translated.text):
                raise ValueError(f"Translation placeholders differ: {code}/{name}/{source}")
            if re.search(r"987654\d+456789|876543\d+345678|ZPX\d+PZX|QZX\d+XZQ", translated.text):
                raise ValueError(f"Unresolved draft marker: {code}/{name}/{source}")
            if any(source.count(term) != translated.text.count(term) for term in PRESERVED_TERMS if term in source):
                raise ValueError(f"Translation changed a literal term: {code}/{name}/{source}")
            entries[source] = translated.text
    for context, expected in sources().items():
        if set(found.get(context, {})) != set(expected):
            raise ValueError(f"Translation coverage differs: {code}/{context}")
    for context, expected in optional_sources().items():
        if context in found and set(found[context]) != set(expected):
            raise ValueError(f"Pilot translation coverage differs: {code}/{context}")
    validate_review(code, tree)
    return tree


def update(code):
    path = CATALOGS / f"{code}.ts"
    previous = {}
    if path.exists():
        for context in catalog(code).getroot().findall("context"):
            for message in context.findall("message"):
                previous[(context.findtext("name"), message.findtext("source"))] = message
    root = ET.Element("TS", version="2.1", language=code, sourcelanguage="en")
    expected = sources() | {name: values for name, values in optional_sources().items()
                            if any(context == name for context, _ in previous)}
    for name, values in expected.items():
        context = ET.SubElement(root, "context")
        ET.SubElement(context, "name").text = name
        for value in values:
            message = ET.SubElement(context, "message")
            old = previous.get((name, value))
            if old is not None:
                for annotation in old:
                    if annotation.tag in {"location", "extracomment", "translatorcomment"}:
                        message.append(copy.deepcopy(annotation))
            ET.SubElement(message, "source").text = value
            text = old.findtext("translation") if old is not None else (value if code == "en" or structural(value) else None)
            attributes = dict(old.find("translation").attrib) if old is not None and old.find("translation") is not None else {}
            if not text:
                attributes["type"] = "unfinished"
            ET.SubElement(message, "translation", attributes).text = text
    ET.indent(root, space="  ")
    CATALOGS.mkdir(exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--language", action="append", help="Only validate/update/compile this code; repeat for several locales")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from app.conversation.response_language import RESPONSE_LANGUAGES
    codes = [language.code for language in RESPONSE_LANGUAGES if language.code != "auto"]
    if args.language:
        if any(code not in codes for code in args.language):
            parser.error("Unsupported language code")
        codes = list(dict.fromkeys(args.language))
    from PySide6 import __file__ as qt_file
    compiler = Path(qt_file).with_name("lrelease.exe" if sys.platform == "win32" else "lrelease")
    for code in codes:
        if args.update:
            update(code)
        if not args.update or args.compile:
            validate(code)
        if args.compile and code != "en":
            subprocess.run([str(compiler), "-silent", str(CATALOGS / f"{code}.ts"),
                            "-qm", str(CATALOGS / f"{code}.qm")], check=True)
    print(f"{len(codes)} catalog(s); {sum(len(v) for v in sources().values())} shared sources; "
          f"{sum(len(v) for v in optional_sources().values())} optional pilot sources")


if __name__ == "__main__":
    main()
