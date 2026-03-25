"""LLM request/response types."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    """A single message in a conversation."""

    role: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolCall:
    """A tool call from the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMRequest:
    """Request to an LLM backend."""

    messages: list[ChatMessage]
    tools: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class LLMResponse:
    """Response from an LLM backend."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    estimated_cost: float = 0.0
