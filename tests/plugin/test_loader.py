"""Tests for plugin discovery and loading."""

from unittest.mock import MagicMock

import pytest

from quartermaster.plugin.base import QuartermasterPlugin
from quartermaster.plugin.context import PluginContext
from quartermaster.plugin.health import HealthReport, HealthStatus
from quartermaster.plugin.loader import PluginLoader


class FakePlugin(QuartermasterPlugin):
    name = "fake"
    version = "0.1.0"
    dependencies: list[str] = []

    async def setup(self, ctx: PluginContext) -> None:
        pass

    async def teardown(self) -> None:
        pass

    async def health(self) -> HealthReport:
        return HealthReport(status=HealthStatus.OK)


class DependentPlugin(QuartermasterPlugin):
    name = "dependent"
    version = "0.1.0"
    dependencies = ["fake"]

    async def setup(self, ctx: PluginContext) -> None:
        pass

    async def teardown(self) -> None:
        pass

    async def health(self) -> HealthReport:
        return HealthReport(status=HealthStatus.OK)


def test_health_status_values() -> None:
    assert HealthStatus.OK == "ok"  # type: ignore[comparison-overlap]
    assert HealthStatus.DEGRADED == "degraded"  # type: ignore[comparison-overlap]
    assert HealthStatus.DOWN == "down"  # type: ignore[comparison-overlap]


@pytest.mark.asyncio
async def test_load_plugin() -> None:
    loader = PluginLoader()
    loader.register_class(FakePlugin)
    ctx = MagicMock(spec=PluginContext)
    await loader.load_all(ctx)
    assert "fake" in loader.loaded_plugins()


@pytest.mark.asyncio
async def test_dependency_resolution_order() -> None:
    loader = PluginLoader()
    loader.register_class(DependentPlugin)
    loader.register_class(FakePlugin)
    ctx = MagicMock(spec=PluginContext)
    await loader.load_all(ctx)
    loaded = loader.loaded_plugins()
    assert list(loaded.keys()).index("fake") < list(loaded.keys()).index("dependent")


@pytest.mark.asyncio
async def test_missing_dependency_skips_plugin() -> None:
    loader = PluginLoader()
    loader.register_class(DependentPlugin)
    ctx = MagicMock(spec=PluginContext)
    await loader.load_all(ctx)
    assert "dependent" not in loader.loaded_plugins()


@pytest.mark.asyncio
async def test_plugin_health_check() -> None:
    loader = PluginLoader()
    loader.register_class(FakePlugin)
    ctx = MagicMock(spec=PluginContext)
    await loader.load_all(ctx)
    reports = await loader.check_health()
    assert "fake" in reports
    assert reports["fake"].status == HealthStatus.OK
