"""Synthetic read-only adapter exercising the production STA and private channel."""
import asyncio
from threading import get_ident

from app.mcp.office_live import LiveOffice, OfficeSTA
from app.mcp.office_server import create_live_server, serve


class MemoryOffice:
    def __init__(self):
        self.thread = get_ident()
        self.docs = [{"kind": "excel", "name": "Synthetic workbook", "value": "alpha", "path": None},
                     {"kind": "word", "name": "Synthetic document", "value": "beta", "path": None}]
        self.closed = False

    def check(self):
        assert get_ident() == self.thread

    def documents(self, enabled):
        self.check()
        return [(doc["kind"], doc) for doc in self.docs if doc["kind"] in enabled]

    def same(self, left, right):
        self.check()
        return left is right

    def alive(self, kind, doc):
        self.check()
        return any(doc is value for value in self.docs)

    def metadata(self, kind, doc):
        self.check()
        return {"title": doc["name"], "dirty": True, "read_only": False, "path": doc["path"]}

    def plan(self, kind, doc, target):
        self.check()
        if target == "invalid":
            raise ValueError("SECRET-COM-EXCEPTION")
        return [doc]

    def piece(self, descriptor, offset, chars):
        self.check()
        text = descriptor["value"][offset:offset + chars]
        return {"label": "Synthetic target", "text": text}, (
            offset + len(text) if offset + len(text) < len(descriptor["value"]) else None)

    def close(self):
        self.check()
        self.closed = True


async def main():
    sta = OfficeSTA(lambda: LiveOffice(MemoryOffice))
    try:
        await serve(create_live_server(sta))
    finally:
        await sta.close()


if __name__ == "__main__":
    asyncio.run(main())
