"""Real stdio SDK fixture, with synthetic in-memory document data only."""
import asyncio
import os
import sys

from mcp.server.lowlevel import Server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from app.mcp.office_contracts import OFFICE_TOOLS
from app.mcp.office_server import create_server, serve


MODE = sys.argv[1] if len(sys.argv) > 1 else "normal"
STATE = {"value": 1, "version": 1}
DOCUMENT = {"document": "d1", "application": "excel", "title": "Synthetic workbook",
            "dirty": True, "has_path": False, "read_only": False}


async def handle(contract, arguments, meta):
    if MODE == "hang_call" or (MODE == "hang_write" and contract.permission.value == "write"):
        await asyncio.sleep(60)
    if MODE == "crash_call" or (MODE == "crash_write" and contract.permission.value == "write"):
        os._exit(7)
    if MODE == "bad_result":
        return CallToolResult(content=[TextContent(text="SECRET-FIXTURE")],
                              structuredContent={"unexpected": "SECRET-FIXTURE"})
    name = contract.name
    if name == "office.documents":
        output = {"documents": [DOCUMENT]}
    elif name == "office.attach":
        output = {"session": "s1", "document": DOCUMENT}
    elif name == "office.read":
        output = {"session": "s1", "application": "excel", "snapshot": "snap" + str(STATE["version"]),
                  "items": [{"target": "r1", "label": "Sheet1 A1", "values": [[STATE["value"]]]}]}
    elif name == "office.excel_edit":
        if arguments.snapshot != "snap" + str(STATE["version"]):
            return CallToolResult(isError=True, content=[TextContent(text="Changed target.")])
        values = arguments.changes[0].values
        if values is not None:
            STATE["value"] = values[0][0]
        STATE["version"] += 1
        output = {"session": "s1", "operation": meta["orsiOperation"],
                  "outcome": "applied", "affected_items": 1, "recovery": "rec1"}
    elif name == "office.save":
        output = {"session": "s1", "operation": meta["orsiOperation"], "saved": True}
    else:
        return CallToolResult(isError=True, content=[TextContent(text="Unsupported fixture operation.")])
    return CallToolResult(content=[TextContent(text="Duplicate content is deliberately not forwarded.")],
                          structuredContent=output)


async def main():
    if MODE == "hang_start":
        await asyncio.sleep(60)
    if MODE == "oversized_frame":
        os.write(1, b"X" * 70_000 + b"\n")
        await asyncio.sleep(60)
    if MODE in {"bad_schema", "extra_tool"}:
        async def list_tools(context, params):
            tools = [Tool(name=t.name, inputSchema=t.arguments.model_json_schema(),
                          outputSchema=t.result.model_json_schema()) for t in OFFICE_TOOLS]
            if MODE == "bad_schema":
                tools[0].input_schema["additionalProperties"] = True
            else:
                tools.append(Tool(name="shell.run", inputSchema={"type": "object"}))
            return ListToolsResult(tools=tools)
        server = Server("orsi-office", version="1", on_list_tools=list_tools)
    else:
        server = create_server(handler=handle)
    await serve(server)


if __name__ == "__main__":
    asyncio.run(main())
