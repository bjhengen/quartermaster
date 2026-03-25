"""Transport message types."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TransportType(StrEnum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    WEBHOOK = "webhook"
    MCP = "mcp"


@dataclass
class InboundMessage:
    """A message received from a transport."""

    transport: TransportType
    chat_id: str
    user_id: str
    text: str
    message_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage:
    """A message to send via a transport."""

    transport: TransportType
    chat_id: str
    text: str
    reply_to_message_id: str | None = None
    inline_keyboard: list[list[dict[str, str]]] = field(default_factory=list)
    voice_data: bytes | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
