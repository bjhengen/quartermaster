#!/usr/bin/env python3
"""Minimal MCP stdio server for integration testing.

Exposes a single 'echo' tool that returns its input.
"""

import asyncio
import json

from mcp.server.lowlevel.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("echo-test")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="echo",
            description="Echo back the input",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message to echo"},
                },
                "required": ["message"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None = None) -> list[TextContent]:
    if name == "echo":
        msg = (arguments or {}).get("message", "")
        return [TextContent(type="text", text=json.dumps({"echo": msg}))]
    return [TextContent(type="text", text=json.dumps({"error": "unknown tool"}))]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
