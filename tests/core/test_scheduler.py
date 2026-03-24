"""Tests for the cron-like scheduler."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from quartermaster.core.scheduler import ScheduleEntry, Scheduler


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.execute = AsyncMock(return_value=1)
    db.fetch_one = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_events() -> MagicMock:
    events = MagicMock()
    events.emit = AsyncMock()
    return events


def test_schedule_entry_creation() -> None:
    entry = ScheduleEntry(
        plugin_name="briefing",
        task_name="morning",
        cron_expression="30 6 * * *",
        event_name="schedule.briefing.morning",
    )
    assert entry.cron_expression == "30 6 * * *"
    assert entry.enabled is True


@pytest.mark.asyncio
async def test_register_schedule(mock_db: MagicMock, mock_events: MagicMock) -> None:
    scheduler = Scheduler(db=mock_db, events=mock_events, grace_minutes=15)
    scheduler.register(ScheduleEntry(
        plugin_name="briefing",
        task_name="morning",
        cron_expression="30 6 * * *",
        event_name="schedule.briefing.morning",
    ))
    assert len(scheduler.list_schedules()) == 1


@pytest.mark.asyncio
async def test_missed_event_within_grace_fires(mock_db: MagicMock, mock_events: MagicMock) -> None:
    scheduler = Scheduler(db=mock_db, events=mock_events, grace_minutes=15)
    entry = ScheduleEntry(
        plugin_name="briefing",
        task_name="morning",
        cron_expression="30 6 * * *",
        event_name="schedule.briefing.morning",
    )
    # Simulate a missed event 5 minutes ago
    entry.next_run_at = datetime.now(UTC) - timedelta(minutes=5)
    scheduler.register(entry)

    fired = await scheduler.check_missed_events()
    assert fired == 1
    mock_events.emit.assert_awaited_once()


@pytest.mark.asyncio
async def test_missed_event_beyond_grace_skips(mock_db: MagicMock, mock_events: MagicMock) -> None:
    scheduler = Scheduler(db=mock_db, events=mock_events, grace_minutes=15)
    entry = ScheduleEntry(
        plugin_name="briefing",
        task_name="morning",
        cron_expression="30 6 * * *",
        event_name="schedule.briefing.morning",
    )
    # Simulate a missed event 2 hours ago
    entry.next_run_at = datetime.now(UTC) - timedelta(hours=2)
    scheduler.register(entry)

    fired = await scheduler.check_missed_events()
    assert fired == 0
