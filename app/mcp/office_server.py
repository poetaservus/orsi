"""Bundled stdio Office server shell. Live document adapters start in phase 3."""
from __future__ import annotations

import asyncio

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from app.mcp.office_contracts import OFFICE_TOOLS


def create_server(*, handler=None):
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

    return Server("orsi-office", version="1", on_list_tools=list_tools, on_call_tool=call_tool)


async def serve(server=None):
    server = server or create_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(serve())
