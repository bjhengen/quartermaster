"""Tests for the commands plugin."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from plugins.commands.plugin import CommandsPlugin
from quartermaster.plugin.health import HealthStatus


def test_commands_plugin_metadata() -> None:
    plugin = CommandsPlugin()
    assert plugin.name == "commands"
    assert plugin.version == "0.1.0"


@pytest.mark.asyncio
async def test_commands_plugin_health() -> None:
    plugin = CommandsPlugin()
    report = await plugin.health()
    assert report.status == HealthStatus.OK


def test_commands_list() -> None:
    plugin = CommandsPlugin()
    assert "status" in plugin.commands
    assert "help" in plugin.commands
    assert "models" in plugin.commands
    assert "spend" in plugin.commands
    assert "new" in plugin.commands
