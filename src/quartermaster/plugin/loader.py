"""Plugin discovery and lifecycle management."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

import structlog

from quartermaster.plugin.base import QuartermasterPlugin  # noqa: TCH001
from quartermaster.plugin.health import HealthReport, HealthStatus

if TYPE_CHECKING:
    from quartermaster.plugin.context import PluginContext

logger = structlog.get_logger()


class PluginLoader:
    """Discovers, validates, and lifecycle-manages plugins."""

    def __init__(self) -> None:
        self._classes: dict[str, type[QuartermasterPlugin]] = {}
        self._instances: OrderedDict[str, QuartermasterPlugin] = OrderedDict()

    def register_class(self, cls: type[QuartermasterPlugin]) -> None:
        """Register a plugin class for loading."""
        self._classes[cls.name] = cls

    def loaded_plugins(self) -> OrderedDict[str, QuartermasterPlugin]:
        """Return loaded plugin instances in load order."""
        return self._instances

    async def load_all(self, ctx: PluginContext) -> None:
        """Load all registered plugins in dependency order."""
        load_order = self._resolve_dependencies()

        for name in load_order:
            cls = self._classes[name]
            instance = cls()
            try:
                await instance.setup(ctx)
                self._instances[name] = instance
                logger.info("plugin_loaded", plugin=name, version=cls.version)
            except Exception:
                logger.exception("plugin_setup_failed", plugin=name)

    async def teardown_all(self) -> None:
        """Teardown all loaded plugins in reverse order."""
        for name in reversed(list(self._instances.keys())):
            try:
                await self._instances[name].teardown()
                logger.info("plugin_teardown", plugin=name)
            except Exception:
                logger.exception("plugin_teardown_failed", plugin=name)

    async def check_health(self) -> dict[str, HealthReport]:
        """Check health of all loaded plugins."""
        reports: dict[str, HealthReport] = {}
        for name, plugin in self._instances.items():
            try:
                reports[name] = await plugin.health()
            except Exception as exc:
                reports[name] = HealthReport(
                    status=HealthStatus.DOWN,
                    message=f"Health check failed: {exc}",
                )
        return reports

    def _resolve_dependencies(self) -> list[str]:
        """Topological sort of plugins by dependencies."""
        resolved: list[str] = []
        seen: set[str] = set()

        def visit(name: str) -> bool:
            if name in resolved:
                return True
            if name in seen:
                logger.warning("plugin_circular_dependency", plugin=name)
                return False
            if name not in self._classes:
                logger.warning("plugin_missing_dependency", plugin=name)
                return False

            seen.add(name)
            cls = self._classes[name]
            for dep in cls.dependencies:
                if not visit(dep):
                    logger.warning(
                        "plugin_skipped_missing_dep",
                        plugin=name,
                        missing=dep,
                    )
                    return False
            resolved.append(name)
            return True

        for name in list(self._classes.keys()):
            visit(name)

        return resolved
