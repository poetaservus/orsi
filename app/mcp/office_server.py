"""Bundled Office server; live controls are private to the local application."""
from __future__ import annotations

import asyncio
import json

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ReadResourceResult, TextResourceContents

from app.mcp.office_contracts import OFFICE_TOOLS
from app.mcp.office_excel import OfficeConflict, OfficeUnknown


def create_server(*, handler=None, control=None):
    async def list_tools(context, params):
        return ListToolsResult(tools=[Tool(name=tool.name, description=tool.description,
            inputSchema=tool.arguments.model_json_schema(), outputSchema=tool.result.model_json_schema())
            for tool in OFFICE_TOOLS])

    async def call_tool(context, params):
        contract = next((tool for tool in OFFICE_TOOLS if tool.name == params.name), None)
        if contract is None or handler is None:
            return CallToolResult(isError=True, content=[TextContent(text="Office live adapter is unavailable.")])
        try:
            arguments = contract.arguments.model_validate(params.arguments or {})
        except ValueError:
            return CallToolResult(isError=True, content=[TextContent(text="Invalid Office arguments.")])
        # Only trusted app composition may install a handler; model requests cannot.
        return await handler(contract, arguments, params.meta)

    async def read_resource(context, params):
        if control is None or not str(params.uri).startswith("orsi-office://local/"):
            raise ValueError("Unknown local resource.")
        action = str(params.uri).removeprefix("orsi-office://local/")
        data = params.meta.get("orsiControl", {}) if params.meta else {}
        try:
            result = await control(action, data)
        except OfficeConflict as error:
            result = {"error": "Office conflict: " + str(error), "code": "conflict"}
        except Exception:
            # COM/SDK exceptions may embed paths or document contents.
            result = {"error": "Office target is unavailable; refresh the connection or selection."}
        text = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(text.encode()) > 48000:
            text = '{"error":"Local Office response exceeded its bound."}'
        return ReadResourceResult(contents=[TextResourceContents(uri=str(params.uri),
                                  mimeType="application/json", text=text)])

    return Server("orsi-office", version="1", on_list_tools=list_tools, on_call_tool=call_tool,
                  on_read_resource=read_resource if control else None)


def create_live_server(sta):
    async def handler(contract, arguments, meta):
        authority = meta.get("orsiAuthority") if meta else None
        try:
            output = await sta.invoke("call", contract, arguments, authority, meta.get("orsiOperation") if meta else None)
            contract.validate_result(arguments, output)
            return CallToolResult(content=[], structuredContent=output)
        except OfficeConflict as error:
            return CallToolResult(isError=True, content=[TextContent(text="Office conflict; no write was started.")],
                                  meta={"orsiFailure": "conflict", "orsiMessage": "Office conflict: " + str(error)})
        except OfficeUnknown as error:
            return CallToolResult(isError=True, content=[TextContent(text="Office mutation outcome is uncertain; no automatic retry.")],
                meta={"orsiFailure": "unknown", "orsiStage": getattr(error, "stage", None),
                      "orsiHresult": getattr(error, "hresult", None), "orsiMismatch": getattr(error, "mismatch", [])})
        except Exception:
            return CallToolResult(isError=True, content=[TextContent(
                text="Office target is unavailable or changed; refresh the selection and read again.")])

    return create_server(handler=handler, control=lambda action, data: sta.invoke("control", action, data))


async def serve(server=None):
    from app.mcp.office_live import OfficeSTA
    sta = OfficeSTA() if server is None else None
    server = server or create_live_server(sta)
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        if sta is not None:
            await sta.close()


if __name__ == "__main__":
    asyncio.run(serve())
