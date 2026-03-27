"""Configuration models for Quartermaster."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from quartermaster.mcp.config import MCPConfig


class DatabaseConfig(BaseModel):
    """Oracle database connection configuration."""

    dsn: str
    user: str
    password: str
    pool_min: int = 2
    pool_max: int = 10


class LocalLLMConfig(BaseModel):
    """Local LLM (llama-swap) configuration."""

    base_url: str = "http://localhost:8200/v1"
    preferred_model: str = "qwen3.5-27b"
    timeout_seconds: int = 60
    swap_timeout_seconds: int = 120


class AnthropicConfig(BaseModel):
    """Anthropic API configuration."""

    api_key_file: str
    default_model: str = "claude-sonnet-4-20250514"
    fallback_model: str = "claude-haiku-4-5-20251001"


class LLMConfig(BaseModel):
    """LLM routing configuration."""

    local: LocalLLMConfig = Field(default_factory=LocalLLMConfig)
    anthropic: AnthropicConfig | None = None
    monthly_budget_usd: float = 50.0
    budget_warn_percent: int = 80
    budget_block_percent: int = 100


class SchedulerConfig(BaseModel):
    """Scheduler configuration."""

    missed_event_grace_minutes: int = 15


class ApprovalConfig(BaseModel):
    """Approval manager configuration."""

    default_timeout_minutes: int = 60


class MetricsConfig(BaseModel):
    """Prometheus metrics configuration."""

    port: int = 9100


class ConversationConfig(BaseModel):
    """Conversation manager configuration."""

    context_window_max_turns: int = 20
    context_window_max_tokens: int = 8000
    idle_timeout_hours: int = 4


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"


class EmailAccountConfig(BaseModel):
    """Configuration for a single email account."""

    provider: str  # "gmail", future: "outlook"
    credential_file: str
    label: str


class EmailConfig(BaseModel):
    """Email integration configuration."""

    accounts: dict[str, EmailAccountConfig] = {}


class QuartermasterConfig(BaseModel):
    """Root configuration model."""

    telegram_bot_token: str = ""
    allowed_user_ids: list[int] = Field(default_factory=list)
    database: DatabaseConfig = Field(
        default_factory=lambda: DatabaseConfig(dsn="", user="", password="")
    )
    llm: LLMConfig = Field(default_factory=LLMConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    conversation: ConversationConfig = Field(default_factory=ConversationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    persona: str = ""
    plugins_dir: str = "/app/plugins"


def load_config(path: Path) -> QuartermasterConfig:
    """Load configuration from a YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    qm_section = raw.get("quartermaster", {})
    return QuartermasterConfig(**qm_section)
