"""Async event bus for inter-component communication."""

from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

logger = structlog.get_logger()

EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus:
    """Async publish/subscribe event bus.

    At-most-once delivery. Handler crashes are caught and logged,
    not propagated to other handlers.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event: str, handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        """Remove a handler for an event type."""
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: str, data: dict[str, Any]) -> None:
        """Emit an event to all registered handlers.

        Handlers run concurrently. Exceptions in one handler
        do not affect others.
        """
        handlers = self._handlers.get(event, [])
        if not handlers:
            return

        for handler in handlers:
            try:
                await handler(data)
            except Exception:
                logger.exception(
                    "event_handler_error",
                    event_type=event,
                    handler=handler.__qualname__,
                )

    def list_events(self) -> list[str]:
        """Return all event types with registered handlers."""
        return list(self._handlers.keys())
