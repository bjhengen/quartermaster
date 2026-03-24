"""Tests for API usage tracking and budget enforcement."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from quartermaster.core.usage import BudgetStatus, UsageRecord, UsageTracker


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(return_value=1)
    db.fetch_one = AsyncMock(return_value=(10.50,))
    return db


@pytest.mark.asyncio
async def test_log_usage(mock_db: MagicMock) -> None:
    tracker = UsageTracker(db=mock_db, monthly_budget=50.0)
    await tracker.log(UsageRecord(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        tokens_in=100,
        tokens_out=200,
        estimated_cost=0.003,
        purpose="chat",
        plugin_name="chat",
    ))
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_monthly_spend(mock_db: MagicMock) -> None:
    tracker = UsageTracker(db=mock_db, monthly_budget=50.0)
    spend = await tracker.get_monthly_spend()
    assert spend == 10.50


@pytest.mark.asyncio
async def test_budget_status_ok(mock_db: MagicMock) -> None:
    mock_db.fetch_one = AsyncMock(return_value=(10.0,))
    tracker = UsageTracker(db=mock_db, monthly_budget=50.0)
    status = await tracker.get_budget_status()
    assert status == BudgetStatus.OK


@pytest.mark.asyncio
async def test_budget_status_warning(mock_db: MagicMock) -> None:
    mock_db.fetch_one = AsyncMock(return_value=(42.0,))
    tracker = UsageTracker(db=mock_db, monthly_budget=50.0, warn_percent=80)
    status = await tracker.get_budget_status()
    assert status == BudgetStatus.WARNING


@pytest.mark.asyncio
async def test_budget_status_blocked(mock_db: MagicMock) -> None:
    mock_db.fetch_one = AsyncMock(return_value=(51.0,))
    tracker = UsageTracker(db=mock_db, monthly_budget=50.0)
    status = await tracker.get_budget_status()
    assert status == BudgetStatus.BLOCKED
