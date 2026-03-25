"""Tests for MCP ↔ QM tool schema bridge."""


from mcp.types import Tool as MCPTool

from quartermaster.core.tools import ApprovalTier, ToolDefinition
from quartermaster.mcp.bridge import (
    definition_to_mcp_tool,
    dict_to_mcp_result,
    mcp_result_to_dict,
    mcp_tool_to_definition,
)


def test_mcp_tool_to_definition_basic() -> None:
    """Translate a basic MCP tool to a QM ToolDefinition."""
    mcp_tool = MCPTool(
        name="search",
        description="Search the memory",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    )

    async def mock_handler(params: dict) -> dict:
        return {}

    defn = mcp_tool_to_definition(
        tool=mcp_tool,
        handler=mock_handler,
        server_name="claude-memory",
        approval_tier=ApprovalTier.AUTONOMOUS,
    )

    assert defn.name == "claude-memory.search"
    assert defn.description == "Search the memory"
    assert defn.parameters["properties"]["query"]["type"] == "string"
    assert defn.source == "claude-memory"
    assert defn.approval_tier == ApprovalTier.AUTONOMOUS
    assert defn.is_remote is True


def test_mcp_tool_to_definition_custom_namespace() -> None:
    """Custom namespace overrides server name prefix."""
    mcp_tool = MCPTool(
        name="search",
        description="Search",
        inputSchema={"type": "object", "properties": {}},
    )

    async def mock_handler(params: dict) -> dict:
        return {}

    defn = mcp_tool_to_definition(
        tool=mcp_tool,
        handler=mock_handler,
        server_name="claude-memory",
        approval_tier=ApprovalTier.CONFIRM,
        namespace="mem",
    )

    assert defn.name == "mem.search"
    assert defn.source == "claude-memory"


def test_mcp_tool_to_definition_no_description() -> None:
    """MCP tool with no description gets a default."""
    mcp_tool = MCPTool(
        name="do_thing",
        inputSchema={"type": "object", "properties": {}},
    )

    async def mock_handler(params: dict) -> dict:
        return {}

    defn = mcp_tool_to_definition(
        tool=mcp_tool,
        handler=mock_handler,
        server_name="test",
        approval_tier=ApprovalTier.CONFIRM,
    )

    assert defn.description != ""  # Should have a default


def test_definition_to_mcp_tool() -> None:
    """Translate a QM ToolDefinition to an MCP Tool."""
    async def handler(params: dict) -> dict:
        return {}

    defn = ToolDefinition(
        name="commands.system_status",
        description="Get system status",
        parameters={
            "type": "object",
            "properties": {
                "verbose": {"type": "boolean", "default": False},
            },
            "required": [],
        },
        handler=handler,
    )

    mcp_tool = definition_to_mcp_tool(defn)

    assert mcp_tool.name == "commands.system_status"
    assert mcp_tool.description == "Get system status"
    assert mcp_tool.inputSchema["properties"]["verbose"]["type"] == "boolean"


def test_mcp_result_to_dict_text() -> None:
    """Translate MCP text result to dict."""
    from mcp.types import CallToolResult, TextContent

    result = CallToolResult(
        content=[TextContent(type="text", text='{"status": "ok"}')],
        isError=False,
    )
    d = mcp_result_to_dict(result)
    assert d == {"status": "ok"}


def test_mcp_result_to_dict_error() -> None:
    """Translate MCP error result to error dict."""
    from mcp.types import CallToolResult, TextContent

    result = CallToolResult(
        content=[TextContent(type="text", text="connection refused")],
        isError=True,
    )
    d = mcp_result_to_dict(result)
    assert "error" in d


def test_mcp_result_to_dict_non_json_text() -> None:
    """Non-JSON text result is wrapped in a text key."""
    from mcp.types import CallToolResult, TextContent

    result = CallToolResult(
        content=[TextContent(type="text", text="plain text response")],
        isError=False,
    )
    d = mcp_result_to_dict(result)
    assert d == {"text": "plain text response"}


def test_dict_to_mcp_result() -> None:
    """Translate dict result to MCP CallToolResult."""
    result = dict_to_mcp_result({"status": "ok", "count": 42})
    assert len(result) == 1
    assert result[0].type == "text"
    assert '"status"' in result[0].text
