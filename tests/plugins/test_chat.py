"""Tests for the chat plugin."""

import pytest

from plugins.chat.plugin import ChatPlugin
from plugins.chat.prompts import DEFAULT_PERSONA
from quartermaster.plugin.health import HealthStatus


def test_default_persona_exists() -> None:
    assert "Quartermaster" in DEFAULT_PERSONA


@pytest.mark.asyncio
async def test_chat_plugin_health() -> None:
    plugin = ChatPlugin()
    report = await plugin.health()
    assert report.status == HealthStatus.OK


def test_chat_plugin_metadata() -> None:
    plugin = ChatPlugin()
    assert plugin.name == "chat"
    assert plugin.version == "0.1.0"
