"""Transport manager — abstracts message delivery."""

from typing import Protocol

import structlog

from quartermaster.transport.types import (
    OutboundMessage,
    TransportType,
)

logger = structlog.get_logger()


class Transport(Protocol):
    """Protocol for transport implementations."""

    transport_type: TransportType

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, message: OutboundMessage) -> str: ...


class TransportManager:
    """Manages multiple transports and routes messages."""

    def __init__(self) -> None:
        self._transports: dict[TransportType, Transport] = {}

    def register(self, transport: Transport) -> None:
        """Register a transport."""
        self._transports[transport.transport_type] = transport
        logger.info("transport_registered", type=transport.transport_type.value)

    async def send(self, message: OutboundMessage) -> str:
        """Send a message via the appropriate transport."""
        transport = self._transports.get(message.transport)
        if transport is None:
            raise ValueError(f"No transport registered for {message.transport}")
        return await transport.send(message)

    async def start_all(self) -> None:
        """Start all registered transports."""
        for transport in self._transports.values():
            await transport.start()

    async def stop_all(self) -> None:
        """Stop all registered transports."""
        for transport in self._transports.values():
            await transport.stop()
