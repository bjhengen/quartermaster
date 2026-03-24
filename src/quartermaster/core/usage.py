"""API usage tracking and budget enforcement."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger()


class BudgetStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    BLOCKED = "blocked"


@dataclass
class UsageRecord:
    """A single API usage record."""

    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    estimated_cost: float
    purpose: str
    plugin_name: str


class UsageTracker:
    """Tracks API usage and enforces budget limits."""

    def __init__(
        self,
        db: Any,
        monthly_budget: float = 50.0,
        warn_percent: int = 80,
        block_percent: int = 100,
    ) -> None:
        self._db = db
        self._monthly_budget = monthly_budget
        self._warn_percent = warn_percent
        self._block_percent = block_percent

    async def log(self, record: UsageRecord) -> None:
        """Log a usage record to Oracle."""
        await self._db.execute(
            """INSERT INTO qm.usage_log
               (provider, model, tokens_in, tokens_out,
                estimated_cost, purpose, plugin_name)
               VALUES (:provider, :model, :tokens_in, :tokens_out,
                       :cost, :purpose, :plugin)""",
            {
                "provider": record.provider,
                "model": record.model,
                "tokens_in": record.tokens_in,
                "tokens_out": record.tokens_out,
                "cost": record.estimated_cost,
                "purpose": record.purpose,
                "plugin": record.plugin_name,
            },
        )
        logger.info(
            "usage_logged",
            provider=record.provider,
            model=record.model,
            cost=record.estimated_cost,
        )

    async def get_monthly_spend(self) -> float:
        """Get total spend for the current month."""
        row = await self._db.fetch_one(
            """SELECT COALESCE(SUM(estimated_cost), 0)
               FROM qm.usage_log
               WHERE created_at >= TRUNC(SYSDATE, 'MM')"""
        )
        return float(row[0]) if row else 0.0

    async def get_budget_status(self) -> BudgetStatus:
        """Check current budget status."""
        spend = await self.get_monthly_spend()
        pct = (spend / self._monthly_budget) * 100 if self._monthly_budget > 0 else 0

        if pct >= self._block_percent:
            return BudgetStatus.BLOCKED
        elif pct >= self._warn_percent:
            return BudgetStatus.WARNING
        return BudgetStatus.OK

    async def get_spend_summary(self) -> dict[str, Any]:
        """Get a formatted spend summary for /spend command."""
        spend = await self.get_monthly_spend()
        status = await self.get_budget_status()
        return {
            "monthly_spend": round(spend, 2),
            "monthly_budget": self._monthly_budget,
            "percent_used": round((spend / self._monthly_budget) * 100, 1),
            "status": status.value,
        }
