"""Synthetic Excel state behind the real production STA, SDK and executor."""
import asyncio
from pathlib import Path
import re
import sys
import time

from app.mcp.office_contracts import excel_range_shape
from app.mcp.office_live import LiveOffice, OfficeSTA
from app.mcp.office_server import create_live_server, serve
from tests.fixtures.office_live_server import MemoryOffice


class MemoryExcel(MemoryOffice):
    def __init__(self, mode="normal"):
        super().__init__()
        self.docs = self.docs[:1]
        self.sheets = {"Sheet1": {}, "Other": {}}
        self.mode, self.writes = mode, 0

    def plan(self, kind, doc, target):
        self.check()
        sheet, address = target.rsplit("!", 1) if target != "selection" else ("Sheet1", "A1")
        sheet = sheet.strip("'").replace("''", "'")
        obj = self.sheets[sheet]
        rows, columns = excel_range_shape(address)
        match = re.match(r"\$?([A-Za-z]+)\$?([0-9]+)", address)
        left = 0
        for letter in match[1].upper():
            left = left * 26 + ord(letter) - 64
        return [("cell", obj, int(match[2]) + r, left + c) for r in range(rows) for c in range(columns)]

    def capture_excel(self, descriptor):
        self.check()
        _, sheet, row, column = descriptor
        return dict(sheet.get((row, column), {"value": None, "formula": "", "number_format": "General",
                                             "bold": False, "italic": False}))

    def excel_writable(self, document):
        self.check()

    def piece(self, descriptor, offset, chars):
        state = self.capture_excel(descriptor)
        if isinstance(state["value"], str) and len(state["value"]) > chars:
            text = state["value"][offset:offset + chars]
            return {"label": "Synthetic cell", "text": text}, offset + len(text) if offset + len(text) < len(state["value"]) else None
        return {"label": "Synthetic cell", "values": [[state["value"]]], "formulas": [[state["formula"]]]}, None

    def write_excel(self, descriptor, state, fields):
        self.check()
        self.writes += 1
        _, sheet, row, column = descriptor
        updated = dict(state)
        if "formula" in fields and state["formula"]:
            updated["value"] = 5 if state["formula"].upper() == "=2+3" else 2
        sheet[(row, column)] = updated
        if self.mode == "hang":
            time.sleep(60)
        if self.mode == "partial" and self.writes == 1:
            raise RuntimeError("SECRET-WRITE-EXCEPTION")
        if self.mode == "miswrite":
            sheet[(row, column)]["italic"] = not state["italic"]

    def save_excel(self, document, save, overwrite):
        self.check()
        Path(save["path"]).write_text("synthetic workbook", encoding="utf-8")
        document["path"] = save["path"]


class ExcelFixture(LiveOffice):
    def control(self, action, data):
        if action == "fixture-document":
            self.backend.docs[0]["path"] = data["path"]
            self.backend.docs[0]["name"] = Path(data["path"]).name
            return {"changed": True}
        if action == "fixture":
            descriptor = self.backend.plan("excel", self.backend.docs[0], data.get("target", "Sheet1!A1"))[0]
            state = self.backend.capture_excel(descriptor)
            state.update(data["change"])
            descriptor[1][descriptor[2:]] = state
            return {"changed": True}
        return super().control(action, data)


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
    sta = OfficeSTA(lambda: ExcelFixture(lambda: MemoryExcel(mode)))
    try:
        await serve(create_live_server(sta))
    finally:
        await sta.close()


if __name__ == "__main__":
    asyncio.run(main())
