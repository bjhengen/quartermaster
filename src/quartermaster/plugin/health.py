"""Plugin health check types."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class HealthReport:
    status: HealthStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
