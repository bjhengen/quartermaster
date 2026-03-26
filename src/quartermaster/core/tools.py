"""Tool Registry — the central nervous system of Quartermaster."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from quartermaster.core.events import EventBus

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
    source: str = "local"

    @property
    def is_remote(self) -> bool:
        """True if this tool comes from a remote MCP server."""
        return self.source != "local"


class ToolRegistry:
    """Central registry for all tools.

    Tools are registered by plugins at startup. The LLM Router
    queries the registry for available tool schemas, and the
    Tool Executor dispatches calls through the registry.
    """

    def __init__(self, events: EventBus | None = None) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._events = events

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: ToolHandler,
        approval_tier: ApprovalTier = ApprovalTier.AUTONOMOUS,
        metadata: dict[str, Any] | None = None,
        source: str = "local",
    ) -> None:
        """Register a tool."""
        if name in self._tools:
            logger.warning("tool_name_collision", tool=name, source=source)
            return
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            approval_tier=approval_tier,
            metadata=metadata or {},
            source=source,
        )
        logger.info("tool_registered", tool=name, tier=approval_tier.value, source=source)
        self._emit_event("registered", name)

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        del self._tools[name]
        logger.info("tool_unregistered", tool=name)
        self._emit_event("unregistered", name)

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_by_source(self, source: str) -> list[ToolDefinition]:
        """List tools filtered by source."""
        return [t for t in self._tools.values() if t.source == source]

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get tool schemas in OpenAI function-calling format."""
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
        """Execute a tool by name."""
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' not found")
        try:
            return await tool.handler(params)
        except Exception as e:
            logger.exception("tool_execution_error", tool=name)
            return {"error": f"{type(e).__name__}: {e}"}

    def _emit_event(self, action: str, tool_name: str) -> None:
        """Emit a tools.registry_changed event if EventBus is available."""
        if self._events is None:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._events.emit(
                    "tools.registry_changed",
                    {"action": action, "tool": tool_name},
                )
            )
        except RuntimeError:
            # No running event loop (e.g., during sync test setup)
            pass
