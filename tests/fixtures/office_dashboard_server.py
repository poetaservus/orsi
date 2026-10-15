"""Synthetic drawing backend behind the production stdio server and guard engine."""
import asyncio
from copy import deepcopy
import sys

from app.mcp.office_live import OfficeSTA
from app.mcp.office_server import create_live_server, serve
from tests.fixtures.office_excel_server import ExcelFixture, MemoryExcel


class DashboardBackend(MemoryExcel):
    def __init__(self, mode="normal"):
        super().__init__(mode)
        self.objects = {}

    def excel_drawing_writable(self, document, sheet):
        self.check()

    def excel_object_names(self, document, sheet):
        return {"names": sorted(self.objects), "shapes": [], "pivots": [], "slicer_caches": []}

    def create_excel_object(self, document, spec, sheet, source_sheet, pivot):
        self.writes += 1
        obj = {"spec": spec.model_dump(mode="json"), "name": spec.name}
        self.objects[spec.name] = obj
        if self.mode == "partial":
            raise RuntimeError("synthetic partial object creation")
        return obj, None

    def capture_excel_object(self, document, spec, obj, auxiliary):
        return deepcopy(obj)

    def verify_excel_object(self, spec, state):
        assert state["name"] == spec.name

    def excel_object_matches(self, document, spec, obj, auxiliary):
        return self.objects.get(spec.name) is obj

    def delete_excel_object(self, document, spec, obj, auxiliary):
        self.objects.pop(spec.name)


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
    sta = OfficeSTA(lambda: ExcelFixture(lambda: DashboardBackend(mode)))
    try:
        await serve(create_live_server(sta))
    finally:
        await sta.close()


if __name__ == "__main__":
    asyncio.run(main())
