"""Plugin context — provides access to core services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PluginContext:
    """Provides plugins access to core services."""

    config: Any  # QuartermasterConfig or plugin-specific section
    events: Any  # EventBus
    tools: Any  # ToolRegistry
    db: Any = None  # Database
    llm: Any = None  # LLMRouter
    transport: Any = None  # TransportManager
    scheduler: Any = None  # Scheduler
    approval: Any = None  # ApprovalManager
    usage: Any = None  # UsageTracker
    conversation: Any = None  # ConversationManager
    mcp_client: Any = None  # MCPClientManager
