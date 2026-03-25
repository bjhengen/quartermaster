"""Bidirectional MCP ↔ QM ToolDefinition translation.

This is the single translation point between MCP tool schemas
and Quartermaster's internal ToolDefinition format. Both client
and server use this module.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from mcp.types import CallToolResult, TextContent
from mcp.types import Tool as MCPTool

from quartermaster.core.tools import ApprovalTier, ToolDefinition, ToolHandler

logger = structlog.get_logger()


def mcp_tool_to_definition(
    tool: MCPTool,
    handler: ToolHandler,
    server_name: str,
    approval_tier: ApprovalTier,
    namespace: str | None = None,
) -> ToolDefinition:
    """Translate an MCP Tool schema to a QM ToolDefinition."""
    prefix = namespace or server_name
    name = f"{prefix}.{tool.name}"
    description = tool.description or f"Remote tool: {tool.name} (from {server_name})"
    parameters = tool.inputSchema if tool.inputSchema else {"type": "object", "properties": {}}

    return ToolDefinition(
        name=name,
        description=description,
        parameters=parameters,
        handler=handler,
        approval_tier=approval_tier,
        source=server_name,
        metadata={"mcp_server": server_name, "mcp_original_name": tool.name},
    )


def definition_to_mcp_tool(defn: ToolDefinition) -> MCPTool:
    """Translate a QM ToolDefinition to an MCP Tool schema."""
    return MCPTool(
        name=defn.name,
        description=defn.description,
        inputSchema=defn.parameters if defn.parameters else {"type": "object", "properties": {}},
    )


def mcp_result_to_dict(result: CallToolResult) -> dict[str, Any]:
    """Translate an MCP CallToolResult to a plain dict."""
    if result.isError:
        texts = [c.text for c in result.content if isinstance(c, TextContent)]
        return {"error": " ".join(texts) if texts else "Unknown MCP tool error"}

    texts = [c.text for c in result.content if isinstance(c, TextContent)]
    if not texts:
        return {"result": "ok"}

    combined = "\n".join(texts)

    try:
        parsed = json.loads(combined)
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}
    except (json.JSONDecodeError, ValueError):
        return {"text": combined}


def dict_to_mcp_result(result: dict[str, Any]) -> list[TextContent]:
    """Translate a dict result to MCP TextContent list."""
    return [TextContent(type="text", text=json.dumps(result, default=str))]
