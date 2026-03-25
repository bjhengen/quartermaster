"""Cron-like async scheduler."""

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from croniter import croniter  # type: ignore[import-untyped]

logger = structlog.get_logger()


@dataclass
class ScheduleEntry:
    """A registered scheduled task."""

    plugin_name: str
    task_name: str
    cron_expression: str
    event_name: str
    enabled: bool = True
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    last_status: str = ""
    consecutive_failures: int = 0
    config: dict[str, Any] = field(default_factory=dict)

    def compute_next_run(self) -> None:
        """Compute the next run time from the cron expression."""
        cron = croniter(self.cron_expression, datetime.now(UTC))
        self.next_run_at = cron.get_next(datetime).replace(tzinfo=UTC)


class Scheduler:
    """Cron-like scheduler with missed-event recovery."""

    def __init__(
        self,
        db: Any,
        events: Any,
        grace_minutes: int = 15,
    ) -> None:
        self._db = db
        self._events = events
        self._grace_minutes = grace_minutes
        self._entries: dict[str, ScheduleEntry] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def register(self, entry: ScheduleEntry) -> None:
        """Register a schedule entry."""
        key = f"{entry.plugin_name}.{entry.task_name}"
        if entry.next_run_at is None:
            entry.compute_next_run()
        self._entries[key] = entry
        logger.info("schedule_registered", key=key, cron=entry.cron_expression)

    def list_schedules(self) -> list[ScheduleEntry]:
        """Return all registered schedule entries."""
        return list(self._entries.values())

    async def check_missed_events(self) -> int:
        """Check for and fire missed events within the grace window."""
        now = datetime.now(UTC)
        grace = timedelta(minutes=self._grace_minutes)
        fired = 0

        for key, entry in self._entries.items():
            if not entry.enabled or entry.next_run_at is None:
                continue
            if entry.next_run_at > now:
                continue

            missed_by = now - entry.next_run_at
            if missed_by <= grace:
                logger.info("firing_missed_event", key=key, missed_by=str(missed_by))
                await self._fire(key, entry)
                fired += 1
            else:
                logger.info("skipping_old_event", key=key, missed_by=str(missed_by))
                entry.compute_next_run()

        return fired

    async def start(self) -> None:
        """Start the scheduler loop."""
        self._running = True
        await self.check_missed_events()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run_loop(self) -> None:
        """Main scheduler loop — check every 30 seconds."""
        while self._running:
            await asyncio.sleep(30)
            now = datetime.now(UTC)
            for key, entry in self._entries.items():
                if not entry.enabled or entry.next_run_at is None:
                    continue
                if entry.next_run_at <= now:
                    await self._fire(key, entry)

    async def _fire(self, key: str, entry: ScheduleEntry) -> None:
        """Fire a scheduled event."""
        try:
            await self._events.emit(
                entry.event_name,
                {
                    "schedule_key": key,
                    "plugin": entry.plugin_name,
                    "task": entry.task_name,
                },
            )
            entry.last_status = "success"
            entry.last_run_at = datetime.now(UTC)
            entry.consecutive_failures = 0
        except Exception:
            logger.exception("schedule_fire_error", key=key)
            entry.last_status = "failed"
            entry.consecutive_failures += 1
            if entry.consecutive_failures >= 3:
                logger.error(
                    "schedule_persistent_failure",
                    key=key,
                    failures=entry.consecutive_failures,
                )

        entry.compute_next_run()
