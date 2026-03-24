"""Tests for the async event bus."""

import pytest

from quartermaster.core.events import EventBus


@pytest.mark.asyncio
async def test_subscribe_and_emit() -> None:
    bus = EventBus()
    received: list[dict] = []

    async def handler(data: dict) -> None:
        received.append(data)

    bus.subscribe("test.event", handler)
    await bus.emit("test.event", {"key": "value"})
    assert len(received) == 1
    assert received[0] == {"key": "value"}


@pytest.mark.asyncio
async def test_multiple_subscribers() -> None:
    bus = EventBus()
    results: list[str] = []

    async def handler_a(data: dict) -> None:
        results.append("a")

    async def handler_b(data: dict) -> None:
        results.append("b")

    bus.subscribe("test.event", handler_a)
    bus.subscribe("test.event", handler_b)
    await bus.emit("test.event", {})
    assert sorted(results) == ["a", "b"]


@pytest.mark.asyncio
async def test_emit_no_subscribers_is_silent() -> None:
    bus = EventBus()
    # Should not raise
    await bus.emit("nobody.listening", {"data": 1})


@pytest.mark.asyncio
async def test_handler_crash_does_not_break_others() -> None:
    bus = EventBus()
    results: list[str] = []

    async def bad_handler(data: dict) -> None:
        raise RuntimeError("boom")

    async def good_handler(data: dict) -> None:
        results.append("ok")

    bus.subscribe("test.event", bad_handler)
    bus.subscribe("test.event", good_handler)
    await bus.emit("test.event", {})
    assert results == ["ok"]


@pytest.mark.asyncio
async def test_unsubscribe() -> None:
    bus = EventBus()
    received: list[dict] = []

    async def handler(data: dict) -> None:
        received.append(data)

    bus.subscribe("test.event", handler)
    bus.unsubscribe("test.event", handler)
    await bus.emit("test.event", {"key": "value"})
    assert len(received) == 0


@pytest.mark.asyncio
async def test_list_events() -> None:
    bus = EventBus()

    async def handler(data: dict) -> None:
        pass

    bus.subscribe("alpha", handler)
    bus.subscribe("beta", handler)
    assert sorted(bus.list_events()) == ["alpha", "beta"]
