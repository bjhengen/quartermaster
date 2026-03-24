# Quartermaster Phase 1 MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core Quartermaster bot — a Telegram-based personal AI assistant with smart LLM routing (llama-swap local + Anthropic fallback), Oracle 26ai persistence, plugin architecture with Tool Registry, and basic chat/commands/briefing plugins.

**Architecture:** Python 3.13 asyncio daemon in Docker (host networking). Plugin-based with central Tool Registry — the LLM is an orchestrator that selects tools, not a worker. Oracle 26ai PDB for all persistence. Event bus for inter-component communication.

**Tech Stack:** Python 3.13, python-telegram-bot, httpx, python-oracledb, pydantic v2, structlog, prometheus-client, anthropic SDK

**Spec:** `docs/superpowers/specs/2026-03-24-quartermaster-architecture-design.md`

---

## File Map

### Project Root
| File | Purpose |
|------|---------|
| `pyproject.toml` | Build config, mypy, ruff settings |
| `requirements.txt` | Production dependencies |
| `requirements-dev.txt` | Dev/test dependencies |
| `Dockerfile` | Container image |
| `docker-compose.yml` | Service definition |
| `.gitignore` | Exclude creds, logs, config |
| `CLAUDE.md` | Project-specific Claude instructions |
| `config/settings.example.yaml` | Config template for public repo |
| `scripts/setup_oracle_pdb.sql` | PDB + schema + table creation |
| `scripts/setup_test_pdb.sql` | Test PDB setup |

### Core (`src/quartermaster/core/`)
| File | Purpose |
|------|---------|
| `config.py` | Pydantic settings models (YAML → typed config) |
| `events.py` | Async event bus (pub/sub) |
| `database.py` | Oracle async connection pool |
| `tools.py` | Tool Registry (register, list, dispatch) |
| `scheduler.py` | Cron-like async scheduler |
| `approval.py` | 3-tier approval manager |
| `usage.py` | API cost tracking + budget enforcement |
| `metrics.py` | Prometheus `/metrics` endpoint |
| `app.py` | Application bootstrap + lifecycle |

### LLM (`src/quartermaster/llm/`)
| File | Purpose |
|------|---------|
| `models.py` | Request/response Pydantic types |
| `local.py` | llama-swap OpenAI-compatible client |
| `anthropic_client.py` | Anthropic SDK wrapper |
| `router.py` | Smart routing: check llama-swap → fallback |

### Transport (`src/quartermaster/transport/`)
| File | Purpose |
|------|---------|
| `types.py` | Message, User, Attachment Pydantic models |
| `manager.py` | Transport abstraction + dispatch |
| `telegram.py` | python-telegram-bot async handler |

### Conversation (`src/quartermaster/conversation/`)
| File | Purpose |
|------|---------|
| `models.py` | Conversation, Turn Pydantic models |
| `manager.py` | History loading, context window assembly |

### Plugin (`src/quartermaster/plugin/`)
| File | Purpose |
|------|---------|
| `base.py` | QuartermasterPlugin base class |
| `context.py` | PluginContext dataclass |
| `loader.py` | Plugin discovery + dependency resolution |
| `health.py` | HealthStatus enum + types |

### Plugins
| File | Purpose |
|------|---------|
| `plugins/chat/plugin.py` | Basic LLM conversation |
| `plugins/chat/prompts.py` | System prompt (Quartermaster persona) |
| `plugins/commands/plugin.py` | /status, /models, /help, /spend, /new |
| `plugins/briefing/plugin.py` | Scheduled briefing skeleton |
| `plugins/briefing/templates.py` | Briefing text formatting |

### Tests
| File | Purpose |
|------|---------|
| `tests/conftest.py` | Shared fixtures (mock DB, mock LLM, mock transport) |
| `tests/core/test_events.py` | Event bus tests |
| `tests/core/test_config.py` | Config loading tests |
| `tests/core/test_tools.py` | Tool Registry tests |
| `tests/core/test_database.py` | Database layer tests |
| `tests/core/test_scheduler.py` | Scheduler tests |
| `tests/core/test_approval.py` | Approval manager tests |
| `tests/core/test_usage.py` | Usage tracker tests |
| `tests/llm/test_router.py` | LLM routing tests |
| `tests/llm/test_local.py` | llama-swap client tests |
| `tests/llm/test_anthropic_client.py` | Anthropic client tests |
| `tests/transport/test_types.py` | Message type tests |
| `tests/conversation/test_manager.py` | Conversation manager tests |
| `tests/plugins/test_chat.py` | Chat plugin tests |
| `tests/plugins/test_commands.py` | Commands plugin tests |
| `tests/plugin/test_loader.py` | Plugin loader tests |

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.gitignore`
- Create: `CLAUDE.md`
- Create: `config/settings.example.yaml`
- Create: `src/quartermaster/__init__.py`
- Create: `src/quartermaster/__main__.py` (placeholder)
- Create: `tests/__init__.py`
- Create: `tests/conftest.py` (minimal)
- Create: `credentials/.gitkeep`
- Create: `logs/.gitkeep`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "quartermaster"
version = "0.1.0"
description = "Self-hosted personal AI assistant with plugin architecture"
requires-python = ">=3.13"
readme = "README.md"
license = {text = "MIT"}

[tool.mypy]
python_version = "3.13"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create requirements.txt**

```
python-telegram-bot>=22.0
httpx>=0.27.0
python-oracledb>=2.0.0
pydantic>=2.0
pydantic-settings>=2.0
pyyaml>=6.0
structlog>=24.0
prometheus-client>=0.20
anthropic>=0.40.0
tiktoken>=0.7.0
aiohttp>=3.9.0
croniter>=2.0.0
```

- [ ] **Step 3: Create requirements-dev.txt**

```
-r requirements.txt
pytest>=8.0
pytest-asyncio>=0.24.0
pytest-cov>=5.0
mypy>=1.10
ruff>=0.6.0
types-PyYAML
```

- [ ] **Step 4: Create Dockerfile**

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install Oracle Instant Client dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libaio1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY plugins/ plugins/

ENV PYTHONPATH=/app/src:/app
ENV QM_ENV=production

ENTRYPOINT ["python", "-m", "quartermaster"]
```

- [ ] **Step 5: Create docker-compose.yml**

```yaml
services:
  quartermaster:
    build: .
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./config:/app/config
      - ./credentials:/app/credentials
      - ./logs:/app/logs
      - ./plugins:/app/plugins
    environment:
      - QM_ENV=production
      - ORACLE_DSN=localhost:1521/quartermaster_pdb
```

- [ ] **Step 6: Create .gitignore**

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
venv/

# Project secrets
credentials/
!credentials/.gitkeep
config/settings.yaml
*.pem
*.key

# Logs
logs/
!logs/.gitkeep

# IDE
.idea/
.vscode/
*.swp

# Testing
.coverage
htmlcov/
.pytest_cache/
.mypy_cache/

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 7: Create config/settings.example.yaml**

```yaml
# Quartermaster Configuration
# Copy to config/settings.yaml and fill in your values

quartermaster:
  # Telegram bot token from @BotFather
  telegram_bot_token: "YOUR_BOT_TOKEN"
  # Your Telegram user ID (only this user can interact)
  allowed_user_ids:
    - 123456789

  # Oracle database
  database:
    dsn: "localhost:1521/quartermaster_pdb"
    user: "qm"
    password: "YOUR_PASSWORD"
    pool_min: 2
    pool_max: 10

  # LLM routing
  llm:
    # Local LLM via llama-swap
    local:
      base_url: "http://localhost:8200/v1"
      preferred_model: "qwen3.5-27b"
      timeout_seconds: 60
      swap_timeout_seconds: 120
    # Anthropic API fallback
    anthropic:
      api_key_file: "/app/credentials/anthropic_api_key"
      default_model: "claude-sonnet-4-20250514"
      fallback_model: "claude-haiku-4-5-20251001"
    # Budget
    monthly_budget_usd: 50.00
    budget_warn_percent: 80
    budget_block_percent: 100

  # Scheduler
  scheduler:
    missed_event_grace_minutes: 15

  # Approval
  approval:
    default_timeout_minutes: 60

  # Metrics
  metrics:
    port: 9100

  # Bot persona
  persona: |
    You are Quartermaster, a personal AI assistant. You are concise, direct,
    and action-oriented. When you can answer directly, do so. When a task
    requires a tool, call it without preamble. For actions with external
    consequences, always present a draft for approval before executing.
    Keep status reports scannable — use bullet points, not paragraphs.
    Match the user's tone — brief messages get brief replies.

  # Conversation
  conversation:
    context_window_max_turns: 20
    context_window_max_tokens: 8000
    idle_timeout_hours: 4

  # Plugins directory
  plugins_dir: "/app/plugins"

  # Logging
  logging:
    level: "INFO"
    format: "json"
```

- [ ] **Step 8: Create CLAUDE.md**

```markdown
# Quartermaster

Self-hosted personal AI assistant with plugin architecture.

## Project Structure
- `src/quartermaster/` — Core application (do not modify lightly)
- `plugins/` — Plugin packages (each is self-contained)
- `config/` — YAML configuration (settings.yaml is gitignored)
- `credentials/` — API keys, OAuth tokens (gitignored)
- `tests/` — pytest test suite

## Development
- Python 3.13, strict mypy, ruff linting
- Run tests: `pytest`
- Type check: `mypy src/`
- Lint: `ruff check src/ plugins/ tests/`
- All data structures use Pydantic v2 models
- Structured logging via structlog (JSON format)

## Architecture
- Everything is a tool registered in the Tool Registry
- Plugins register tools at startup via PluginContext
- LLM is an orchestrator (selects tools), not a worker
- Event bus for loose coupling between components
- Oracle 26ai PDB for all persistence (no SQLite)

## Testing
- TDD: write failing test first, then implement
- Core services: unit tests with mocks
- Database: integration tests against QUARTERMASTER_TEST_PDB
- Each plugin tested in isolation against mock PluginContext

## Key Files
- `src/quartermaster/core/app.py` — Application bootstrap
- `src/quartermaster/core/tools.py` — Tool Registry (central nervous system)
- `src/quartermaster/core/events.py` — Event bus
- `src/quartermaster/llm/router.py` — Smart LLM routing
- `src/quartermaster/plugin/base.py` — Plugin base class
```

- [ ] **Step 9: Create package init files and placeholder main**

`src/quartermaster/__init__.py`:
```python
"""Quartermaster — Self-hosted personal AI assistant."""

__version__ = "0.1.0"
```

`src/quartermaster/__main__.py`:
```python
"""Entry point for python -m quartermaster."""

import asyncio
import sys


def main() -> None:
    """Launch the Quartermaster application."""
    # Placeholder — will be replaced in Task 21
    print(f"Quartermaster v0.1.0 — not yet implemented")
    sys.exit(1)


if __name__ == "__main__":
    main()
```

`tests/__init__.py`: empty file
`tests/conftest.py`:
```python
"""Shared test fixtures for Quartermaster."""
```

- [ ] **Step 10: Create directory stubs**

```bash
mkdir -p src/quartermaster/{core,llm,transport,conversation,plugin}
mkdir -p plugins/{chat,commands,briefing}
mkdir -p tests/{core,llm,transport,conversation,plugin,plugins}
mkdir -p credentials logs config scripts
touch src/quartermaster/core/__init__.py
touch src/quartermaster/llm/__init__.py
touch src/quartermaster/transport/__init__.py
touch src/quartermaster/conversation/__init__.py
touch src/quartermaster/plugin/__init__.py
touch plugins/chat/__init__.py
touch plugins/commands/__init__.py
touch plugins/briefing/__init__.py
touch tests/core/__init__.py
touch tests/llm/__init__.py
touch tests/transport/__init__.py
touch tests/conversation/__init__.py
touch tests/plugin/__init__.py
touch tests/plugins/__init__.py
touch credentials/.gitkeep
touch logs/.gitkeep
```

- [ ] **Step 11: Verify scaffold**

Run: `pip install -e ".[dev]" 2>/dev/null || pip install -r requirements-dev.txt`
Run: `python -m quartermaster` — should print version and exit 1
Run: `pytest --co` — should collect 0 tests (no test files yet)
Run: `ruff check src/` — should pass
Run: `mypy src/quartermaster/__init__.py` — should pass

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "chore: project scaffold with build config, Docker, and settings template"
```

---

## Task 2: Oracle PDB Setup Script

**Files:**
- Create: `scripts/setup_oracle_pdb.sql`
- Create: `scripts/setup_test_pdb.sql`

- [ ] **Step 1: Create production PDB setup script**

`scripts/setup_oracle_pdb.sql`:
```sql
-- Quartermaster Oracle PDB Setup
-- Run as SYSDBA from the CDB root:
--   sqlplus / as sysdba @scripts/setup_oracle_pdb.sql

-- Create PDB
CREATE PLUGGABLE DATABASE quartermaster_pdb
  ADMIN USER qm_admin IDENTIFIED BY CHANGE_ME_ADMIN
  FILE_NAME_CONVERT = ('/pdbseed/', '/quartermaster_pdb/');

ALTER PLUGGABLE DATABASE quartermaster_pdb OPEN;
ALTER PLUGGABLE DATABASE quartermaster_pdb SAVE STATE;

-- Connect to the new PDB
ALTER SESSION SET CONTAINER = quartermaster_pdb;

-- Create application schema user
CREATE USER qm IDENTIFIED BY CHANGE_ME_QM
  DEFAULT TABLESPACE users
  QUOTA UNLIMITED ON users;

GRANT CREATE SESSION TO qm;
GRANT CREATE TABLE TO qm;
GRANT CREATE SEQUENCE TO qm;
GRANT CREATE PROCEDURE TO qm;

-- Create Phase 1 tables
-- Conversation history
CREATE TABLE qm.conversations (
    conversation_id   RAW(16) DEFAULT sys_guid() PRIMARY KEY,
    transport         VARCHAR2(20) NOT NULL,
    external_chat_id  VARCHAR2(100) NOT NULL,
    created_at        TIMESTAMP DEFAULT systimestamp,
    last_active_at    TIMESTAMP DEFAULT systimestamp,
    metadata          JSON
);

CREATE INDEX qm.idx_conv_chat_id ON qm.conversations(external_chat_id);
CREATE INDEX qm.idx_conv_last_active ON qm.conversations(last_active_at);

-- Individual turns in a conversation
CREATE TABLE qm.turns (
    turn_id           RAW(16) DEFAULT sys_guid() PRIMARY KEY,
    conversation_id   RAW(16) NOT NULL REFERENCES qm.conversations,
    role              VARCHAR2(20) NOT NULL,
    content           CLOB,
    tool_calls        JSON,
    tool_results      JSON,
    llm_backend       VARCHAR2(50),
    tokens_in         NUMBER,
    tokens_out        NUMBER,
    estimated_cost    NUMBER(12,6),
    created_at        TIMESTAMP DEFAULT systimestamp
);

CREATE INDEX qm.idx_turns_conv ON qm.turns(conversation_id, created_at);

-- Plugin state (generic key-value per plugin)
CREATE TABLE qm.plugin_state (
    plugin_name       VARCHAR2(50) NOT NULL,
    state_key         VARCHAR2(100) NOT NULL,
    state_value       JSON,
    updated_at        TIMESTAMP DEFAULT systimestamp,
    CONSTRAINT pk_plugin_state PRIMARY KEY (plugin_name, state_key)
);

-- Scheduled tasks
CREATE TABLE qm.schedules (
    schedule_id       RAW(16) DEFAULT sys_guid() PRIMARY KEY,
    plugin_name       VARCHAR2(50) NOT NULL,
    task_name         VARCHAR2(100) NOT NULL,
    cron_expression   VARCHAR2(100) NOT NULL,
    enabled           NUMBER(1) DEFAULT 1,
    last_run_at       TIMESTAMP,
    next_run_at       TIMESTAMP,
    last_status       VARCHAR2(20),
    config            JSON
);

-- API usage tracking
CREATE TABLE qm.usage_log (
    usage_id          RAW(16) DEFAULT sys_guid() PRIMARY KEY,
    provider          VARCHAR2(30) NOT NULL,
    model             VARCHAR2(50),
    tokens_in         NUMBER,
    tokens_out        NUMBER,
    estimated_cost    NUMBER(12,6),
    purpose           VARCHAR2(100),
    plugin_name       VARCHAR2(50),
    created_at        TIMESTAMP DEFAULT systimestamp
);

CREATE INDEX qm.idx_usage_created ON qm.usage_log(created_at);
CREATE INDEX qm.idx_usage_provider ON qm.usage_log(provider, created_at);

-- Approval queue
CREATE TABLE qm.approvals (
    approval_id       RAW(16) DEFAULT sys_guid() PRIMARY KEY,
    plugin_name       VARCHAR2(50) NOT NULL,
    tool_name         VARCHAR2(100) NOT NULL,
    draft_content     CLOB,
    action_payload    JSON,
    status            VARCHAR2(20) DEFAULT 'pending',
    transport         VARCHAR2(20),
    external_msg_id   VARCHAR2(100),
    requested_at      TIMESTAMP DEFAULT systimestamp,
    resolved_at       TIMESTAMP,
    resolved_by       VARCHAR2(50)
);

CREATE INDEX qm.idx_approvals_status ON qm.approvals(status, requested_at);

COMMIT;

-- Verify
SELECT table_name FROM all_tables WHERE owner = 'QM' ORDER BY table_name;
```

- [ ] **Step 2: Create test PDB setup script**

`scripts/setup_test_pdb.sql`:
```sql
-- Quartermaster Test PDB Setup
-- Run as SYSDBA: sqlplus / as sysdba @scripts/setup_test_pdb.sql

CREATE PLUGGABLE DATABASE quartermaster_test_pdb
  ADMIN USER qm_test_admin IDENTIFIED BY test_admin_pw
  FILE_NAME_CONVERT = ('/pdbseed/', '/quartermaster_test_pdb/');

ALTER PLUGGABLE DATABASE quartermaster_test_pdb OPEN;
ALTER PLUGGABLE DATABASE quartermaster_test_pdb SAVE STATE;

ALTER SESSION SET CONTAINER = quartermaster_test_pdb;

CREATE USER qm IDENTIFIED BY test_qm_pw
  DEFAULT TABLESPACE users
  QUOTA UNLIMITED ON users;

GRANT CREATE SESSION TO qm;
GRANT CREATE TABLE TO qm;
GRANT CREATE SEQUENCE TO qm;
GRANT CREATE PROCEDURE TO qm;

-- Same tables as production — duplicate the DDL from setup_oracle_pdb.sql here.
-- During implementation, copy the CREATE TABLE and CREATE INDEX statements
-- from setup_oracle_pdb.sql into this file (everything after the CREATE USER block).
```

Note: The test PDB tables can be factored into a shared `setup_oracle_pdb_tables.sql` during implementation. The key point is that tests run against a real Oracle instance with the same schema.

- [ ] **Step 3: Run the PDB setup on slmbeast**

```bash
sqlplus / as sysdba @scripts/setup_oracle_pdb.sql
```
Expected: 6 tables created under QM schema.

- [ ] **Step 4: Commit**

```bash
git add scripts/
git commit -m "chore: Oracle PDB setup scripts for production and test"
```

---

## Task 3: Core Config Models

**Files:**
- Create: `src/quartermaster/core/config.py`
- Create: `tests/core/test_config.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_config.py`:
```python
"""Tests for configuration loading."""

import pytest
from pathlib import Path
from quartermaster.core.config import (
    QuartermasterConfig,
    DatabaseConfig,
    LLMConfig,
    LocalLLMConfig,
    AnthropicConfig,
    SchedulerConfig,
    ApprovalConfig,
    MetricsConfig,
    ConversationConfig,
    load_config,
)


def test_database_config_defaults() -> None:
    cfg = DatabaseConfig(dsn="localhost:1521/test", user="qm", password="pw")
    assert cfg.pool_min == 2
    assert cfg.pool_max == 10


def test_llm_config_defaults() -> None:
    local = LocalLLMConfig()
    assert local.base_url == "http://localhost:8200/v1"
    assert local.preferred_model == "qwen3.5-27b"
    assert local.timeout_seconds == 60


def test_anthropic_config_requires_key_file() -> None:
    cfg = AnthropicConfig(api_key_file="/path/to/key")
    assert cfg.default_model == "claude-sonnet-4-20250514"


def test_full_config_from_yaml(tmp_path: Path) -> None:
    yaml_content = """
quartermaster:
  telegram_bot_token: "test-token"
  allowed_user_ids:
    - 12345
  database:
    dsn: "localhost:1521/test_pdb"
    user: "qm"
    password: "testpw"
  llm:
    local:
      base_url: "http://localhost:8200/v1"
    anthropic:
      api_key_file: "/tmp/key"
    monthly_budget_usd: 50.0
  plugins_dir: "/app/plugins"
"""
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(yaml_content)
    cfg = load_config(config_file)
    assert cfg.telegram_bot_token == "test-token"
    assert cfg.allowed_user_ids == [12345]
    assert cfg.database.dsn == "localhost:1521/test_pdb"
    assert cfg.llm.monthly_budget_usd == 50.0


def test_load_config_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/settings.yaml"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quartermaster.core.config'`

- [ ] **Step 3: Implement config.py**

`src/quartermaster/core/config.py`:
```python
"""Configuration models for Quartermaster."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


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
    persona: str = ""
    plugins_dir: str = "/app/plugins"


def load_config(path: Path) -> QuartermasterConfig:
    """Load configuration from a YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    qm_section = raw.get("quartermaster", {})
    return QuartermasterConfig(**qm_section)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_config.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Run type check and lint**

Run: `mypy src/quartermaster/core/config.py --strict`
Run: `ruff check src/quartermaster/core/config.py`

- [ ] **Step 6: Commit**

```bash
git add src/quartermaster/core/config.py tests/core/test_config.py
git commit -m "feat: configuration models with YAML loading"
```

---

## Task 4: Event Bus

**Files:**
- Create: `src/quartermaster/core/events.py`
- Create: `tests/core/test_events.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_events.py`:
```python
"""Tests for the async event bus."""

import asyncio
import pytest
from quartermaster.core.events import EventBus


@pytest.mark.asyncio
async def test_subscribe_and_emit() -> None:
    bus = EventBus()
    received: list[dict] = []

    async def handler(data: dict) -> None:
        received.append(data)

    bus.subscribe("test.event", handler)
    await bus.emit("test.event", {"key": "value"})
    assert len(received) == 1
    assert received[0] == {"key": "value"}


@pytest.mark.asyncio
async def test_multiple_subscribers() -> None:
    bus = EventBus()
    results: list[str] = []

    async def handler_a(data: dict) -> None:
        results.append("a")

    async def handler_b(data: dict) -> None:
        results.append("b")

    bus.subscribe("test.event", handler_a)
    bus.subscribe("test.event", handler_b)
    await bus.emit("test.event", {})
    assert sorted(results) == ["a", "b"]


@pytest.mark.asyncio
async def test_emit_no_subscribers_is_silent() -> None:
    bus = EventBus()
    # Should not raise
    await bus.emit("nobody.listening", {"data": 1})


@pytest.mark.asyncio
async def test_handler_crash_does_not_break_others() -> None:
    bus = EventBus()
    results: list[str] = []

    async def bad_handler(data: dict) -> None:
        raise RuntimeError("boom")

    async def good_handler(data: dict) -> None:
        results.append("ok")

    bus.subscribe("test.event", bad_handler)
    bus.subscribe("test.event", good_handler)
    await bus.emit("test.event", {})
    assert results == ["ok"]


@pytest.mark.asyncio
async def test_unsubscribe() -> None:
    bus = EventBus()
    received: list[dict] = []

    async def handler(data: dict) -> None:
        received.append(data)

    bus.subscribe("test.event", handler)
    bus.unsubscribe("test.event", handler)
    await bus.emit("test.event", {"key": "value"})
    assert len(received) == 0


@pytest.mark.asyncio
async def test_list_events() -> None:
    bus = EventBus()

    async def handler(data: dict) -> None:
        pass

    bus.subscribe("alpha", handler)
    bus.subscribe("beta", handler)
    assert sorted(bus.list_events()) == ["alpha", "beta"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_events.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement events.py**

`src/quartermaster/core/events.py`:
```python
"""Async event bus for inter-component communication."""

from collections import defaultdict
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger()

EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus:
    """Async publish/subscribe event bus.

    At-most-once delivery. Handler crashes are caught and logged,
    not propagated to other handlers.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event: str, handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        """Remove a handler for an event type."""
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: str, data: dict[str, Any]) -> None:
        """Emit an event to all registered handlers.

        Handlers run concurrently. Exceptions in one handler
        do not affect others.
        """
        handlers = self._handlers.get(event, [])
        if not handlers:
            return

        for handler in handlers:
            try:
                await handler(data)
            except Exception:
                logger.exception(
                    "event_handler_error",
                    event=event,
                    handler=handler.__qualname__,
                )

    def list_events(self) -> list[str]:
        """Return all event types with registered handlers."""
        return list(self._handlers.keys())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_events.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/core/events.py tests/core/test_events.py
git commit -m "feat: async event bus with handler isolation"
```

---

## Task 5: Tool Registry

**Files:**
- Create: `src/quartermaster/core/tools.py`
- Create: `tests/core/test_tools.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_tools.py`:
```python
"""Tests for the Tool Registry."""

import pytest
from quartermaster.core.tools import ToolRegistry, ToolDefinition, ApprovalTier


@pytest.mark.asyncio
async def test_register_and_get_tool() -> None:
    registry = ToolRegistry()

    async def my_handler(params: dict) -> dict:
        return {"result": "ok"}

    registry.register(
        name="test.hello",
        description="A test tool",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Who to greet"},
            },
            "required": ["name"],
        },
        handler=my_handler,
        approval_tier=ApprovalTier.AUTONOMOUS,
    )

    tool = registry.get("test.hello")
    assert tool is not None
    assert tool.name == "test.hello"
    assert tool.description == "A test tool"
    assert tool.approval_tier == ApprovalTier.AUTONOMOUS


@pytest.mark.asyncio
async def test_execute_tool() -> None:
    registry = ToolRegistry()

    async def add_handler(params: dict) -> dict:
        return {"sum": params["a"] + params["b"]}

    registry.register(
        name="math.add",
        description="Add two numbers",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
        handler=add_handler,
    )

    result = await registry.execute("math.add", {"a": 2, "b": 3})
    assert result == {"sum": 5}


@pytest.mark.asyncio
async def test_execute_nonexistent_tool() -> None:
    registry = ToolRegistry()
    with pytest.raises(KeyError, match=r"no\.such\.tool"):
        await registry.execute("no.such.tool", {})


def test_list_tools() -> None:
    registry = ToolRegistry()

    async def handler(params: dict) -> dict:
        return {}

    registry.register(name="a.tool", description="A", parameters={}, handler=handler)
    registry.register(name="b.tool", description="B", parameters={}, handler=handler)

    tools = registry.list_tools()
    names = [t.name for t in tools]
    assert "a.tool" in names
    assert "b.tool" in names


def test_get_schemas_for_llm() -> None:
    registry = ToolRegistry()

    async def handler(params: dict) -> dict:
        return {}

    registry.register(
        name="test.tool",
        description="Test",
        parameters={
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": [],
        },
        handler=handler,
    )

    schemas = registry.get_tool_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "test.tool"
    assert schemas[0]["type"] == "function"


def test_duplicate_registration_raises() -> None:
    registry = ToolRegistry()

    async def handler(params: dict) -> dict:
        return {}

    registry.register(name="dup", description="First", parameters={}, handler=handler)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(name="dup", description="Second", parameters={}, handler=handler)


@pytest.mark.asyncio
async def test_tool_execution_error_returns_error_dict() -> None:
    registry = ToolRegistry()

    async def failing_handler(params: dict) -> dict:
        raise RuntimeError("connection refused")

    registry.register(name="fail.tool", description="Fails", parameters={}, handler=failing_handler)

    result = await registry.execute("fail.tool", {})
    assert "error" in result
    assert "connection refused" in result["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement tools.py**

`src/quartermaster/core/tools.py`:
```python
"""Tool Registry — the central nervous system of Quartermaster."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger()

ToolHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


class ApprovalTier(str, Enum):
    """Approval tiers for tool execution."""
    AUTONOMOUS = "autonomous"
    CONFIRM = "confirm"
    NOTIFY = "notify"


@dataclass
class ToolDefinition:
    """A registered tool in the registry."""
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    approval_tier: ApprovalTier = ApprovalTier.AUTONOMOUS
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """Central registry for all tools.

    Tools are registered by plugins at startup. The LLM Router
    queries the registry for available tool schemas, and the
    Tool Executor dispatches calls through the registry.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: ToolHandler,
        approval_tier: ApprovalTier = ApprovalTier.AUTONOMOUS,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a tool."""
        if name in self._tools:
            raise ValueError(f"Tool '{name}' already registered")
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            approval_tier=approval_tier,
            metadata=metadata or {},
        )
        logger.info("tool_registered", tool=name, tier=approval_tier.value)

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get tool schemas in OpenAI function-calling format.

        Returns a list compatible with both llama-swap (OpenAI format)
        and Anthropic's tool_use format.
        """
        schemas: list[dict[str, Any]] = []
        for tool in self._tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return schemas

    async def execute(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name.

        Returns the tool's result dict. If the tool raises an exception,
        returns an error dict instead (so the LLM can handle it).
        """
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' not found")
        try:
            return await tool.handler(params)
        except Exception as e:
            logger.exception("tool_execution_error", tool=name)
            return {"error": f"{type(e).__name__}: {e}"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_tools.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/core/tools.py tests/core/test_tools.py
git commit -m "feat: Tool Registry with schema generation and error handling"
```

---

## Task 6: Plugin Framework

**Files:**
- Create: `src/quartermaster/plugin/health.py`
- Create: `src/quartermaster/plugin/base.py`
- Create: `src/quartermaster/plugin/context.py`
- Create: `src/quartermaster/plugin/loader.py`
- Create: `tests/plugin/test_loader.py`

- [ ] **Step 1: Write failing test**

`tests/plugin/test_loader.py`:
```python
"""Tests for plugin discovery and loading."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from quartermaster.plugin.loader import PluginLoader
from quartermaster.plugin.base import QuartermasterPlugin
from quartermaster.plugin.context import PluginContext
from quartermaster.plugin.health import HealthStatus, HealthReport


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
    assert HealthStatus.OK == "ok"
    assert HealthStatus.DEGRADED == "degraded"
    assert HealthStatus.DOWN == "down"


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
    loader.register_class(DependentPlugin)  # depends on "fake" which is not registered
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/plugin/test_loader.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement health.py, base.py, context.py, loader.py**

`src/quartermaster/plugin/health.py`:
```python
"""Plugin health check types."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class HealthReport:
    status: HealthStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
```

`src/quartermaster/plugin/base.py`:
```python
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
```

`src/quartermaster/plugin/context.py`:
```python
"""Plugin context — provides access to core services."""

from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from quartermaster.core.events import EventBus
    from quartermaster.core.tools import ToolRegistry
    from quartermaster.core.config import QuartermasterConfig


@dataclass
class PluginContext:
    """Provides plugins access to core services."""
    config: Any  # QuartermasterConfig or plugin-specific section
    events: Any  # EventBus
    tools: Any  # ToolRegistry
    db: Any = None  # Database
    llm: Any = None  # LLMRouter
    transport: Any = None  # TransportManager
    scheduler: Any = None  # Scheduler
    approval: Any = None  # ApprovalManager
    usage: Any = None  # UsageTracker
    conversation: Any = None  # ConversationManager
```

`src/quartermaster/plugin/loader.py`:
```python
"""Plugin discovery and lifecycle management."""

from __future__ import annotations
from collections import OrderedDict
from typing import TYPE_CHECKING

import structlog

from quartermaster.plugin.base import QuartermasterPlugin
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
            except Exception as e:
                reports[name] = HealthReport(
                    status=HealthStatus.DOWN,
                    message=f"Health check failed: {e}",
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/plugin/test_loader.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/plugin/ tests/plugin/
git commit -m "feat: plugin framework with base class, context, loader, and health checks"
```

---

## Task 7: Database Layer

**Files:**
- Create: `src/quartermaster/core/database.py`
- Create: `tests/core/test_database.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_database.py`:
```python
"""Tests for the Oracle database layer."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from quartermaster.core.database import Database
from quartermaster.core.config import DatabaseConfig


@pytest.fixture
def db_config() -> DatabaseConfig:
    return DatabaseConfig(
        dsn="localhost:1521/quartermaster_test_pdb",
        user="qm",
        password="test_pw",
    )


@pytest.mark.asyncio
async def test_database_connect_and_close(db_config: DatabaseConfig) -> None:
    """Test that database can connect and close (mocked)."""
    with patch("quartermaster.core.database.oracledb") as mock_ora:
        mock_pool = MagicMock()
        mock_ora.create_pool_async = AsyncMock(return_value=mock_pool)
        mock_pool.close = AsyncMock()

        db = Database(db_config)
        await db.connect()
        assert db.is_connected

        await db.close()
        mock_pool.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_database_execute(db_config: DatabaseConfig) -> None:
    """Test execute returns results (mocked)."""
    with patch("quartermaster.core.database.oracledb") as mock_ora:
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_ora.create_pool_async = AsyncMock(return_value=mock_pool)
        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_pool.release = AsyncMock()
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_cursor.execute = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[(1, "test")])
        mock_cursor.close = AsyncMock()

        db = Database(db_config)
        await db.connect()
        rows = await db.fetch_all("SELECT 1, 'test' FROM dual")
        assert rows == [(1, "test")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_database.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement database.py**

`src/quartermaster/core/database.py`:
```python
"""Oracle database connection pool."""

from typing import Any

import oracledb
import structlog

from quartermaster.core.config import DatabaseConfig

logger = structlog.get_logger()


class Database:
    """Async Oracle database connection pool.

    Wraps python-oracledb's async pool for connection management.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._pool: oracledb.AsyncConnectionPool | None = None

    @property
    def is_connected(self) -> bool:
        return self._pool is not None

    async def connect(self) -> None:
        """Initialize the connection pool."""
        self._pool = await oracledb.create_pool_async(
            user=self._config.user,
            password=self._config.password,
            dsn=self._config.dsn,
            min=self._config.pool_min,
            max=self._config.pool_max,
        )
        logger.info("database_connected", dsn=self._config.dsn)

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("database_closed")

    async def fetch_all(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[tuple[Any, ...]]:
        """Execute a query and return all rows."""
        assert self._pool is not None, "Database not connected"
        conn = await self._pool.acquire()
        try:
            cursor = conn.cursor()
            await cursor.execute(sql, params or {})
            rows: list[tuple[Any, ...]] = await cursor.fetchall()
            await cursor.close()
            return rows
        finally:
            await self._pool.release(conn)

    async def fetch_one(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> tuple[Any, ...] | None:
        """Execute a query and return one row."""
        assert self._pool is not None, "Database not connected"
        conn = await self._pool.acquire()
        try:
            cursor = conn.cursor()
            await cursor.execute(sql, params or {})
            row: tuple[Any, ...] | None = await cursor.fetchone()
            await cursor.close()
            return row
        finally:
            await self._pool.release(conn)

    async def execute(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> int:
        """Execute a DML statement and return rows affected."""
        assert self._pool is not None, "Database not connected"
        conn = await self._pool.acquire()
        try:
            cursor = conn.cursor()
            await cursor.execute(sql, params or {})
            await conn.commit()
            rowcount: int = cursor.rowcount
            await cursor.close()
            return rowcount
        finally:
            await self._pool.release(conn)

    async def execute_many(
        self, sql: str, params_list: list[dict[str, Any]]
    ) -> None:
        """Execute a DML statement with multiple parameter sets."""
        assert self._pool is not None, "Database not connected"
        conn = await self._pool.acquire()
        try:
            cursor = conn.cursor()
            await cursor.executemany(sql, params_list)
            await conn.commit()
            await cursor.close()
        finally:
            await self._pool.release(conn)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_database.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/core/database.py tests/core/test_database.py
git commit -m "feat: Oracle async database layer with connection pooling"
```

---

## Task 8: Usage Tracker

**Files:**
- Create: `src/quartermaster/core/usage.py`
- Create: `tests/core/test_usage.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_usage.py`:
```python
"""Tests for API usage tracking and budget enforcement."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from quartermaster.core.usage import UsageTracker, UsageRecord, BudgetStatus


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(return_value=1)
    db.fetch_one = AsyncMock(return_value=(10.50,))  # $10.50 spent this month
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
    mock_db.fetch_one = AsyncMock(return_value=(10.0,))  # 20% of $50
    tracker = UsageTracker(db=mock_db, monthly_budget=50.0)
    status = await tracker.get_budget_status()
    assert status == BudgetStatus.OK


@pytest.mark.asyncio
async def test_budget_status_warning(mock_db: MagicMock) -> None:
    mock_db.fetch_one = AsyncMock(return_value=(42.0,))  # 84% of $50
    tracker = UsageTracker(db=mock_db, monthly_budget=50.0, warn_percent=80)
    status = await tracker.get_budget_status()
    assert status == BudgetStatus.WARNING


@pytest.mark.asyncio
async def test_budget_status_blocked(mock_db: MagicMock) -> None:
    mock_db.fetch_one = AsyncMock(return_value=(51.0,))  # 102% of $50
    tracker = UsageTracker(db=mock_db, monthly_budget=50.0)
    status = await tracker.get_budget_status()
    assert status == BudgetStatus.BLOCKED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_usage.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement usage.py**

`src/quartermaster/core/usage.py`:
```python
"""API usage tracking and budget enforcement."""

from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class BudgetStatus(str, Enum):
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
        db: Any,  # Database
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_usage.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/core/usage.py tests/core/test_usage.py
git commit -m "feat: usage tracker with budget enforcement"
```

---

## Task 9: Scheduler

**Files:**
- Create: `src/quartermaster/core/scheduler.py`
- Create: `tests/core/test_scheduler.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_scheduler.py`:
```python
"""Tests for the cron-like scheduler."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from quartermaster.core.scheduler import Scheduler, ScheduleEntry


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
    entry.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=5)
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
    entry.next_run_at = datetime.now(timezone.utc) - timedelta(hours=2)
    scheduler.register(entry)

    fired = await scheduler.check_missed_events()
    assert fired == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_scheduler.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement scheduler.py**

`src/quartermaster/core/scheduler.py`:
```python
"""Cron-like async scheduler."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

from croniter import croniter
import structlog

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
        cron = croniter(self.cron_expression, datetime.now(timezone.utc))
        self.next_run_at = cron.get_next(datetime).replace(tzinfo=timezone.utc)


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
        return list(self._entries.values())

    async def check_missed_events(self) -> int:
        """Check for and fire missed events within the grace window."""
        now = datetime.now(timezone.utc)
        grace = timedelta(minutes=self._grace_minutes)
        fired = 0

        for key, entry in self._entries.items():
            if not entry.enabled or entry.next_run_at is None:
                continue
            if entry.next_run_at > now:
                continue  # Not due yet

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
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        """Main scheduler loop — check every 30 seconds."""
        while self._running:
            await asyncio.sleep(30)
            now = datetime.now(timezone.utc)
            for key, entry in self._entries.items():
                if not entry.enabled or entry.next_run_at is None:
                    continue
                if entry.next_run_at <= now:
                    await self._fire(key, entry)

    async def _fire(self, key: str, entry: ScheduleEntry) -> None:
        """Fire a scheduled event."""
        try:
            await self._events.emit(entry.event_name, {
                "schedule_key": key,
                "plugin": entry.plugin_name,
                "task": entry.task_name,
            })
            entry.last_status = "success"
            entry.last_run_at = datetime.now(timezone.utc)
            entry.consecutive_failures = 0
        except Exception:
            logger.exception("schedule_fire_error", key=key)
            entry.last_status = "failed"
            entry.consecutive_failures += 1
            if entry.consecutive_failures >= 3:
                logger.error("schedule_persistent_failure", key=key, failures=entry.consecutive_failures)

        entry.compute_next_run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_scheduler.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/core/scheduler.py tests/core/test_scheduler.py
git commit -m "feat: cron-like scheduler with missed-event recovery"
```

---

## Task 10: Approval Manager

**Files:**
- Create: `src/quartermaster/core/approval.py`
- Create: `tests/core/test_approval.py`

- [ ] **Step 1: Write failing test**

`tests/core/test_approval.py`:
```python
"""Tests for the approval manager."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from quartermaster.core.approval import ApprovalManager, ApprovalRequest, ApprovalStatus


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(return_value=1)
    db.fetch_one = AsyncMock(return_value=None)
    db.fetch_all = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_transport() -> MagicMock:
    transport = MagicMock()
    transport.send = AsyncMock(return_value="msg_123")
    return transport


@pytest.fixture
def mock_events() -> MagicMock:
    events = MagicMock()
    events.emit = AsyncMock()
    events.subscribe = MagicMock()
    return events


@pytest.mark.asyncio
async def test_request_approval(
    mock_db: MagicMock,
    mock_transport: MagicMock,
    mock_events: MagicMock,
) -> None:
    mgr = ApprovalManager(db=mock_db, transport=mock_transport, events=mock_events)
    req = ApprovalRequest(
        plugin_name="social",
        tool_name="social.post",
        draft_content="Draft tweet: Hello world!",
        action_payload={"text": "Hello world!"},
        chat_id="12345",
    )
    approval_id = await mgr.request_approval(req)
    assert approval_id is not None
    mock_transport.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_approval(
    mock_db: MagicMock,
    mock_transport: MagicMock,
    mock_events: MagicMock,
) -> None:
    # Simulate a pending approval in DB
    mock_db.fetch_one = AsyncMock(return_value=(
        b"\x01" * 16,  # approval_id
        "social",  # plugin_name
        "social.post",  # tool_name
        "Draft tweet",  # draft_content
        '{"text": "hello"}',  # action_payload
        "pending",  # status
    ))
    mgr = ApprovalManager(db=mock_db, transport=mock_transport, events=mock_events)
    result = await mgr.resolve("approval_123", ApprovalStatus.APPROVED, "brian")
    assert result is True
    mock_events.emit.assert_awaited()


def test_approval_status_values() -> None:
    assert ApprovalStatus.PENDING == "pending"
    assert ApprovalStatus.APPROVED == "approved"
    assert ApprovalStatus.REJECTED == "rejected"
    assert ApprovalStatus.EXPIRED == "expired"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_approval.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement approval.py**

`src/quartermaster/core/approval.py`:
```python
"""Three-tier approval manager."""

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from quartermaster.transport.types import OutboundMessage, TransportType

logger = structlog.get_logger()


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ApprovalRequest:
    """A request for user approval."""
    plugin_name: str
    tool_name: str
    draft_content: str
    action_payload: dict[str, Any]
    chat_id: str
    transport: TransportType = TransportType.TELEGRAM


class ApprovalManager:
    """Manages the draft → approve → execute flow."""

    def __init__(
        self,
        db: Any,
        transport: Any,
        events: Any,
        timeout_minutes: int = 60,
    ) -> None:
        self._db = db
        self._transport = transport
        self._events = events
        self._timeout_minutes = timeout_minutes
        self._pending_callbacks: dict[str, ApprovalRequest] = {}

        # Subscribe to approval callbacks from Telegram
        events.subscribe("approval.callback", self._handle_callback)

    async def request_approval(self, req: ApprovalRequest) -> str:
        """Send a draft for approval and store in Oracle."""
        approval_id = str(uuid.uuid4())[:8]

        # Store in Oracle
        await self._db.execute(
            """INSERT INTO qm.approvals
               (plugin_name, tool_name, draft_content, action_payload,
                status, transport, external_msg_id)
               VALUES (:plugin, :tool, :draft, :payload,
                       'pending', :transport, :msg_id)""",
            {
                "plugin": req.plugin_name,
                "tool": req.tool_name,
                "draft": req.draft_content,
                "payload": json.dumps(req.action_payload),
                "transport": req.transport.value,
                "msg_id": approval_id,
            },
        )

        # Send inline keyboard to Telegram
        msg_id = await self._transport.send(OutboundMessage(
            transport=req.transport,
            chat_id=req.chat_id,
            text=f"**Approval needed:**\n\n{req.draft_content}",
            inline_keyboard=[
                [
                    {"text": "Approve", "callback_data": f"approve:{approval_id}"},
                    {"text": "Reject", "callback_data": f"reject:{approval_id}"},
                ],
            ],
        ))

        self._pending_callbacks[approval_id] = req
        logger.info("approval_requested", id=approval_id, tool=req.tool_name)
        return approval_id

    async def resolve(
        self, approval_id: str, status: ApprovalStatus, resolved_by: str
    ) -> bool:
        """Resolve a pending approval."""
        await self._db.execute(
            """UPDATE qm.approvals
               SET status = :status,
                   resolved_at = systimestamp,
                   resolved_by = :by
               WHERE external_msg_id = :id AND status = 'pending'""",
            {"status": status.value, "by": resolved_by, "id": approval_id},
        )

        await self._events.emit("approval.resolved", {
            "approval_id": approval_id,
            "status": status.value,
            "resolved_by": resolved_by,
        })

        logger.info("approval_resolved", id=approval_id, status=status.value)
        return True

    async def _handle_callback(self, data: dict[str, Any]) -> None:
        """Handle an inline keyboard callback from Telegram."""
        callback_data = data.get("callback_data", "")
        if ":" not in callback_data:
            return

        action, approval_id = callback_data.split(":", 1)

        if approval_id not in self._pending_callbacks:
            # May be expired
            chat_id = data.get("chat_id", "")
            if chat_id:
                await self._transport.send(OutboundMessage(
                    transport=TransportType.TELEGRAM,
                    chat_id=chat_id,
                    text="This action has expired.",
                ))
            return

        if action == "approve":
            await self.resolve(approval_id, ApprovalStatus.APPROVED, "brian")
        elif action == "reject":
            await self.resolve(approval_id, ApprovalStatus.REJECTED, "brian")

        self._pending_callbacks.pop(approval_id, None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_approval.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/core/approval.py tests/core/test_approval.py
git commit -m "feat: three-tier approval manager with inline keyboard flow"
```

---

## Task 11: LLM Types and Local Client

**Files:**
- Create: `src/quartermaster/llm/models.py`
- Create: `src/quartermaster/llm/local.py`
- Create: `tests/llm/test_local.py`

- [ ] **Step 1: Write failing test**

`tests/llm/test_local.py`:
```python
"""Tests for the llama-swap local LLM client."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch
from quartermaster.llm.local import LocalLLMClient, LlamaSwapStatus
from quartermaster.llm.models import (
    LLMRequest,
    LLMResponse,
    ChatMessage,
    ToolCall,
)


def test_llm_request_model() -> None:
    req = LLMRequest(
        messages=[ChatMessage(role="user", content="hello")],
        tools=[],
    )
    assert req.messages[0].role == "user"


def test_llm_response_model() -> None:
    resp = LLMResponse(
        content="Hello!",
        tool_calls=[],
        model="qwen3.5-27b",
        tokens_in=5,
        tokens_out=10,
    )
    assert resp.content == "Hello!"
    assert resp.tokens_in == 5


@pytest.mark.asyncio
async def test_check_status_idle() -> None:
    mock_response = httpx.Response(
        200,
        json={"running": []},
        request=httpx.Request("GET", "http://localhost:8200/running"),
    )
    with patch("quartermaster.llm.local.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        client = LocalLLMClient(base_url="http://localhost:8200/v1", preferred_model="qwen3.5-27b")
        status = await client.check_status()
        assert status == LlamaSwapStatus.IDLE


@pytest.mark.asyncio
async def test_check_status_preferred_loaded() -> None:
    mock_response = httpx.Response(
        200,
        json={"running": [{"model": "qwen3.5-27b", "state": "ready"}]},
        request=httpx.Request("GET", "http://localhost:8200/running"),
    )
    with patch("quartermaster.llm.local.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        client = LocalLLMClient(base_url="http://localhost:8200/v1", preferred_model="qwen3.5-27b")
        status = await client.check_status()
        assert status == LlamaSwapStatus.PREFERRED_LOADED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/llm/test_local.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement models.py and local.py**

`src/quartermaster/llm/models.py`:
```python
"""LLM request/response types."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    """A single message in a conversation."""
    role: str  # 'system', 'user', 'assistant', 'tool'
    content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolCall:
    """A tool call from the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMRequest:
    """Request to an LLM backend."""
    messages: list[ChatMessage]
    tools: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class LLMResponse:
    """Response from an LLM backend."""
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    estimated_cost: float = 0.0
```

`src/quartermaster/llm/local.py`:
```python
"""llama-swap local LLM client (OpenAI-compatible API)."""

import json
from enum import Enum
from typing import Any

import httpx
import structlog

from quartermaster.llm.models import LLMRequest, LLMResponse, ToolCall, ChatMessage

logger = structlog.get_logger()


class LlamaSwapStatus(str, Enum):
    IDLE = "idle"
    PREFERRED_LOADED = "preferred_loaded"
    OTHER_LOADED = "other_loaded"
    UNREACHABLE = "unreachable"


class LocalLLMClient:
    """Client for llama-swap's OpenAI-compatible API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8200/v1",
        preferred_model: str = "qwen3.5-27b",
        timeout: int = 60,
    ) -> None:
        self._base_url = base_url
        self._preferred_model = preferred_model
        self._timeout = timeout
        # Derive the running endpoint from base_url
        # base_url is like http://localhost:8200/v1, running is at /running
        self._status_url = base_url.rsplit("/v1", 1)[0] + "/running"

    async def check_status(self) -> LlamaSwapStatus:
        """Check what's currently loaded in llama-swap."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self._status_url, timeout=5)
                data = resp.json()
                running = data.get("running", [])

                if not running:
                    return LlamaSwapStatus.IDLE

                loaded_models = [m.get("model", "") for m in running]
                if any(self._preferred_model in m for m in loaded_models):
                    return LlamaSwapStatus.PREFERRED_LOADED

                return LlamaSwapStatus.OTHER_LOADED

        except (httpx.ConnectError, httpx.TimeoutException):
            return LlamaSwapStatus.UNREACHABLE

    async def chat(self, request: LLMRequest, timeout: int | None = None) -> LLMResponse:
        """Send a chat completion request to llama-swap."""
        effective_timeout = timeout or self._timeout

        messages_payload = []
        for msg in request.messages:
            m: dict[str, Any] = {"role": msg.role}
            if msg.content is not None:
                m["content"] = msg.content
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.name:
                m["name"] = msg.name
            messages_payload.append(m)

        payload: dict[str, Any] = {
            "model": request.model or self._preferred_model,
            "messages": messages_payload,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if request.tools:
            payload["tools"] = request.tools

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                timeout=effective_timeout,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        message = choice["message"]

        tool_calls: list[ToolCall] = []
        if "tool_calls" in message and message["tool_calls"]:
            for tc in message["tool_calls"]:
                args = tc["function"].get("arguments", "{}")
                if isinstance(args, str):
                    args = json.loads(args)
                tool_calls.append(ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=args,
                ))

        usage = data.get("usage", {})
        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            model=data.get("model", self._preferred_model),
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/llm/test_local.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/llm/models.py src/quartermaster/llm/local.py tests/llm/test_local.py
git commit -m "feat: LLM types and llama-swap local client"
```

---

## Task 12: Anthropic Client

**Files:**
- Create: `src/quartermaster/llm/anthropic_client.py`
- Create: `tests/llm/test_anthropic_client.py`

- [ ] **Step 1: Write failing test**

`tests/llm/test_anthropic_client.py`:
```python
"""Tests for the Anthropic API client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from quartermaster.llm.anthropic_client import AnthropicClient
from quartermaster.llm.models import LLMRequest, ChatMessage


@pytest.mark.asyncio
async def test_chat_returns_response() -> None:
    """Test that chat converts between our types and Anthropic SDK."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(type="text", text="Hello!")]
    mock_message.model = "claude-sonnet-4-20250514"
    mock_message.usage.input_tokens = 10
    mock_message.usage.output_tokens = 20
    mock_message.stop_reason = "end_turn"

    with patch("quartermaster.llm.anthropic_client.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)
        mock_cls.return_value = mock_client

        client = AnthropicClient(api_key="test-key", default_model="claude-sonnet-4-20250514")
        request = LLMRequest(
            messages=[ChatMessage(role="user", content="Hi")],
        )
        response = await client.chat(request)
        assert response.content == "Hello!"
        assert response.tokens_in == 10
        assert response.tokens_out == 20


@pytest.mark.asyncio
async def test_anthropic_converts_tools_to_anthropic_format() -> None:
    """Test that OpenAI-format tools are converted to Anthropic format."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(type="text", text="ok")]
    mock_message.model = "claude-sonnet-4-20250514"
    mock_message.usage.input_tokens = 5
    mock_message.usage.output_tokens = 5
    mock_message.stop_reason = "end_turn"

    with patch("quartermaster.llm.anthropic_client.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)
        mock_cls.return_value = mock_client

        client = AnthropicClient(api_key="test-key")
        request = LLMRequest(
            messages=[ChatMessage(role="user", content="test")],
            tools=[{
                "type": "function",
                "function": {
                    "name": "test.tool",
                    "description": "A test",
                    "parameters": {"type": "object", "properties": {}},
                },
            }],
        )
        response = await client.chat(request)

        # Verify Anthropic format was used in the call
        call_kwargs = mock_client.messages.create.call_args
        tools = call_kwargs.kwargs.get("tools", [])
        assert tools[0]["name"] == "test.tool"
        assert "input_schema" in tools[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/llm/test_anthropic_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement anthropic_client.py**

`src/quartermaster/llm/anthropic_client.py`:
```python
"""Anthropic API client wrapper."""

from typing import Any

import structlog
from anthropic import AsyncAnthropic

from quartermaster.llm.models import LLMRequest, LLMResponse, ToolCall, ChatMessage

logger = structlog.get_logger()

# Rough cost per million tokens (USD) — update as pricing changes
COST_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
}


class AnthropicClient:
    """Client for the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._default_model = default_model

    async def chat(self, request: LLMRequest) -> LLMResponse:
        """Send a chat request to Anthropic."""
        model = request.model or self._default_model

        # Convert messages — extract system prompt, convert rest
        system_prompt = ""
        messages: list[dict[str, Any]] = []
        for msg in request.messages:
            if msg.role == "system":
                system_prompt = msg.content or ""
            else:
                m: dict[str, Any] = {"role": msg.role}
                if msg.content is not None:
                    m["content"] = msg.content
                if msg.tool_call_id:
                    m["tool_use_id"] = msg.tool_call_id
                messages.append(m)

        # Convert tools from OpenAI format to Anthropic format
        tools: list[dict[str, Any]] = []
        if request.tools:
            for tool in request.tools:
                fn = tool.get("function", {})
                tools.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {}),
                })

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)

        # Parse response
        content_text: str | None = None
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                content_text = block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))

        # Estimate cost
        cost_rates = COST_PER_MTOK.get(model, {"input": 3.0, "output": 15.0})
        estimated_cost = (
            (response.usage.input_tokens * cost_rates["input"] / 1_000_000)
            + (response.usage.output_tokens * cost_rates["output"] / 1_000_000)
        )

        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            model=model,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            estimated_cost=estimated_cost,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/llm/test_anthropic_client.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/llm/anthropic_client.py tests/llm/test_anthropic_client.py
git commit -m "feat: Anthropic API client with cost estimation"
```

---

## Task 13: LLM Router

**Files:**
- Create: `src/quartermaster/llm/router.py`
- Create: `tests/llm/test_router.py`

- [ ] **Step 1: Write failing test**

`tests/llm/test_router.py`:
```python
"""Tests for the smart LLM router."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from quartermaster.llm.router import LLMRouter
from quartermaster.llm.models import LLMRequest, LLMResponse, ChatMessage
from quartermaster.llm.local import LlamaSwapStatus
from quartermaster.core.usage import BudgetStatus


@pytest.fixture
def mock_local() -> MagicMock:
    client = MagicMock()
    client.check_status = AsyncMock(return_value=LlamaSwapStatus.PREFERRED_LOADED)
    client.chat = AsyncMock(return_value=LLMResponse(
        content="local response",
        tool_calls=[],
        model="qwen3.5-27b",
        tokens_in=10,
        tokens_out=20,
    ))
    return client


@pytest.fixture
def mock_anthropic() -> MagicMock:
    client = MagicMock()
    client.chat = AsyncMock(return_value=LLMResponse(
        content="cloud response",
        tool_calls=[],
        model="claude-sonnet-4-20250514",
        tokens_in=10,
        tokens_out=20,
        estimated_cost=0.001,
    ))
    return client


@pytest.fixture
def mock_usage() -> MagicMock:
    tracker = MagicMock()
    tracker.log = AsyncMock()
    tracker.get_budget_status = AsyncMock(return_value=BudgetStatus.OK)
    return tracker


@pytest.mark.asyncio
async def test_routes_to_local_when_preferred_loaded(
    mock_local: MagicMock,
    mock_anthropic: MagicMock,
    mock_usage: MagicMock,
) -> None:
    router = LLMRouter(
        local_client=mock_local,
        anthropic_client=mock_anthropic,
        usage_tracker=mock_usage,
    )
    request = LLMRequest(messages=[ChatMessage(role="user", content="hi")])
    response = await router.chat(request)
    assert response.content == "local response"
    mock_local.chat.assert_awaited_once()
    mock_anthropic.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_routes_to_local_when_idle(
    mock_local: MagicMock,
    mock_anthropic: MagicMock,
    mock_usage: MagicMock,
) -> None:
    mock_local.check_status = AsyncMock(return_value=LlamaSwapStatus.IDLE)
    router = LLMRouter(
        local_client=mock_local,
        anthropic_client=mock_anthropic,
        usage_tracker=mock_usage,
    )
    request = LLMRequest(messages=[ChatMessage(role="user", content="hi")])
    response = await router.chat(request)
    assert response.content == "local response"


@pytest.mark.asyncio
async def test_falls_back_to_anthropic_when_unreachable(
    mock_local: MagicMock,
    mock_anthropic: MagicMock,
    mock_usage: MagicMock,
) -> None:
    mock_local.check_status = AsyncMock(return_value=LlamaSwapStatus.UNREACHABLE)
    router = LLMRouter(
        local_client=mock_local,
        anthropic_client=mock_anthropic,
        usage_tracker=mock_usage,
    )
    request = LLMRequest(messages=[ChatMessage(role="user", content="hi")])
    response = await router.chat(request)
    assert response.content == "cloud response"
    mock_anthropic.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_falls_back_on_local_timeout(
    mock_local: MagicMock,
    mock_anthropic: MagicMock,
    mock_usage: MagicMock,
) -> None:
    import httpx
    mock_local.check_status = AsyncMock(return_value=LlamaSwapStatus.PREFERRED_LOADED)
    mock_local.chat = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    router = LLMRouter(
        local_client=mock_local,
        anthropic_client=mock_anthropic,
        usage_tracker=mock_usage,
    )
    request = LLMRequest(messages=[ChatMessage(role="user", content="hi")])
    response = await router.chat(request)
    assert response.content == "cloud response"


@pytest.mark.asyncio
async def test_usage_logged_for_cloud_calls(
    mock_local: MagicMock,
    mock_anthropic: MagicMock,
    mock_usage: MagicMock,
) -> None:
    mock_local.check_status = AsyncMock(return_value=LlamaSwapStatus.UNREACHABLE)
    router = LLMRouter(
        local_client=mock_local,
        anthropic_client=mock_anthropic,
        usage_tracker=mock_usage,
    )
    request = LLMRequest(messages=[ChatMessage(role="user", content="hi")])
    await router.chat(request)
    mock_usage.log.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/llm/test_router.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement router.py**

`src/quartermaster/llm/router.py`:
```python
"""Smart LLM routing — local-first with Anthropic fallback."""

from typing import Any

import httpx
import structlog

from quartermaster.llm.local import LocalLLMClient, LlamaSwapStatus
from quartermaster.llm.anthropic_client import AnthropicClient
from quartermaster.llm.models import LLMRequest, LLMResponse
from quartermaster.core.usage import UsageTracker, UsageRecord, BudgetStatus

logger = structlog.get_logger()


class LLMRouter:
    """Routes LLM requests to the best available backend.

    Priority: local (llama-swap) → Anthropic API fallback.
    """

    def __init__(
        self,
        local_client: LocalLLMClient | Any,
        anthropic_client: AnthropicClient | Any | None = None,
        usage_tracker: UsageTracker | Any | None = None,
    ) -> None:
        self._local = local_client
        self._anthropic = anthropic_client
        self._usage = usage_tracker

    async def chat(
        self,
        request: LLMRequest,
        purpose: str = "chat",
        plugin_name: str = "core",
    ) -> LLMResponse:
        """Route a chat request to the best available backend."""
        status = await self._local.check_status()
        logger.debug("llm_routing", llama_swap_status=status.value)

        # Try local first if available
        if status in (LlamaSwapStatus.IDLE, LlamaSwapStatus.PREFERRED_LOADED):
            try:
                response = await self._local.chat(request)
                await self._log_usage(response, "llama-swap", purpose, plugin_name)
                return response
            except httpx.TimeoutException:
                logger.warning("local_llm_timeout", status=status.value)
            except Exception:
                logger.exception("local_llm_error")

        # Try local with swap timeout for OTHER_LOADED
        if status == LlamaSwapStatus.OTHER_LOADED:
            try:
                response = await self._local.chat(request, timeout=120)
                await self._log_usage(response, "llama-swap", purpose, plugin_name)
                return response
            except httpx.TimeoutException:
                logger.warning("local_llm_swap_timeout")
            except Exception:
                logger.exception("local_llm_error")

        # Fall back to Anthropic — check budget first
        if self._anthropic:
            if self._usage:
                budget_status = await self._usage.get_budget_status()
                if budget_status == BudgetStatus.BLOCKED:
                    logger.warning("anthropic_blocked_by_budget")
                    return LLMResponse(
                        content="API budget exhausted for this month. Waiting for local LLM availability.",
                        model="budget-blocked",
                    )
            try:
                response = await self._anthropic.chat(request)
                await self._log_usage(response, "anthropic", purpose, plugin_name)
                return response
            except Exception:
                logger.exception("anthropic_error")

        # Both failed
        return LLMResponse(
            content="I'm having trouble reaching my backends — try again in a few minutes.",
            model="error",
        )

    async def get_local_status(self) -> LlamaSwapStatus:
        """Check what's currently loaded in llama-swap (public API)."""
        return await self._local.check_status()

    async def _log_usage(
        self,
        response: LLMResponse,
        provider: str,
        purpose: str,
        plugin_name: str,
    ) -> None:
        """Log usage if tracker is available."""
        if self._usage:
            await self._usage.log(UsageRecord(
                provider=provider,
                model=response.model,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                estimated_cost=response.estimated_cost,
                purpose=purpose,
                plugin_name=plugin_name,
            ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/llm/test_router.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/llm/router.py tests/llm/test_router.py
git commit -m "feat: smart LLM router with local-first routing and fallback"
```

---

## Task 14: Transport Types and Manager

**Files:**
- Create: `src/quartermaster/transport/types.py`
- Create: `src/quartermaster/transport/manager.py`
- Create: `tests/transport/test_types.py`

- [ ] **Step 1: Write failing test**

`tests/transport/test_types.py`:
```python
"""Tests for transport types."""

from quartermaster.transport.types import (
    InboundMessage,
    OutboundMessage,
    TransportType,
)


def test_inbound_message() -> None:
    msg = InboundMessage(
        transport=TransportType.TELEGRAM,
        chat_id="12345",
        user_id="67890",
        text="hello",
    )
    assert msg.transport == TransportType.TELEGRAM
    assert msg.text == "hello"


def test_outbound_message() -> None:
    msg = OutboundMessage(
        transport=TransportType.TELEGRAM,
        chat_id="12345",
        text="response",
    )
    assert msg.text == "response"


def test_outbound_message_with_inline_keyboard() -> None:
    msg = OutboundMessage(
        transport=TransportType.TELEGRAM,
        chat_id="12345",
        text="Approve?",
        inline_keyboard=[
            [{"text": "Yes", "callback_data": "approve:123"}],
            [{"text": "No", "callback_data": "reject:123"}],
        ],
    )
    assert len(msg.inline_keyboard) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/transport/test_types.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement types.py and manager.py**

`src/quartermaster/transport/types.py`:
```python
"""Transport message types."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TransportType(str, Enum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    WEBHOOK = "webhook"
    MCP = "mcp"


@dataclass
class InboundMessage:
    """A message received from a transport."""
    transport: TransportType
    chat_id: str
    user_id: str
    text: str
    message_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage:
    """A message to send via a transport."""
    transport: TransportType
    chat_id: str
    text: str
    reply_to_message_id: str | None = None
    inline_keyboard: list[list[dict[str, str]]] = field(default_factory=list)
    voice_data: bytes | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

`src/quartermaster/transport/manager.py`:
```python
"""Transport manager — abstracts message delivery."""

from typing import Any, Protocol

import structlog

from quartermaster.transport.types import (
    InboundMessage,
    OutboundMessage,
    TransportType,
)

logger = structlog.get_logger()


class Transport(Protocol):
    """Protocol for transport implementations."""

    transport_type: TransportType

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, message: OutboundMessage) -> str: ...


class TransportManager:
    """Manages multiple transports and routes messages."""

    def __init__(self) -> None:
        self._transports: dict[TransportType, Transport] = {}

    def register(self, transport: Transport) -> None:
        """Register a transport."""
        self._transports[transport.transport_type] = transport
        logger.info("transport_registered", type=transport.transport_type.value)

    async def send(self, message: OutboundMessage) -> str:
        """Send a message via the appropriate transport.

        Returns the external message ID.
        """
        transport = self._transports.get(message.transport)
        if transport is None:
            raise ValueError(f"No transport registered for {message.transport}")
        return await transport.send(message)

    async def start_all(self) -> None:
        """Start all registered transports."""
        for transport in self._transports.values():
            await transport.start()

    async def stop_all(self) -> None:
        """Stop all registered transports."""
        for transport in self._transports.values():
            await transport.stop()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/transport/test_types.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/transport/ tests/transport/
git commit -m "feat: transport types and manager abstraction"
```

---

## Task 15: Conversation Manager

**Files:**
- Create: `src/quartermaster/conversation/models.py`
- Create: `src/quartermaster/conversation/manager.py`
- Create: `tests/conversation/test_manager.py`

- [ ] **Step 1: Write failing test**

`tests/conversation/test_manager.py`:
```python
"""Tests for conversation management."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from quartermaster.conversation.manager import ConversationManager
from quartermaster.conversation.models import Conversation, Turn
from quartermaster.core.config import ConversationConfig


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    db.fetch_one = AsyncMock(return_value=None)
    db.fetch_all = AsyncMock(return_value=[])
    db.execute = AsyncMock(return_value=1)
    return db


@pytest.fixture
def config() -> ConversationConfig:
    return ConversationConfig(
        context_window_max_turns=20,
        context_window_max_tokens=8000,
        idle_timeout_hours=4,
    )


@pytest.mark.asyncio
async def test_get_or_create_conversation_creates_new(
    mock_db: MagicMock,
    config: ConversationConfig,
) -> None:
    manager = ConversationManager(db=mock_db, config=config)
    conv = await manager.get_or_create("telegram", "chat123")
    assert conv.transport == "telegram"
    assert conv.external_chat_id == "chat123"
    mock_db.execute.assert_awaited()  # INSERT was called


@pytest.mark.asyncio
async def test_save_and_get_context_window(
    mock_db: MagicMock,
    config: ConversationConfig,
) -> None:
    # Simulate existing turns in DB
    mock_db.fetch_all = AsyncMock(return_value=[
        (b"\x01" * 16, "user", "hello", None, None, None, 5, 0),
        (b"\x02" * 16, "assistant", "hi there", None, None, None, 0, 10),
    ])

    manager = ConversationManager(db=mock_db, config=config)
    conv = Conversation(
        conversation_id="test-id",
        transport="telegram",
        external_chat_id="chat123",
    )
    messages = await manager.get_context_window(conv)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/conversation/test_manager.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement models.py and manager.py**

`src/quartermaster/conversation/models.py`:
```python
"""Conversation data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Turn:
    """A single turn in a conversation."""
    turn_id: str = ""
    conversation_id: str = ""
    role: str = ""  # user, assistant, tool
    content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    llm_backend: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    estimated_cost: float = 0.0
    created_at: datetime | None = None


@dataclass
class Conversation:
    """A conversation session."""
    conversation_id: str = ""
    transport: str = ""
    external_chat_id: str = ""
    created_at: datetime | None = None
    last_active_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

`src/quartermaster/conversation/manager.py`:
```python
"""Conversation history and context window management."""

import json
from typing import Any
from datetime import datetime, timedelta, timezone

import structlog

from quartermaster.conversation.models import Conversation, Turn
from quartermaster.core.config import ConversationConfig
from quartermaster.llm.models import ChatMessage

logger = structlog.get_logger()


class ConversationManager:
    """Manages conversation history and context window assembly."""

    def __init__(self, db: Any, config: ConversationConfig) -> None:
        self._db = db
        self._config = config

    async def get_or_create(
        self, transport: str, chat_id: str
    ) -> Conversation:
        """Get the active conversation for a chat, or create a new one."""
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=self._config.idle_timeout_hours
        )

        row = await self._db.fetch_one(
            """SELECT conversation_id, transport, external_chat_id,
                      created_at, last_active_at
               FROM qm.conversations
               WHERE transport = :transport
                 AND external_chat_id = :chat_id
                 AND last_active_at > :cutoff
               ORDER BY last_active_at DESC
               FETCH FIRST 1 ROW ONLY""",
            {"transport": transport, "chat_id": chat_id, "cutoff": cutoff},
        )

        if row:
            return Conversation(
                conversation_id=str(row[0]),
                transport=row[1],
                external_chat_id=row[2],
                created_at=row[3],
                last_active_at=row[4],
            )

        # Create new conversation
        conv = Conversation(transport=transport, external_chat_id=chat_id)
        await self._db.execute(
            """INSERT INTO qm.conversations
               (transport, external_chat_id)
               VALUES (:transport, :chat_id)""",
            {"transport": transport, "chat_id": chat_id},
        )
        logger.info("conversation_created", transport=transport, chat_id=chat_id)
        return conv

    async def save_turn(self, conv: Conversation, turn: Turn) -> None:
        """Save a turn to the conversation."""
        await self._db.execute(
            """INSERT INTO qm.turns
               (conversation_id, role, content, tool_calls, tool_results,
                llm_backend, tokens_in, tokens_out, estimated_cost)
               VALUES (:conv_id, :role, :content, :tool_calls, :tool_results,
                       :backend, :tokens_in, :tokens_out, :cost)""",
            {
                "conv_id": conv.conversation_id,
                "role": turn.role,
                "content": turn.content,
                "tool_calls": json.dumps(turn.tool_calls) if turn.tool_calls else None,
                "tool_results": json.dumps(turn.tool_results) if turn.tool_results else None,
                "backend": turn.llm_backend,
                "tokens_in": turn.tokens_in,
                "tokens_out": turn.tokens_out,
                "cost": turn.estimated_cost,
            },
        )

        # Update last_active_at
        await self._db.execute(
            """UPDATE qm.conversations
               SET last_active_at = systimestamp
               WHERE conversation_id = :conv_id""",
            {"conv_id": conv.conversation_id},
        )

    async def force_new_conversation(self, transport: str, chat_id: str) -> None:
        """Force the next message to start a new conversation.

        Sets last_active_at to a time older than idle_timeout, so
        get_or_create will create a fresh conversation.
        """
        await self._db.execute(
            """UPDATE qm.conversations
               SET last_active_at = systimestamp - NUMTODSMINTERVAL(:hours, 'HOUR')
               WHERE transport = :transport
                 AND external_chat_id = :chat_id
                 AND last_active_at > systimestamp - INTERVAL :hours2 HOUR""",
            {
                "hours": str(self._config.idle_timeout_hours + 1),
                "transport": transport,
                "chat_id": chat_id,
                "hours2": str(self._config.idle_timeout_hours),
            },
        )

    async def get_context_window(self, conv: Conversation) -> list[ChatMessage]:
        """Load recent turns and build the context window.

        Uses a token budget to determine how many turns to include.
        Fetches up to max_turns, then trims from oldest if token count
        exceeds max_tokens.
        """
        rows = await self._db.fetch_all(
            """SELECT turn_id, role, content, tool_calls, tool_results,
                      llm_backend, tokens_in, tokens_out
               FROM qm.turns
               WHERE conversation_id = :conv_id
               ORDER BY created_at DESC
               FETCH FIRST :max_turns ROWS ONLY""",
            {
                "conv_id": conv.conversation_id,
                "max_turns": self._config.context_window_max_turns,
            },
        )

        # Reverse to chronological order
        rows = list(reversed(rows))

        # Build messages with token budget enforcement
        messages: list[ChatMessage] = []
        total_tokens = 0
        max_tokens = self._config.context_window_max_tokens

        for row in rows:
            role = row[1]
            content = row[2]
            tool_calls_raw = row[3]

            msg = ChatMessage(role=role, content=content)
            if tool_calls_raw:
                parsed = json.loads(tool_calls_raw) if isinstance(tool_calls_raw, str) else tool_calls_raw
                msg.tool_calls = parsed

            # Estimate tokens: ~4 chars per token (rough but fast)
            msg_text = (content or "") + str(tool_calls_raw or "")
            estimated_tokens = len(msg_text) // 4
            total_tokens += estimated_tokens
            messages.append(msg)

        # Trim oldest messages if over token budget
        while total_tokens > max_tokens and len(messages) > 1:
            removed = messages.pop(0)
            removed_text = (removed.content or "") + str(removed.tool_calls or "")
            total_tokens -= len(removed_text) // 4

        return messages
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/conversation/test_manager.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/conversation/ tests/conversation/
git commit -m "feat: conversation manager with history and context window"
```

---

## Task 16: Telegram Transport

**Files:**
- Create: `src/quartermaster/transport/telegram.py`

This task implements the Telegram handler using `python-telegram-bot`. Due to the complexity of mocking the Telegram library, we test this primarily through integration tests. The handler's job is thin: receive messages, normalize to `InboundMessage`, emit events, and send `OutboundMessage` responses.

- [ ] **Step 1: Implement telegram.py**

`src/quartermaster/transport/telegram.py`:
```python
"""Telegram transport using python-telegram-bot."""

from typing import Any

import structlog
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from quartermaster.transport.types import (
    InboundMessage,
    OutboundMessage,
    TransportType,
)
from quartermaster.core.events import EventBus

logger = structlog.get_logger()


class TelegramTransport:
    """Telegram bot transport via long-polling."""

    transport_type = TransportType.TELEGRAM

    def __init__(
        self,
        bot_token: str,
        allowed_user_ids: list[int],
        events: EventBus,
    ) -> None:
        self._bot_token = bot_token
        self._allowed_user_ids = set(allowed_user_ids)
        self._events = events
        self._app: Application | None = None  # type: ignore[type-arg]

    async def start(self) -> None:
        """Initialize and start the Telegram bot."""
        self._app = (
            Application.builder()
            .token(self._bot_token)
            .build()
        )

        # Register handlers
        self._app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self._handle_message,
        ))
        self._app.add_handler(MessageHandler(
            filters.COMMAND,
            self._handle_command,
        ))
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)  # type: ignore[union-attr]
        logger.info("telegram_started")

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._app:
            await self._app.updater.stop()  # type: ignore[union-attr]
            await self._app.stop()
            await self._app.shutdown()
            logger.info("telegram_stopped")

    async def send(self, message: OutboundMessage) -> str:
        """Send a message via Telegram."""
        assert self._app is not None
        bot = self._app.bot

        kwargs: dict[str, Any] = {
            "chat_id": int(message.chat_id),
            "text": message.text,
        }

        if message.reply_to_message_id:
            kwargs["reply_to_message_id"] = int(message.reply_to_message_id)

        if message.inline_keyboard:
            buttons = [
                [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])
                 for btn in row]
                for row in message.inline_keyboard
            ]
            kwargs["reply_markup"] = InlineKeyboardMarkup(buttons)

        sent = await bot.send_message(**kwargs)

        if message.voice_data:
            await bot.send_voice(
                chat_id=int(message.chat_id),
                voice=message.voice_data,
            )

        return str(sent.message_id)

    def _is_allowed(self, user_id: int) -> bool:
        """Check if a user is in the allowlist."""
        return user_id in self._allowed_user_ids

    async def _handle_message(self, update: Update, context: Any) -> None:
        """Handle incoming text messages."""
        if not update.effective_user or not update.effective_message:
            return
        if not self._is_allowed(update.effective_user.id):
            return

        # Show typing indicator
        assert update.effective_chat is not None
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing",
        )

        inbound = InboundMessage(
            transport=TransportType.TELEGRAM,
            chat_id=str(update.effective_chat.id),
            user_id=str(update.effective_user.id),
            text=update.effective_message.text or "",
            message_id=str(update.effective_message.message_id),
        )

        await self._events.emit("message.received", {"message": inbound})

    async def _handle_command(self, update: Update, context: Any) -> None:
        """Handle incoming commands (forward as messages)."""
        # Commands are handled the same way — the LLM or command plugin routes them
        await self._handle_message(update, context)

    async def _handle_callback(self, update: Update, context: Any) -> None:
        """Handle inline keyboard callbacks (approval flow)."""
        query = update.callback_query
        if not query or not query.from_user:
            return
        if not self._is_allowed(query.from_user.id):
            return

        await query.answer()
        await self._events.emit("approval.callback", {
            "callback_data": query.data,
            "message_id": str(query.message.message_id) if query.message else "",
            "chat_id": str(query.message.chat_id) if query.message else "",
            "user_id": str(query.from_user.id),
        })
```

- [ ] **Step 2: Verify imports work**

Run: `python -c "from quartermaster.transport.telegram import TelegramTransport; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/quartermaster/transport/telegram.py
git commit -m "feat: Telegram transport with long-polling and inline keyboards"
```

---

## Task 17: Chat Plugin

**Files:**
- Create: `plugins/chat/plugin.py`
- Create: `plugins/chat/prompts.py`
- Create: `tests/plugins/test_chat.py`

- [ ] **Step 1: Write failing test**

`tests/plugins/test_chat.py`:
```python
"""Tests for the chat plugin."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from plugins.chat.plugin import ChatPlugin
from plugins.chat.prompts import DEFAULT_PERSONA
from quartermaster.plugin.health import HealthStatus


def test_default_persona_exists() -> None:
    assert "Quartermaster" in DEFAULT_PERSONA


@pytest.mark.asyncio
async def test_chat_plugin_health() -> None:
    plugin = ChatPlugin()
    report = await plugin.health()
    assert report.status == HealthStatus.OK


def test_chat_plugin_metadata() -> None:
    plugin = ChatPlugin()
    assert plugin.name == "chat"
    assert plugin.version == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src:. pytest tests/plugins/test_chat.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement prompts.py and plugin.py**

`plugins/chat/prompts.py`:
```python
"""System prompts for the Quartermaster persona."""

DEFAULT_PERSONA = """You are Quartermaster, a personal AI assistant. You are concise, direct, \
and action-oriented. When you can answer directly, do so. When a task requires a tool, call it \
without preamble. For actions with external consequences, always present a draft for approval \
before executing. Keep status reports scannable — use bullet points, not paragraphs. Match the \
user's tone — brief messages get brief replies."""
```

`plugins/chat/plugin.py`:
```python
"""Chat plugin — basic LLM conversation handling."""

from typing import Any

import structlog

from quartermaster.plugin.base import QuartermasterPlugin
from quartermaster.plugin.context import PluginContext
from quartermaster.plugin.health import HealthReport, HealthStatus
from quartermaster.llm.models import LLMRequest, ChatMessage
from quartermaster.conversation.models import Turn
from quartermaster.transport.types import OutboundMessage, TransportType
from plugins.chat.prompts import DEFAULT_PERSONA

logger = structlog.get_logger()


class ChatPlugin(QuartermasterPlugin):
    """Handles basic conversational messages."""

    name = "chat"
    version = "0.1.0"
    dependencies: list[str] = []

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None
        self._persona: str = DEFAULT_PERSONA

    async def setup(self, ctx: PluginContext) -> None:
        self._ctx = ctx
        # Use persona from config if available
        if hasattr(ctx.config, 'persona') and ctx.config.persona:
            self._persona = ctx.config.persona

        ctx.events.subscribe("message.received", self._handle_message)
        logger.info("chat_plugin_ready")

    async def teardown(self) -> None:
        pass

    async def health(self) -> HealthReport:
        return HealthReport(status=HealthStatus.OK)

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle an incoming message by routing through the LLM."""
        assert self._ctx is not None
        message = data["message"]

        # Skip command messages — let the commands plugin handle those
        if message.text.startswith("/"):
            return

        # Get or create conversation
        conv = await self._ctx.conversation.get_or_create(
            message.transport.value, message.chat_id
        )

        # Build context window
        history = await self._ctx.conversation.get_context_window(conv)

        # Build LLM request
        messages = [ChatMessage(role="system", content=self._persona)]
        messages.extend(history)
        messages.append(ChatMessage(role="user", content=message.text))

        # Get available tools
        tool_schemas = self._ctx.tools.get_tool_schemas()

        request = LLMRequest(messages=messages, tools=tool_schemas)

        # Route through LLM
        response = await self._ctx.llm.chat(request, purpose="chat", plugin_name="chat")

        # Handle tool calls if present
        if response.tool_calls:
            await self._handle_tool_calls(response, messages, message, conv)
            return

        # Send response
        await self._ctx.transport.send(OutboundMessage(
            transport=message.transport,
            chat_id=message.chat_id,
            text=response.content or "I couldn't generate a response.",
        ))

        # Save conversation turns
        await self._ctx.conversation.save_turn(conv, Turn(
            role="user", content=message.text,
        ))
        await self._ctx.conversation.save_turn(conv, Turn(
            role="assistant",
            content=response.content,
            llm_backend=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            estimated_cost=response.estimated_cost,
        ))

    async def _handle_tool_calls(
        self,
        response: Any,
        messages: list[ChatMessage],
        original_message: Any,
        conv: Any,
    ) -> None:
        """Execute tool calls and get final LLM response."""
        assert self._ctx is not None
        max_iterations = 5
        current_response = response

        for _ in range(max_iterations):
            if not current_response.tool_calls:
                break

            # Execute each tool call
            for tool_call in current_response.tool_calls:
                tool_def = self._ctx.tools.get(tool_call.name)
                if tool_def and tool_def.approval_tier.value == "confirm":
                    # TODO: Route through approval manager (Task for later)
                    result = {"status": "approval_required", "message": "This action needs approval."}
                else:
                    result = await self._ctx.tools.execute(tool_call.name, tool_call.arguments)

                # Add tool call and result to messages
                messages.append(ChatMessage(
                    role="assistant",
                    tool_calls=[{
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": str(tool_call.arguments),
                        },
                    }],
                ))
                messages.append(ChatMessage(
                    role="tool",
                    content=str(result),
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                ))

            # Get next LLM response
            tool_schemas = self._ctx.tools.get_tool_schemas()
            request = LLMRequest(messages=messages, tools=tool_schemas)
            current_response = await self._ctx.llm.chat(
                request, purpose="tool-followup", plugin_name="chat"
            )

        # Send final response
        final_text = current_response.content or "Done."
        await self._ctx.transport.send(OutboundMessage(
            transport=original_message.transport,
            chat_id=original_message.chat_id,
            text=final_text,
        ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src:. pytest tests/plugins/test_chat.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/chat/ tests/plugins/test_chat.py
git commit -m "feat: chat plugin with LLM conversation and tool calling loop"
```

---

## Task 18: Commands Plugin

**Files:**
- Create: `plugins/commands/plugin.py`
- Create: `tests/plugins/test_commands.py`

- [ ] **Step 1: Write failing test**

`tests/plugins/test_commands.py`:
```python
"""Tests for the commands plugin."""

import pytest
from plugins.commands.plugin import CommandsPlugin
from quartermaster.plugin.health import HealthStatus


def test_commands_plugin_metadata() -> None:
    plugin = CommandsPlugin()
    assert plugin.name == "commands"


@pytest.mark.asyncio
async def test_commands_plugin_health() -> None:
    plugin = CommandsPlugin()
    report = await plugin.health()
    assert report.status == HealthStatus.OK


def test_commands_list() -> None:
    plugin = CommandsPlugin()
    assert "status" in plugin.COMMANDS
    assert "help" in plugin.COMMANDS
    assert "models" in plugin.COMMANDS
    assert "spend" in plugin.COMMANDS
    assert "new" in plugin.COMMANDS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src:. pytest tests/plugins/test_commands.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement plugin.py**

`plugins/commands/plugin.py`:
```python
"""Commands plugin — handles /status, /models, /help, /spend, /new."""

from typing import Any

import structlog

from quartermaster.plugin.base import QuartermasterPlugin
from quartermaster.plugin.context import PluginContext
from quartermaster.plugin.health import HealthReport, HealthStatus
from quartermaster.transport.types import OutboundMessage

logger = structlog.get_logger()


class CommandsPlugin(QuartermasterPlugin):
    """Handles bot commands."""

    name = "commands"
    version = "0.1.0"
    dependencies: list[str] = []

    COMMANDS = {
        "help": "Show available commands",
        "status": "Show system and plugin health",
        "models": "Show loaded LLM models",
        "spend": "Show API usage and budget",
        "new": "Start a new conversation",
    }

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None

    async def setup(self, ctx: PluginContext) -> None:
        self._ctx = ctx
        ctx.events.subscribe("message.received", self._handle_command)
        logger.info("commands_plugin_ready")

    async def teardown(self) -> None:
        pass

    async def health(self) -> HealthReport:
        return HealthReport(status=HealthStatus.OK)

    async def _handle_command(self, data: dict[str, Any]) -> None:
        """Handle command messages."""
        assert self._ctx is not None
        message = data["message"]

        if not message.text.startswith("/"):
            return

        parts = message.text.split(maxsplit=1)
        command = parts[0].lstrip("/").lower()
        # Strip @botname if present
        if "@" in command:
            command = command.split("@")[0]

        handler = {
            "help": self._cmd_help,
            "status": self._cmd_status,
            "models": self._cmd_models,
            "spend": self._cmd_spend,
            "new": self._cmd_new,
        }.get(command)

        if handler:
            await handler(message)

    async def _cmd_help(self, message: Any) -> None:
        """Show available commands."""
        assert self._ctx is not None
        lines = ["**Quartermaster Commands:**", ""]
        for cmd, desc in self.COMMANDS.items():
            lines.append(f"/{cmd} — {desc}")

        tools = self._ctx.tools.list_tools()
        if tools:
            lines.append("")
            lines.append(f"**Available tools:** {len(tools)}")

        await self._ctx.transport.send(OutboundMessage(
            transport=message.transport,
            chat_id=message.chat_id,
            text="\n".join(lines),
        ))

    async def _cmd_status(self, message: Any) -> None:
        """Show system and plugin health."""
        assert self._ctx is not None
        # TODO: Aggregate plugin health from plugin loader
        await self._ctx.transport.send(OutboundMessage(
            transport=message.transport,
            chat_id=message.chat_id,
            text="**Status:** All systems operational\n(detailed health coming soon)",
        ))

    async def _cmd_models(self, message: Any) -> None:
        """Show loaded LLM models."""
        assert self._ctx is not None
        try:
            status = await self._ctx.llm.get_local_status()
            await self._ctx.transport.send(OutboundMessage(
                transport=message.transport,
                chat_id=message.chat_id,
                text=f"**LLM Status:** {status.value}",
            ))
        except Exception as e:
            await self._ctx.transport.send(OutboundMessage(
                transport=message.transport,
                chat_id=message.chat_id,
                text=f"**LLM Status:** Error checking — {e}",
            ))

    async def _cmd_spend(self, message: Any) -> None:
        """Show API usage and budget."""
        assert self._ctx is not None
        try:
            summary = await self._ctx.usage.get_spend_summary()
            text = (
                f"**API Budget:**\n"
                f"• Spent: ${summary['monthly_spend']:.2f} / ${summary['monthly_budget']:.2f}\n"
                f"• Used: {summary['percent_used']:.1f}%\n"
                f"• Status: {summary['status']}"
            )
        except Exception:
            text = "**API Budget:** Unable to retrieve spend data"

        await self._ctx.transport.send(OutboundMessage(
            transport=message.transport,
            chat_id=message.chat_id,
            text=text,
        ))

    async def _cmd_new(self, message: Any) -> None:
        """Start a new conversation by resetting the idle timeout boundary."""
        assert self._ctx is not None
        # Touch the conversation to create a boundary — next message
        # will start a fresh conversation since we force a gap
        await self._ctx.conversation.force_new_conversation(
            message.transport.value, message.chat_id
        )
        await self._ctx.transport.send(OutboundMessage(
            transport=message.transport,
            chat_id=message.chat_id,
            text="New conversation started. Previous context cleared.",
        ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src:. pytest tests/plugins/test_commands.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/commands/ tests/plugins/test_commands.py
git commit -m "feat: commands plugin with /status, /models, /help, /spend, /new"
```

---

## Task 19: Briefing Plugin Skeleton

**Files:**
- Create: `plugins/briefing/plugin.py`
- Create: `plugins/briefing/templates.py`

- [ ] **Step 1: Implement templates.py**

`plugins/briefing/templates.py`:
```python
"""Briefing text formatting templates."""


def format_morning_briefing(sections: dict[str, str]) -> str:
    """Format the morning briefing from section data."""
    lines = ["**Good morning! Here's your briefing:**", ""]

    for title, content in sections.items():
        if content:  # Only include sections with data
            lines.append(f"**{title}**")
            lines.append(content)
            lines.append("")

    if len(lines) <= 2:
        lines.append("No data sources configured yet. Plugins will add content as they're installed.")

    return "\n".join(lines)
```

- [ ] **Step 2: Implement plugin.py**

`plugins/briefing/plugin.py`:
```python
"""Briefing plugin — scheduled briefing skeleton.

Phase 1: Emits basic system health.
Phase 3+: Calls email, calendar, news tools as they become available.
"""

from typing import Any

import structlog

from quartermaster.plugin.base import QuartermasterPlugin
from quartermaster.plugin.context import PluginContext
from quartermaster.plugin.health import HealthReport, HealthStatus
from quartermaster.transport.types import OutboundMessage, TransportType
from plugins.briefing.templates import format_morning_briefing

logger = structlog.get_logger()


class BriefingPlugin(QuartermasterPlugin):
    """Scheduled briefings — grows with each phase."""

    name = "briefing"
    version = "0.1.0"
    dependencies: list[str] = []

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None

    async def setup(self, ctx: PluginContext) -> None:
        self._ctx = ctx
        ctx.events.subscribe("schedule.briefing.morning", self._morning_briefing)
        ctx.events.subscribe("schedule.briefing.evening", self._evening_briefing)
        ctx.events.subscribe("schedule.briefing.weekly", self._weekly_briefing)
        ctx.events.subscribe("briefing.ready", self._deliver_briefing)
        logger.info("briefing_plugin_ready")

    async def _deliver_briefing(self, data: dict[str, Any]) -> None:
        """Deliver a composed briefing to all allowed users via Telegram."""
        assert self._ctx is not None
        text = data.get("text", "")
        if not text:
            return
        # Send to each configured user
        for user_id in self._ctx.config.allowed_user_ids:
            await self._ctx.transport.send(OutboundMessage(
                transport=TransportType.TELEGRAM,
                chat_id=str(user_id),
                text=text,
            ))

    async def teardown(self) -> None:
        pass

    async def health(self) -> HealthReport:
        return HealthReport(status=HealthStatus.OK)

    async def _morning_briefing(self, data: dict[str, Any]) -> None:
        """Compose and deliver the morning briefing."""
        assert self._ctx is not None
        sections: dict[str, str] = {}

        # Phase 1: basic system status only
        # Future phases add: calendar, email, news, app store, infra
        try:
            status = await self._ctx.llm.get_local_status()
            sections["System"] = f"• LLM: {status.value}"
        except Exception:
            sections["System"] = "• LLM: unable to check"

        text = format_morning_briefing(sections)

        # Send to all configured chat IDs
        # For now, we rely on the config to know where to send
        # This will be refined as we build out transport management
        await self._ctx.events.emit("briefing.ready", {
            "type": "morning",
            "text": text,
        })

    async def _evening_briefing(self, data: dict[str, Any]) -> None:
        """Compose and deliver the evening briefing."""
        # Skeleton — will be fleshed out in Phase 3+
        await self._ctx.events.emit("briefing.ready", {  # type: ignore[union-attr]
            "type": "evening",
            "text": "**Evening summary:** No data sources configured yet.",
        })

    async def _weekly_briefing(self, data: dict[str, Any]) -> None:
        """Compose and deliver the weekly briefing."""
        # Skeleton — will be fleshed out in Phase 4+
        await self._ctx.events.emit("briefing.ready", {  # type: ignore[union-attr]
            "type": "weekly",
            "text": "**Weekly roundup:** No data sources configured yet.",
        })
```

- [ ] **Step 3: Commit**

```bash
git add plugins/briefing/
git commit -m "feat: briefing plugin skeleton with scheduled event handlers"
```

---

## Task 20: Metrics Endpoint

**Files:**
- Create: `src/quartermaster/core/metrics.py`

- [ ] **Step 1: Implement metrics.py**

`src/quartermaster/core/metrics.py`:
```python
"""Prometheus metrics endpoint."""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from aiohttp import web

import structlog

logger = structlog.get_logger()

# LLM metrics
llm_requests_total = Counter(
    "qm_llm_requests_total",
    "Total LLM requests",
    ["provider", "model", "purpose"],
)
llm_request_duration = Histogram(
    "qm_llm_request_duration_seconds",
    "LLM request duration",
    ["provider"],
)
llm_tokens_total = Counter(
    "qm_llm_tokens_total",
    "Total tokens processed",
    ["provider", "direction"],  # direction: input/output
)
llm_cost_total = Counter(
    "qm_llm_cost_usd_total",
    "Total API cost in USD",
    ["provider"],
)

# Tool metrics
tool_invocations_total = Counter(
    "qm_tool_invocations_total",
    "Total tool invocations",
    ["tool", "status"],  # status: success/error
)

# Message metrics
messages_total = Counter(
    "qm_messages_total",
    "Total messages",
    ["transport", "direction"],  # direction: inbound/outbound
)

# Plugin health
plugin_health = Gauge(
    "qm_plugin_health",
    "Plugin health status (1=ok, 0.5=degraded, 0=down)",
    ["plugin"],
)

# Budget
budget_used_usd = Gauge(
    "qm_budget_used_usd",
    "Current month API spend in USD",
)
budget_limit_usd = Gauge(
    "qm_budget_limit_usd",
    "Monthly API budget limit in USD",
)


async def metrics_handler(request: web.Request) -> web.Response:
    """HTTP handler for /metrics endpoint."""
    return web.Response(
        body=generate_latest(),
        content_type=CONTENT_TYPE_LATEST,
    )


async def start_metrics_server(port: int) -> web.AppRunner:
    """Start the Prometheus metrics HTTP server."""
    app = web.Application()
    app.router.add_get("/metrics", metrics_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("metrics_server_started", port=port)
    return runner
```

Note: `aiohttp` is already in `requirements.txt` (added in Task 1).

- [ ] **Step 2: Commit**

```bash
git add src/quartermaster/core/metrics.py requirements.txt
git commit -m "feat: Prometheus metrics endpoint with LLM, tool, and budget gauges"
```

---

## Task 21: Application Bootstrap

**Files:**
- Create: `src/quartermaster/core/app.py`
- Modify: `src/quartermaster/__main__.py`

This is the wiring task — connecting all the pieces together into a running application.

- [ ] **Step 1: Implement app.py**

`src/quartermaster/core/app.py`:
```python
"""Application bootstrap and lifecycle management."""

import asyncio
import signal
from pathlib import Path
from typing import Any

import structlog

from quartermaster.core.config import load_config, QuartermasterConfig
from quartermaster.core.database import Database
from quartermaster.core.events import EventBus
from quartermaster.core.tools import ToolRegistry
from quartermaster.core.usage import UsageTracker
from quartermaster.core.metrics import start_metrics_server
from quartermaster.core.scheduler import Scheduler
from quartermaster.core.approval import ApprovalManager
from quartermaster.llm.local import LocalLLMClient
from quartermaster.llm.anthropic_client import AnthropicClient
from quartermaster.llm.router import LLMRouter
from quartermaster.transport.manager import TransportManager
from quartermaster.transport.telegram import TelegramTransport
from quartermaster.conversation.manager import ConversationManager
from quartermaster.plugin.loader import PluginLoader
from quartermaster.plugin.context import PluginContext

logger = structlog.get_logger()


class QuartermasterApp:
    """Main application — wires everything together."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._config: QuartermasterConfig | None = None
        self._db: Database | None = None
        self._events: EventBus | None = None
        self._tools: ToolRegistry | None = None
        self._usage: UsageTracker | None = None
        self._llm: LLMRouter | None = None
        self._transport: TransportManager | None = None
        self._conversation: ConversationManager | None = None
        self._scheduler: Any = None
        self._approval: Any = None
        self._plugin_loader: PluginLoader | None = None
        self._metrics_runner: Any = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Initialize and start all services."""
        logger.info("quartermaster_starting")

        # Load config
        self._config = load_config(self._config_path)

        # Core services
        self._events = EventBus()
        self._tools = ToolRegistry()

        # Database
        self._db = Database(self._config.database)
        await self._db.connect()

        # Usage tracker
        self._usage = UsageTracker(
            db=self._db,
            monthly_budget=self._config.llm.monthly_budget_usd,
            warn_percent=self._config.llm.budget_warn_percent,
            block_percent=self._config.llm.budget_block_percent,
        )

        # LLM Router
        local_client = LocalLLMClient(
            base_url=self._config.llm.local.base_url,
            preferred_model=self._config.llm.local.preferred_model,
            timeout=self._config.llm.local.timeout_seconds,
        )

        anthropic_client = None
        if self._config.llm.anthropic:
            api_key_path = Path(self._config.llm.anthropic.api_key_file)
            if api_key_path.exists():
                api_key = api_key_path.read_text().strip()
                anthropic_client = AnthropicClient(
                    api_key=api_key,
                    default_model=self._config.llm.anthropic.default_model,
                )

        self._llm = LLMRouter(
            local_client=local_client,
            anthropic_client=anthropic_client,
            usage_tracker=self._usage,
        )

        # Conversation manager
        self._conversation = ConversationManager(
            db=self._db,
            config=self._config.conversation,
        )

        # Scheduler
        self._scheduler = Scheduler(
            db=self._db,
            events=self._events,
            grace_minutes=self._config.scheduler.missed_event_grace_minutes,
        )

        # Transport
        self._transport = TransportManager()
        telegram = TelegramTransport(
            bot_token=self._config.telegram_bot_token,
            allowed_user_ids=self._config.allowed_user_ids,
            events=self._events,
        )
        self._transport.register(telegram)

        # Approval manager
        self._approval = ApprovalManager(
            db=self._db,
            transport=self._transport,
            events=self._events,
            timeout_minutes=self._config.approval.default_timeout_minutes,
        )

        # Metrics
        self._metrics_runner = await start_metrics_server(
            self._config.metrics.port
        )

        # Plugin context — all fields declared in PluginContext
        ctx = PluginContext(
            config=self._config,
            events=self._events,
            tools=self._tools,
            db=self._db,
            llm=self._llm,
            transport=self._transport,
            scheduler=self._scheduler,
            approval=self._approval,
            usage=self._usage,
            conversation=self._conversation,
        )

        # Load plugins
        self._plugin_loader = PluginLoader()
        self._discover_plugins()
        await self._plugin_loader.load_all(ctx)

        # Start transports and scheduler
        await self._transport.start_all()
        await self._scheduler.start()

        logger.info("quartermaster_started")

    def _discover_plugins(self) -> None:
        """Discover and register plugin classes."""
        assert self._plugin_loader is not None
        # Import built-in plugins
        from plugins.chat.plugin import ChatPlugin
        from plugins.commands.plugin import CommandsPlugin
        from plugins.briefing.plugin import BriefingPlugin

        self._plugin_loader.register_class(ChatPlugin)
        self._plugin_loader.register_class(CommandsPlugin)
        self._plugin_loader.register_class(BriefingPlugin)

    async def stop(self) -> None:
        """Gracefully shut down all services."""
        logger.info("quartermaster_stopping")

        if self._scheduler:
            await self._scheduler.stop()
        if self._transport:
            await self._transport.stop_all()
        if self._plugin_loader:
            await self._plugin_loader.teardown_all()
        if self._metrics_runner:
            await self._metrics_runner.cleanup()
        if self._db:
            await self._db.close()

        logger.info("quartermaster_stopped")

    async def run(self) -> None:
        """Start the application and wait for shutdown signal."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown_event.set)

        await self.start()

        # Wait for shutdown signal
        await self._shutdown_event.wait()
        await self.stop()
```

- [ ] **Step 2: Update __main__.py**

`src/quartermaster/__main__.py`:
```python
"""Entry point for python -m quartermaster."""

import asyncio
import sys
from pathlib import Path

import structlog


def configure_logging() -> None:
    """Configure structlog for JSON output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if sys.stdout.isatty()
            else structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )


def main() -> None:
    """Launch the Quartermaster application."""
    configure_logging()
    logger = structlog.get_logger()

    # Find config file
    config_paths = [
        Path("/app/config/settings.yaml"),
        Path("config/settings.yaml"),
        Path("settings.yaml"),
    ]

    config_path = None
    for path in config_paths:
        if path.exists():
            config_path = path
            break

    if config_path is None:
        logger.error("no_config_found", searched=str(config_paths))
        sys.exit(1)

    logger.info("quartermaster_init", config=str(config_path))

    from quartermaster.core.app import QuartermasterApp
    app = QuartermasterApp(config_path)
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify it starts (with config)**

Create a minimal test config and verify the app initializes (it will fail on Oracle/Telegram without real creds, but should get past config loading).

Run: `python -m quartermaster` (should fail with clear error about config or Oracle, not an import error)

- [ ] **Step 4: Commit**

```bash
git add src/quartermaster/core/app.py src/quartermaster/__main__.py
git commit -m "feat: application bootstrap wiring all core services and plugins"
```

---

## Task 22: Docker Build and Smoke Test

**Files:**
- Modify: `Dockerfile` (if needed)
- Modify: `docker-compose.yml` (if needed)

- [ ] **Step 1: Build the Docker image**

Run: `docker build -t quartermaster:dev .`
Expected: Image builds successfully

- [ ] **Step 2: Run the test suite inside the container**

Run: `docker run --rm -v $(pwd)/tests:/app/tests -v $(pwd)/plugins:/app/plugins quartermaster:dev python -m pytest tests/ -v --ignore=tests/core/test_database.py`

Expected: All unit tests pass inside the container (skip DB integration tests)

- [ ] **Step 3: Verify the app entry point**

Run: `docker run --rm quartermaster:dev python -m quartermaster`
Expected: Clean error about missing config file (not an import crash)

- [ ] **Step 4: Run full lint and type check**

```bash
ruff check src/ plugins/
mypy src/ --strict --ignore-missing-imports
```

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "chore: Docker build verified, lint and type check passing"
```

---

## Task 23: Integration Smoke Test

- [ ] **Step 1: Create a real config/settings.yaml** (not committed)

Copy `config/settings.example.yaml` to `config/settings.yaml` and fill in:
- Telegram bot token (from @BotFather)
- Your Telegram user ID
- Oracle connection details for `quartermaster_pdb`
- Anthropic API key file path

- [ ] **Step 2: Set up the Oracle PDB** (if not done in Task 2)

```bash
sqlplus / as sysdba @scripts/setup_oracle_pdb.sql
```

- [ ] **Step 3: Run the bot locally** (not in Docker)

```bash
PYTHONPATH=src:. python -m quartermaster
```

Expected: Bot starts, connects to Oracle, loads plugins, begins Telegram polling.

- [ ] **Step 4: Send a test message in Telegram**

Send "hello" to the bot. Expected: LLM routes to llama-swap, responds conversationally.

- [ ] **Step 5: Test commands**

Send `/help`, `/status`, `/models`, `/spend` in Telegram. Verify responses.

- [ ] **Step 6: Test Docker deployment**

```bash
docker compose up -d
docker compose logs -f
```

Send another message via Telegram. Verify it works from the container.

- [ ] **Step 7: Verify metrics endpoint**

```bash
curl http://localhost:9100/metrics
```

Expected: Prometheus metrics output with `qm_*` metrics.

- [ ] **Step 8: Final commit and push**

```bash
git add -A  # Only if there are fixes from the smoke test
git commit -m "fix: integration test fixes from smoke testing"
git push origin main
```

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | Project scaffold | — |
| 2 | Oracle PDB setup | SQL scripts |
| 3 | Config models | 5 tests |
| 4 | Event bus | 6 tests |
| 5 | Tool Registry | 7 tests |
| 6 | Plugin framework | 6 tests |
| 7 | Database layer | 2 tests |
| 8 | Usage tracker | 5 tests |
| 9 | Scheduler | 5 tests |
| 10 | Approval manager | 3 tests |
| 11 | LLM types + local client | 4 tests |
| 12 | Anthropic client | 2 tests |
| 13 | LLM Router | 5 tests |
| 14 | Transport types + manager | 3 tests |
| 15 | Conversation manager | 2 tests |
| 16 | Telegram transport | import test |
| 17 | Chat plugin | 3 tests |
| 18 | Commands plugin | 3 tests |
| 19 | Briefing plugin skeleton | — |
| 20 | Metrics endpoint | — |
| 21 | App bootstrap | — |
| 22 | Docker build + smoke | integration |
| 23 | Integration smoke test | manual |

**Total: 23 tasks, ~61 unit tests, ~22 commits**

After completion: a working Telegram bot that chats via llama-swap with Anthropic fallback, tracks API costs with budget enforcement, schedules briefings, supports approval flows for confirm-tier tools, responds to commands, has a plugin architecture ready for Phase 2+ extensions, persists conversations in Oracle, and exposes Prometheus metrics.
