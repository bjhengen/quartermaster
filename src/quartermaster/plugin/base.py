"""Base class for all Quartermaster plugins."""

from __future__ import annotations

from typing import TYPE_CHECKING

from quartermaster.plugin.health import HealthReport, HealthStatus

if TYPE_CHECKING:
    from quartermaster.plugin.context import PluginContext


class QuartermasterPlugin:
    """Base class for all Quartermaster plugins."""

    name: str = ""
    version: str = "0.1.0"
    dependencies: list[str] = []

    async def setup(self, ctx: PluginContext) -> None:
        """Called once at startup."""

    async def teardown(self) -> None:
        """Called on shutdown."""

    async def health(self) -> HealthReport:
        """Return current health status."""
        return HealthReport(status=HealthStatus.OK)
