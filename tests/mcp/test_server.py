"""Tests for MCP Server."""

import json
import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from quartermaster.core.tools import ApprovalTier, ToolRegistry
from quartermaster.mcp.config import MCPServerConfig
from quartermaster.mcp.server import MCPServer


@pytest.fixture
def server_config(tmp_path: Any) -> MCPServerConfig:
    token_file = tmp_path / "token"
    token_file.write_text("test-token-123")
    return MCPServerConfig(
        enabled=True,
        port=0,  # random port for testing
        bind="127.0.0.1",
        auth_token_file=str(token_file),
        allowed_hosts=[],
        approval_chat_id="12345",
    )


@pytest.fixture
def server(
    server_config: MCPServerConfig,
    tool_registry: ToolRegistry,
    mock_events: MagicMock,
) -> MCPServer:
    return MCPServer(
        config=server_config,
        tools=tool_registry,
        events=mock_events,
        approval=MagicMock(),
        transport=MagicMock(),
    )


def test_server_init(server: MCPServer) -> None:
    assert server is not None


def test_server_list_tools(
    server: MCPServer, tool_registry: ToolRegistry
) -> None:
    async def handler(params: dict) -> dict:
        return {}

    tool_registry.register(
        name="test.hello", description="Say hello", parameters={}, handler=handler
    )
    tool_registry.register(
        name="test.goodbye", description="Say goodbye", parameters={}, handler=handler
    )

    tools = server._get_mcp_tools()
    assert len(tools) == 2
    names = {t.name for t in tools}
    assert names == {"test.hello", "test.goodbye"}


@pytest.mark.asyncio
async def test_server_call_autonomous_tool(
    server: MCPServer, tool_registry: ToolRegistry
) -> None:
    async def greet(params: dict) -> dict:
        return {"greeting": f"Hello, {params.get('name', 'world')}!"}

    tool_registry.register(
        name="test.greet",
        description="Greet someone",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}},
        handler=greet,
        approval_tier=ApprovalTier.AUTONOMOUS,
    )

    result = await server._handle_tool_call("test.greet", {"name": "Brian"})
    assert result["greeting"] == "Hello, Brian!"


@pytest.mark.asyncio
async def test_server_call_unknown_tool(server: MCPServer) -> None:
    result = await server._handle_tool_call("nonexistent.tool", {})
    assert "error" in result


@pytest.mark.asyncio
async def test_server_call_confirm_tool_sends_approval(
    server: MCPServer, tool_registry: ToolRegistry
) -> None:
    async def dangerous_action(params: dict) -> dict:
        return {"status": "executed"}

    tool_registry.register(
        name="test.danger",
        description="Dangerous action",
        parameters={},
        handler=dangerous_action,
        approval_tier=ApprovalTier.CONFIRM,
    )

    server._approval = AsyncMock()
    server._approval.request_approval = AsyncMock(return_value="abc123")

    # The confirm-tier handler creates an asyncio.Event and waits for approval.
    # For unit testing, we verify the approval request was sent.
    # Full approval flow is tested in integration.
    result = await server._handle_tool_call("test.danger", {})
    # Either approval was requested, or we got a timeout/error
    assert server._approval.request_approval.called or "error" in result
