"""Tests for the briefing plugin skeleton."""

import pytest

from plugins.briefing.plugin import BriefingPlugin
from plugins.briefing.templates import format_briefing_section
from quartermaster.plugin.health import HealthStatus


def test_briefing_plugin_metadata() -> None:
    plugin = BriefingPlugin()
    assert plugin.name == "briefing"
    assert plugin.version == "0.1.0"


@pytest.mark.asyncio
async def test_briefing_plugin_health() -> None:
    plugin = BriefingPlugin()
    report = await plugin.health()
    assert report.status == HealthStatus.OK


def test_format_briefing_section() -> None:
    result = format_briefing_section("Weather", ["Sunny, 72°F", "No rain expected"])
    assert "Weather" in result
    assert "Sunny" in result
