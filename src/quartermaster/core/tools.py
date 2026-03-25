"""Tool Registry — the central nervous system of Quartermaster."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger()

ToolHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


class ApprovalTier(StrEnum):
    """Approval tiers for tool execution."""

    AUTONOMOUS = "autonomous"
    CONFIRM = "confirm"
    NOTIFY = "notify"


@dataclass
class ToolDefinition:
    """A registered tool in the registry."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    approval_tier: ApprovalTier = ApprovalTier.AUTONOMOUS
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """Central registry for all tools.

    Tools are registered by plugins at startup. The LLM Router
    queries the registry for available tool schemas, and the
    Tool Executor dispatches calls through the registry.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: ToolHandler,
        approval_tier: ApprovalTier = ApprovalTier.AUTONOMOUS,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a tool."""
        if name in self._tools:
            raise ValueError(f"Tool '{name}' already registered")
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            approval_tier=approval_tier,
            metadata=metadata or {},
        )
        logger.info("tool_registered", tool=name, tier=approval_tier.value)

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get tool schemas in OpenAI function-calling format.

        Returns a list compatible with both llama-swap (OpenAI format)
        and Anthropic's tool_use format.
        """
        schemas: list[dict[str, Any]] = []
        for tool in self._tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return schemas

    async def execute(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name.

        Returns the tool's result dict. If the tool raises an exception,
        returns an error dict instead (so the LLM can handle it).
        """
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' not found")
        try:
            return await tool.handler(params)
        except Exception as e:
            logger.exception("tool_execution_error", tool=name)
            return {"error": f"{type(e).__name__}: {e}"}
