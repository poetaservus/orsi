"""Synthetic Word state behind the production SDK, STA and executor."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys

from app.mcp.office_excel import OfficeConflict
from app.mcp.office_live import LiveOffice, OfficeSTA
from app.mcp.office_server import create_live_server, serve
from app.mcp.office_word_native import slice_units, units
from tests.fixtures.office_live_server import MemoryOffice


class MemoryWord(MemoryOffice):
    def __init__(self, mode="normal"):
        super().__init__()
        self.docs = [{"kind": "word", "name": "Synthetic Word document", "value": "alpha\U0001f642 beta", "path": None}]
        self.props, self.mode, self.writes = ["rPr", {"bold": True}, "", []], mode, 0
        self.anchors = []

    def word_descriptor(self, document, start, end):
        anchor = {"start": start, "end": end}
        self.anchors.append(anchor)
        return "word", document, start, end, anchor

    def plan(self, kind, document, target):
        self.check()
        start, end = (map(int, target.split(":")[1:]) if target.startswith("text:") else (0, units(document["value"])))
        return [self.word_descriptor(document, start, end)]

    def word_writable(self, document):
        self.check()
        if document.get("readonly"):
            raise OfficeConflict("Word fixture is read-only.")

    def capture_word(self, descriptor):
        self.check()
        _, document, start, end, anchor = descriptor
        if (anchor["start"], anchor["end"]) != (start, end):
            raise OfficeConflict("The Word anchor moved.")
        text = slice_units(document["value"], start, end)
        if not text:
            raise OfficeConflict("Read nonempty text.")
        return {"start": start, "end": end, "pstart": 0, "pend": units(document["value"]) + 1,
                "text": text, "target": [{}, None, [[deepcopy(self.props), text]]],
                "paragraph": [{}, None, [[deepcopy(self.props), document["value"]]]],
                "paragraph_text": document["value"] + "\r", "dependencies": "styles", "uniform": True}

    def piece(self, descriptor, offset, chars):
        self.check()
        _, document, start, end, anchor = descriptor
        if (anchor["start"], anchor["end"]) != (start, end):
            raise OfficeConflict("The Word anchor moved.")
        text = slice_units(document["value"], start, end)
        # max_chars counts Unicode characters; the continuation uses native units.
        remaining = slice_units(text, offset, units(text))
        piece = remaining[:chars]
        next_offset = offset + units(piece)
        return {"label": f"text:{start + offset}:{start + next_offset}", "text": piece}, (next_offset if next_offset < end - start else None)

    def write_word(self, descriptor, state):
        self.check()
        self.writes += 1
        descriptor[1]["value"] = state["paragraph_text"][:-1]
        if self.mode == "partial":
            raise RuntimeError("SECRET-COM-DESCRIPTION")
        if self.mode == "miswrite":
            self.props = None
        return self.word_descriptor(descriptor[1], state["start"], state["end"])

    def save_word(self, document, save):
        self.check()
        Path(save["path"]).write_bytes(b"Synthetic Word file")
        document["path"], document["name"] = save["path"], Path(save["path"]).name


class WordFixture(LiveOffice):
    def control(self, action, data):
        if action == "fixture-document":
            self.backend.docs[0]["path"] = data["path"]
            return {"changed": True}
        if action == "fixture":
            self.backend.docs[0].update(data)
            return {"changed": True}
        return super().control(action, data)


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
    sta = OfficeSTA(lambda: WordFixture(lambda: MemoryWord(mode)))
    try:
        await serve(create_live_server(sta))
    finally:
        await sta.close()


if __name__ == "__main__":
    asyncio.run(main())
