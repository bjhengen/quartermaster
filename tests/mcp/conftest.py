"""Shared fixtures for MCP tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from quartermaster.core.tools import ToolRegistry


@pytest.fixture
def mock_events() -> MagicMock:
    events = MagicMock()
    events.emit = AsyncMock()
    events.subscribe = MagicMock()
    return events


@pytest.fixture
def tool_registry(mock_events: MagicMock) -> ToolRegistry:
    return ToolRegistry(events=mock_events)
