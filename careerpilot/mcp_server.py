"""MCP server exposing careerpilot.api.TOOLS (stdio).

Plug it into Claude Desktop, Claude Code, or your future Jarvis:
  {"mcpServers": {"careerpilot": {"command": "python", "args": ["-m", "careerpilot", "mcp"], "cwd": "<repo>"}}}
Approving / submitting applications is intentionally not exposed.
Works with the `mcp` package 1.x (decorators) and 2.x (constructor handlers).
"""
import json

from . import api


def _tools(types):
    return [types.Tool(name=t["name"], description=t["description"], inputSchema=t["input_schema"]) for t in api.TOOLS]


def _text(types, name, arguments):
    return [types.TextContent(type="text", text=json.dumps(api.call(name, arguments or {}), default=str))]


def main():
    import anyio
    import mcp.types as types
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server

    if hasattr(Server, "list_tools"):  # mcp 1.x
        server = Server("careerpilot")
        server.list_tools()(lambda: _async(_tools(types)))

        @server.call_tool()
        async def call_tool(name, arguments):
            return _text(types, name, arguments)
    else:  # mcp 2.x
        async def on_list_tools(ctx, params):
            return types.ListToolsResult(tools=_tools(types))

        async def on_call_tool(ctx, params):
            return types.CallToolResult(content=_text(types, params.name, params.arguments))

        server = Server("careerpilot", on_list_tools=on_list_tools, on_call_tool=on_call_tool)

    async def run():
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())

    anyio.run(run)


async def _async(value):
    return value
