"""Conversation data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Turn:
    """A single turn in a conversation."""

    turn_id: str = ""
    conversation_id: str = ""
    role: str = ""
    content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    llm_backend: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    estimated_cost: float = 0.0
    created_at: datetime | None = None


@dataclass
class Conversation:
    """A conversation session."""

    conversation_id: str = ""
    transport: str = ""
    external_chat_id: str = ""
    created_at: datetime | None = None
    last_active_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
