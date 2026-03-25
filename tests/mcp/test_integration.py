"""Integration tests for MCP infrastructure.

Tests the full round-trip: Tool Registry → bridge → transport → protocol.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from quartermaster.core.tools import ToolRegistry
from quartermaster.mcp.client import MCPClientManager
from quartermaster.mcp.config import MCPClientEntry, MCPConfig, TransportType


ECHO_SERVER = str(Path(__file__).parent.parent / "fixtures" / "echo_server.py")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_stdio_echo_server_round_trip() -> None:
    """Connect to the echo test server via stdio and call a tool."""
    events = MagicMock()
    events.emit = AsyncMock()
    events.subscribe = MagicMock()

    tools = ToolRegistry(events=events)

    config = MCPConfig(
        clients={
            "echo": MCPClientEntry(
                transport=TransportType.STDIO,
                command=sys.executable,
                args=[ECHO_SERVER],
                default_approval_tier="autonomous",
                enabled=True,
            ),
        },
    )

    mgr = MCPClientManager(config=config, tools=tools, events=events)
    await mgr.start()

    try:
        # Tool should be registered
        tool = tools.get("echo.echo")
        assert tool is not None
        assert tool.source == "echo"
        assert tool.is_remote is True

        # Call the tool
        result = await tools.execute("echo.echo", {"message": "hello"})
        assert result == {"echo": "hello"}
    finally:
        await mgr.stop()

    # Tool should be unregistered after stop
    assert tools.get("echo.echo") is None
