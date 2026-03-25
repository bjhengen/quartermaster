"""Tests for MCP Client Manager."""

import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from mcp.types import Tool as MCPTool, ListToolsResult, CallToolResult, TextContent

from quartermaster.core.tools import ApprovalTier, ToolRegistry
from quartermaster.mcp.client import MCPClientManager
from quartermaster.mcp.config import MCPClientEntry, MCPConfig, TransportType, ToolOverride


@pytest.fixture
def mcp_config() -> MCPConfig:
    return MCPConfig(
        clients={
            "test-server": MCPClientEntry(
                transport=TransportType.STREAMABLE_HTTP,
                url="http://localhost:9999/mcp",
                default_approval_tier="confirm",
                enabled=True,
            ),
        },
    )


@pytest.fixture
def disabled_config() -> MCPConfig:
    return MCPConfig(
        clients={
            "disabled-server": MCPClientEntry(
                transport=TransportType.STREAMABLE_HTTP,
                url="http://localhost:9999/mcp",
                default_approval_tier="confirm",
                enabled=False,
            ),
        },
    )


@pytest.fixture
def override_config() -> MCPConfig:
    return MCPConfig(
        clients={
            "override-server": MCPClientEntry(
                transport=TransportType.STREAMABLE_HTTP,
                url="http://localhost:9999/mcp",
                default_approval_tier="autonomous",
                tool_overrides={
                    "dangerous_tool": ToolOverride(approval_tier="confirm"),
                    "hidden_tool": ToolOverride(enabled=False),
                },
                enabled=True,
            ),
        },
    )


def test_client_manager_init(
    tool_registry: ToolRegistry, mock_events: MagicMock, mcp_config: MCPConfig
) -> None:
    mgr = MCPClientManager(
        config=mcp_config,
        tools=tool_registry,
        events=mock_events,
    )
    assert mgr is not None


@pytest.mark.asyncio
async def test_register_tools_from_server(
    tool_registry: ToolRegistry, mock_events: MagicMock, mcp_config: MCPConfig
) -> None:
    mgr = MCPClientManager(
        config=mcp_config,
        tools=tool_registry,
        events=mock_events,
    )

    mock_tools = [
        MCPTool(
            name="search",
            description="Search things",
            inputSchema={"type": "object", "properties": {"q": {"type": "string"}}},
        ),
        MCPTool(
            name="list_items",
            description="List items",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]

    mock_session = AsyncMock()
    mock_session.list_tools = AsyncMock(
        return_value=ListToolsResult(tools=mock_tools)
    )

    await mgr._register_server_tools("test-server", mock_session, mcp_config.clients["test-server"])

    assert tool_registry.get("test-server.search") is not None
    assert tool_registry.get("test-server.list_items") is not None
    assert tool_registry.get("test-server.search").source == "test-server"
    assert tool_registry.get("test-server.search").approval_tier == ApprovalTier.CONFIRM


@pytest.mark.asyncio
async def test_approval_tier_override(
    tool_registry: ToolRegistry, mock_events: MagicMock, override_config: MCPConfig
) -> None:
    mgr = MCPClientManager(
        config=override_config,
        tools=tool_registry,
        events=mock_events,
    )

    mock_tools = [
        MCPTool(name="safe_tool", description="Safe", inputSchema={"type": "object", "properties": {}}),
        MCPTool(name="dangerous_tool", description="Dangerous", inputSchema={"type": "object", "properties": {}}),
        MCPTool(name="hidden_tool", description="Hidden", inputSchema={"type": "object", "properties": {}}),
    ]

    mock_session = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=ListToolsResult(tools=mock_tools))

    await mgr._register_server_tools(
        "override-server", mock_session, override_config.clients["override-server"]
    )

    assert tool_registry.get("override-server.safe_tool").approval_tier == ApprovalTier.AUTONOMOUS
    assert tool_registry.get("override-server.dangerous_tool").approval_tier == ApprovalTier.CONFIRM
    assert tool_registry.get("override-server.hidden_tool") is None


@pytest.mark.asyncio
async def test_unregister_server_tools(
    tool_registry: ToolRegistry, mock_events: MagicMock, mcp_config: MCPConfig
) -> None:
    mgr = MCPClientManager(
        config=mcp_config,
        tools=tool_registry,
        events=mock_events,
    )

    mock_tools = [
        MCPTool(name="tool_a", description="A", inputSchema={"type": "object", "properties": {}}),
    ]

    mock_session = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=ListToolsResult(tools=mock_tools))

    await mgr._register_server_tools("test-server", mock_session, mcp_config.clients["test-server"])
    assert tool_registry.get("test-server.tool_a") is not None

    mgr._unregister_server_tools("test-server")
    assert tool_registry.get("test-server.tool_a") is None


@pytest.mark.asyncio
async def test_disabled_server_skipped(
    tool_registry: ToolRegistry, mock_events: MagicMock, disabled_config: MCPConfig
) -> None:
    mgr = MCPClientManager(
        config=disabled_config,
        tools=tool_registry,
        events=mock_events,
    )
    enabled = mgr._get_enabled_entries()
    assert len(enabled) == 0


@pytest.mark.asyncio
async def test_name_collision_skips_remote(
    tool_registry: ToolRegistry, mock_events: MagicMock, mcp_config: MCPConfig
) -> None:
    async def handler(params: dict) -> dict:
        return {}

    tool_registry.register(
        name="test-server.search",
        description="Local version",
        parameters={},
        handler=handler,
    )

    mgr = MCPClientManager(
        config=mcp_config,
        tools=tool_registry,
        events=mock_events,
    )

    mock_tools = [
        MCPTool(name="search", description="Remote version", inputSchema={"type": "object", "properties": {}}),
    ]

    mock_session = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=ListToolsResult(tools=mock_tools))

    await mgr._register_server_tools("test-server", mock_session, mcp_config.clients["test-server"])

    tool = tool_registry.get("test-server.search")
    assert tool is not None
    assert tool.description == "Local version"
    assert tool.source == "local"


def test_get_server_statuses(
    tool_registry: ToolRegistry, mock_events: MagicMock, mcp_config: MCPConfig
) -> None:
    mgr = MCPClientManager(
        config=mcp_config,
        tools=tool_registry,
        events=mock_events,
    )
    statuses = mgr.get_server_statuses()
    assert "test-server" in statuses
    assert statuses["test-server"]["status"] == "disconnected"
