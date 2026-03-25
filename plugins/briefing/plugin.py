"""Briefing plugin — scheduled daily briefings."""

from typing import Any

import structlog

from plugins.briefing.templates import format_morning_briefing
from quartermaster.core.scheduler import ScheduleEntry
from quartermaster.plugin.base import QuartermasterPlugin
from quartermaster.plugin.context import PluginContext
from quartermaster.plugin.health import HealthReport, HealthStatus
from quartermaster.transport.types import OutboundMessage, TransportType

logger = structlog.get_logger()


class BriefingPlugin(QuartermasterPlugin):
    """Provides scheduled briefings (morning, evening)."""

    name = "briefing"
    version = "0.1.0"
    dependencies: list[str] = []

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None

    async def setup(self, ctx: PluginContext) -> None:
        self._ctx = ctx

        # Register morning briefing schedule
        if ctx.scheduler:
            ctx.scheduler.register(
                ScheduleEntry(
                    plugin_name="briefing",
                    task_name="morning",
                    cron_expression="30 6 * * *",  # 6:30 AM
                    event_name="schedule.briefing.morning",
                )
            )

        ctx.events.subscribe("schedule.briefing.morning", self._deliver_morning_briefing)
        logger.info("briefing_plugin_ready")

    async def teardown(self) -> None:
        pass

    async def health(self) -> HealthReport:
        return HealthReport(status=HealthStatus.OK)

    async def _deliver_morning_briefing(self, data: dict[str, Any]) -> None:
        """Deliver the morning briefing."""
        assert self._ctx is not None

        # Phase 1: just a skeleton — later phases will gather real data
        sections = {
            "System": ["All services running", "No alerts"],
            "Schedule": ["No events today"],
        }

        text = format_morning_briefing(sections)

        # Send to all allowed user IDs
        for user_id in self._ctx.config.allowed_user_ids:
            await self._ctx.transport.send(
                OutboundMessage(
                    transport=TransportType.TELEGRAM,
                    chat_id=str(user_id),
                    text=text,
                )
            )
