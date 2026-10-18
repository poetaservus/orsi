"""Bundled Office server; live controls are private to the local application."""
from __future__ import annotations

import asyncio
import json
from time import monotonic

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ReadResourceResult, TextResourceContents

from app.mcp.office_contracts import OFFICE_TOOLS, ReadArguments
from app.mcp.office_com import OfficeUnavailable
from app.mcp.office_read_diagnostics import failure_data, read_failure_message
from app.mcp.office_excel import OfficeConflict, OfficeUnknown
from app.mcp.office_word_render import WordRenderUnavailable


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
        from app.capabilities.contracts import PermissionClass
        from app.mcp.office_word import WordNotApplied
        from app.mcp.office_write_diagnostics import safe_write_event
        started = monotonic()
        authority = meta.get("orsiAuthority") if meta else None
        stage = "dispatch" if contract.permission == PermissionClass.WRITE else "read_execute"
        try:
            output = await sta.invoke("call", contract, arguments, authority, meta.get("orsiOperation") if meta else None)
            stage = "result_validation"
            contract.validate_result(arguments, output)
            diagnostic = getattr(sta, "last_write_diagnostic", None) if contract.permission == PermissionClass.WRITE else None
            return CallToolResult(content=[], structuredContent=output,
                meta={"orsiWriteDiagnostic": safe_write_event(diagnostic)} if diagnostic else None)
        except WordNotApplied as error:
            return CallToolResult(isError=True, content=[TextContent(text=str(error))],
                meta={"orsiFailure": "not_applied", "orsiWriteDiagnostic": error.diagnostic})
        except OfficeConflict as error:
            return CallToolResult(isError=True, content=[TextContent(text="Office conflict; no write was started.")],
                meta={"orsiFailure": "conflict", "orsiMessage": "Office conflict: " + str(error),
                      **({"orsiReadDiagnostic": failure_data(error, stage)} if isinstance(arguments, ReadArguments) else {})})
        except OfficeUnknown as error:
            return CallToolResult(isError=True, content=[TextContent(text="Office mutation outcome is uncertain; no automatic retry.")],
                meta={"orsiFailure": "unknown", "orsiStage": getattr(error, "stage", None),
                      "orsiHresult": getattr(error, "hresult", None), "orsiMismatch": getattr(error, "mismatch", []),
                      "orsiWriteDiagnostic": getattr(error, "diagnostic", None)})
        except WordRenderUnavailable as error:
            return CallToolResult(isError=True, content=[TextContent(text="Word page rendering is unavailable.")],
                meta={"orsiFailure": "read_setup", "orsiMessage": str(error),
                      "orsiReadDiagnostic": {**failure_data(error, stage), "reason": "render_setup"}})
        except Exception as error:
            if isinstance(arguments, ReadArguments):
                diagnostic = failure_data(error, stage)
                return CallToolResult(isError=True, content=[TextContent(
                    text=read_failure_message(arguments.model_dump(), diagnostic))],
                    meta={"orsiFailure": "read_unavailable" if isinstance(error, OfficeUnavailable) else "read_execution",
                          "orsiReadDiagnostic": diagnostic})
            if contract.permission == PermissionClass.WRITE:
                from app.mcp.office_write_diagnostics import category
                diagnostic = safe_write_event({"tool": contract.name, "stage": stage,
                    "category": category(error), "hresult": getattr(error, "hresult", None),
                    "duration_ms": round((monotonic() - started) * 1000), "outcome": "unknown"})
                return CallToolResult(isError=True, content=[TextContent(
                    text="Office write could not be confirmed. Inspect the document before another write.")],
                    meta={"orsiFailure": "unknown", "orsiWriteDiagnostic": diagnostic})
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
