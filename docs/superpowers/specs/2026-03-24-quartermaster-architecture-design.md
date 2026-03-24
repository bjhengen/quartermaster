# Quartermaster — Architecture & Design Specification

**Date:** March 24, 2026
**Status:** Approved
**Authors:** Brian Hengen + Claude (design session)
**Phase scope:** Full architecture, Phase 1 MVP detail

---

## 1. Vision & Goals

Quartermaster is a self-hosted personal AI assistant that communicates via Telegram, manages daily workflows, monitors app store performance, assists with social media marketing, and serves as a unified command center for projects and infrastructure.

### Primary Value Streams

| # | Capability | Description |
|---|-----------|-------------|
| 1 | **Morning/Evening Briefings** | 6:30 AM and 6:30 PM daily digests covering email (4 accounts), calendar, curated news, app store activity, infrastructure status. TTS audio option via Fish Speech cloud API. |
| 2 | **App Store Monitoring** | Analytics, revenue, and AdMob tracking for published apps. Review alerts with LLM-drafted responses. |
| 3 | **Social Media Pipeline** | Draft, review, approve, and publish content to Facebook, Instagram, X, and TikTok from Telegram. |
| 4 | **Infrastructure Control** | Conversational interface to host services. Tiered: local LLM for light ops, Claude Code headless sessions for complex multi-step tasks. |
| 5 | **AWS Monitoring** | Cost tracking, server status, container health for cloud infrastructure. |
| 6 | **Communications** | Send formatted reports to stakeholders via email. |
| 7 | **Weekly Roundup** | Sunday noon summary: revenue/analytics, social media metrics, outstanding and completed action items. |

### Non-Goals

- Multi-user support (single user: Brian; Paula receives email reports only)
- Mobile app or web UI (Telegram is the primary interface)
- Running LLM inference (delegates to llama-swap or Claude API)
- Commercial product (public repo, community-friendly, but not a SaaS)

---

## 2. Architecture Overview

### Core Principle: Everything Is a Tool

Every capability — reading email, checking app stats, restarting a service, drafting a social post — is a **tool** registered in a shared Tool Registry. The LLM acts as an **orchestrator**: it reads user intent, selects the right tool(s), and composes the response. The tools do the actual work.

This design means:
- A local plugin and a remote MCP server register tools the same way
- The LLM's function-calling schema and the MCP tool schema are the same JSON
- Adding capabilities = adding tools. The core never changes.
- Cross-plugin communication goes through the Tool Registry, keeping plugins decoupled

### System Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                     Quartermaster Core                        │
│                                                               │
│  ┌───────────────┐  ┌───────────────┐  ┌──────────────────┐ │
│  │  Transport     │  │  LLM Router   │  │  Database        │ │
│  │  Manager       │  │               │  │  (Oracle PDB)    │ │
│  │  - Telegram    │  │  - Local/swap │  │  - Connection    │ │
│  │  - WhatsApp*   │  │  - Sonnet     │  │    pool          │ │
│  │  - Webhook     │  │  - Haiku      │  │  - Migrations    │ │
│  └───────────────┘  │  - CC Headless │  └──────────────────┘ │
│                      └───────────────┘                        │
│  ┌───────────────┐  ┌───────────────┐  ┌──────────────────┐ │
│  │  Tool          │  │  Scheduler    │  │  Approval        │ │
│  │  Registry      │  │  (cron-like)  │  │  Manager         │ │
│  │  - Local tools │  │               │  │  - Draft/review  │ │
│  │  - MCP tools*  │  │               │  │  - Inline KB     │ │
│  └───────────────┘  └───────────────┘  │  - Timeout rules │ │
│                                         └──────────────────┘ │
│  ┌───────────────┐  ┌───────────────┐  ┌──────────────────┐ │
│  │  Event Bus     │  │  Usage        │  │  Plugin          │ │
│  │  (async pub/   │  │  Tracker      │  │  Manager         │ │
│  │   sub)         │  │  - Token cost │  │  - Discovery     │ │
│  │               │  │  - Budget cap │  │  - Lifecycle      │ │
│  └───────────────┘  └───────────────┘  │  - Dependencies  │ │
│                                         └──────────────────┘ │
│  ┌───────────────┐                                            │
│  │  Conversation  │                                           │
│  │  Manager       │                                           │
│  │  - History     │                                           │
│  │  - Context win │                                           │
│  └───────────────┘                                            │
│                                          * = Phase 2+         │
└──────────────────────────────────────────────────────────────┘

Plugins (loaded at startup):
  ├── chat/          # Basic conversation
  ├── commands/      # /status, /models, /help, /spend
  ├── briefing/      # Scheduled briefings
  ├── gmail/         # Gmail integration (Phase 3)
  ├── outlook/       # O365 integration (Phase 3)
  ├── calendar/      # Calendar integration (Phase 3)
  ├── news/          # Curated news aggregation (Phase 3)
  ├── appstore/      # App Store Connect (Phase 4)
  ├── playstore/     # Google Play Developer (Phase 4)
  ├── admob/         # AdMob revenue (Phase 4)
  ├── facebook/      # Facebook Pages (Phase 5)
  ├── instagram/     # Instagram (Phase 5)
  ├── x_twitter/     # X/Twitter (Phase 5)
  ├── tiktok/        # TikTok (Phase 5)
  ├── infra/         # Infrastructure control (Phase 6)
  ├── aws/           # AWS monitoring (Phase 6)
  └── whatsapp/      # WhatsApp transport (Phase 7)
```

---

## 3. Core Services

### 3.1 Transport Manager

Abstracts message delivery so plugins never know or care which transport delivered a message.

- **Phase 1:** Telegram (long-polling via `python-telegram-bot`)
- **Phase 6:** Webhook endpoint for cron scripts to push notifications
- **Phase 7:** WhatsApp via WAHA Docker container
- Normalizes all inbound messages into a `Message` object with source, user, text, chat_id, and metadata
- Handles "typing" indicators while waiting for LLM responses
- Delivers voice messages (TTS briefings) as Telegram audio

### 3.2 LLM Router

Smart routing that respects GPU sharing with other llama-swap consumers.

**Routing algorithm:**
1. Check `GET http://localhost:8200/running`
2. If idle or preferred model loaded → route to local (qwen3.5-27b via llama-swap)
3. If another model loaded → attempt local with a longer timeout (model swap takes 5-10s)
4. If llama-swap is unreachable or returns an error → fall back to Claude API (Sonnet for most tasks, Haiku for simple classification)
5. If local call times out (configurable, default 60s) → fall back to Claude API
6. For complex infrastructure tasks → spawn Claude Code headless session
7. All calls wrapped with Usage Tracker for cost logging

**Note:** The primary routing signal is llama-swap's own `/running` endpoint, not GPU utilization polling. The `nvidia-smi` approach was considered but rejected — it's a point-in-time snapshot that races with GPU workload fluctuations. llama-swap knows its own state and is the authoritative signal for whether local inference is available.

**Budget safeguard:** If Cloud API spend exceeds 50% of the monthly budget before mid-month, the Usage Tracker emits a warning via Telegram. At 80%, non-essential cloud calls (e.g., chat) are queued to wait for local LLM availability rather than auto-falling-back. At 100%, only `confirm`-tier-approved cloud calls are allowed.

**Connectivity failure handling:**
- llama-swap unreachable → fall through to Claude API, log warning
- Claude API unreachable → respond to user with "I'm having trouble reaching my backends — try again in a few minutes", log error
- Both unreachable → same user message, emit `plugin.health_changed` event

**Budget:** $50/month Anthropic API cap. Bot tracks cumulative spend and can report via `/spend` command.

**Tool calling:** The router presents available tools from the Tool Registry to whichever LLM backend handles the request. Tool schemas are OpenAI function-calling format (compatible with both llama-swap and Anthropic API).

### 3.3 Database (Oracle 26ai PDB)

- **PDB:** `QUARTERMASTER_PDB` within the existing CDB on slmbeast
- **Schema:** `QM` (application user with least-privilege grants)
- Async connection pool via `python-oracledb` (Oracle-maintained driver)
- Each plugin manages its own tables with a migration system (schema version tracked in `plugin_state`)
- JSON columns for flexible data without sacrificing query performance
- Partitioning available for high-volume tables (usage_log, turns) as they grow

### 3.4 Tool Registry

The central nervous system. Every capability registers here with:

- **Name** — namespaced (e.g., `email.unread_summary`, `infra.service_restart`)
- **Description** — used by the LLM to understand when to call the tool
- **Parameter schema** — JSON Schema, doubles as LLM function-calling schema and MCP tool schema
- **Handler** — async function that executes the tool
- **Approval tier** — `autonomous`, `confirm`, or `notify`
- **Metadata** — which transports can trigger it, rate limits, etc.

When MCP lands in Phase 2:
- Local plugin tools and remote MCP server tools coexist in the same registry
- The briefing plugin calls `email.unread_summary` without knowing if it's local or remote
- The Quartermaster MCP server exposes registered tools to external clients (e.g., Claude Code)

### 3.5 Event Bus

Async publish/subscribe for loose coupling between components.

Key events:
- `message.received` — new inbound message from any transport
- `message.contextualized` — message enriched with conversation history
- `message.completed` — full request/response cycle finished
- `schedule.*` — scheduler timer events
- `plugin.health_changed` — a plugin's health status changed
- `approval.resolved` — an approval was accepted/rejected/expired

### 3.6 Scheduler

Cron-like async scheduler for timed events.

| Schedule | Event | Consumer |
|----------|-------|----------|
| `30 6 * * *` | `schedule.briefing.morning` | Briefing plugin |
| `30 18 * * *` | `schedule.briefing.evening` | Briefing plugin |
| `0 12 * * 0` | `schedule.briefing.weekly` | Briefing plugin |
| `*/5 * * * *` | `schedule.health_check` | Core (plugin health) |

Schedules are stored in Oracle and configurable via `settings.yaml`. Plugins can register additional schedules at startup.

**Missed event policy:** On startup, the scheduler checks `next_run_at` for all enabled schedules. If a schedule was missed by less than a configurable grace window (default: 15 minutes), it fires immediately. If missed by more than the grace window, it skips to the next scheduled time. This prevents a 23-hour-late briefing after a long outage, while catching brief restarts.

**`next_run_at` management:** Updated by the scheduler after each execution (success or failure) and on startup during the missed-event check.

**Task failure handling:** If a scheduled task fails, the scheduler logs the error, marks `last_status = 'failed'` in Oracle, and emits a `plugin.health_changed` event. It does not retry — the next scheduled occurrence runs normally. Persistent failures (3+ consecutive) trigger a Telegram alert to Brian.

### 3.7 Approval Manager

Three-tier approval system for tool execution:

| Tier | Behavior | Examples |
|------|----------|---------|
| `autonomous` | Execute immediately | Read email, check calendar, status queries, Telegram messages to Brian, scheduled briefings |
| `confirm` | Draft → Telegram inline keyboard → wait for approve/reject | Send email, post to social media, respond to reviews, restart services |
| `notify` | Execute immediately, notify Brian it happened | Automated alerts, health status changes, budget threshold warnings |

Each tool declares its default tier. Tiers can be overridden in `settings.yaml` (promote to autonomous once trusted, or demote to confirm for tighter control).

Pending approvals stored in Oracle with configurable timeout (default: 1 hour, then expire).

**Expiry behavior:**
- When an approval expires, the bot sends a Telegram notification: "Action expired: [brief description]. Use /retry to re-request."
- If a user taps an inline keyboard button on an expired approval, the bot responds with "This action has expired" (not a silent failure or crash)
- Expired approvals are marked `expired` in Oracle with `resolved_by = 'timeout'`

### 3.8 Usage Tracker

Wraps every LLM API call to log:
- Provider, model, token counts (in/out), estimated cost
- Purpose (chat, briefing, tool-selection, content-generation)
- Plugin that triggered the call

Exposes:
- `/spend` command — current month spend vs budget
- Prometheus metrics — for Grafana dashboards
- Budget enforcement — warn at 80%, block non-essential calls at 100%

### 3.9 Plugin Manager

Discovers, validates, and lifecycle-manages plugins.

- **Discovery** — scans the plugins directory for packages with a `plugin.py` containing a `QuartermasterPlugin` subclass
- **Dependency resolution** — plugins declare dependencies; manager loads them in correct order
- **Lifecycle** — `setup()` → running → `teardown()` on shutdown
- **Health monitoring** — periodic `health()` calls, aggregated for `/status` command
- **Isolation** — a crashing plugin is caught, marked as `down`, and doesn't take out the core or other plugins

### 3.10 Conversation Manager

Manages conversation history and context window assembly for LLM calls.

- **History storage** — all turns (user, assistant, tool calls, tool results) persisted to Oracle `qm.turns` table
- **Context window strategy** — sliding window of the most recent N turns (configurable, default 20). Measured by token budget (configurable, default 8,000 tokens) rather than strict turn count, since tool calls and results can vary dramatically in size. When the window exceeds the budget, oldest turns are dropped first.
- **Tool call serialization** — tool calls and their results are stored as JSON in the `turns` table and reconstructed into the LLM's expected format when building the context window
- **Conversation boundaries** — a new conversation is created when: (a) the user explicitly resets (`/new`), or (b) the gap between messages exceeds a configurable idle timeout (default: 4 hours)
- **Responsibility boundary** — the Conversation Manager owns history loading and context assembly. The LLM Router owns adding tool schemas and system prompts. The Conversation Manager emits `message.contextualized`; the LLM Router listens to that event.
- **Plugin access** — exposed via `PluginContext` as `ctx.conversation` for plugins that need to read or annotate conversation history (e.g., the briefing plugin logging its output as a conversation turn)

---

## 4. Plugin Interface

### Base Class

```python
class QuartermasterPlugin:
    """Base class for all Quartermaster plugins."""

    # Plugin metadata
    name: str = ""                    # e.g., "gmail"
    version: str = "0.1.0"
    dependencies: list[str] = []     # e.g., ["core.scheduler", "core.approval"]

    async def setup(self, ctx: PluginContext):
        """Called once at startup. Register tools, subscribe to events,
        schedule tasks. ctx provides access to all core services."""

    async def teardown(self):
        """Called on shutdown. Clean up connections, flush state."""

    async def health(self) -> HealthStatus:
        """Called periodically and by /status command.
        Return ok, degraded, or down with optional message."""
```

The Plugin Manager resolves `dependencies` at startup, loading plugins in dependency order. If a required dependency is missing or failed to load, the dependent plugin is skipped with a `down` health status and a log warning.

### Plugin Context

```python
class PluginContext:
    db: DatabasePool               # Oracle connection pool
    llm: LLMRouter                 # Request LLM completions
    transport: TransportManager    # Send messages
    tools: ToolRegistry            # Register and call tools
    events: EventBus               # Subscribe and emit events
    scheduler: Scheduler           # Schedule recurring tasks
    approval: ApprovalManager      # Draft/approve/execute flows
    usage: UsageTracker            # Log API costs
    conversation: ConversationManager  # Read/annotate history
    config: PluginConfig           # This plugin's config section
```

### Tool Registration

Tool parameter schemas use standard JSON Schema format, which is directly compatible with
both the OpenAI function-calling format (used by llama-swap) and the Anthropic tool-use format.
No translation layer is needed.

```python
async def setup(self, ctx: PluginContext):
    ctx.tools.register(
        name="email.unread_summary",
        description="Get summary of unread emails across all accounts",
        parameters={
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "description": "Filter to specific account",
                },
                "priority": {
                    "type": "string",
                    "enum": ["all", "high", "low"],
                    "default": "all",
                },
            },
            "required": [],
        },
        handler=self.get_unread_summary,
        approval_tier="autonomous",
    )
```

---

## 5. Message Flow

### User-Initiated (Telegram)

```
1. TRANSPORT: Telegram long-poll receives message
   → Normalize to Message object
   → Emit event: message.received

2. CONVERSATION MANAGER: Load recent history from Oracle
   → Attach context window
   → Emit event: message.contextualized

3. LLM ROUTER: Gather available tools from Tool Registry
   → Check llama-swap status, select backend
   → Send to LLM: conversation history + tool schemas + system prompt
   → LLM responds (conversational text and/or tool calls)

4. TOOL EXECUTION LOOP: If tool calls present
   → For each tool call in the LLM response:
     - Check approval tier:
       - autonomous → execute immediately
       - confirm → pause loop, send draft to Telegram inline keyboard,
         wait for approval (other autonomous tools in the same batch
         proceed; the loop resumes when approval resolves)
       - notify → execute, send notification
     - Collect results from all executed tools
   → Return all tool results to LLM
   → LLM may respond with MORE tool calls (chaining) or final text
   → Loop continues until:
     a) LLM responds with text only (no tool calls) → done
     b) Max iterations reached (configurable, default 5) → respond
        with partial results + "I hit my tool limit for this request"
     c) A `confirm`-tier tool is rejected → LLM informed of rejection,
        composes response acknowledging cancellation
   → Multi-step chaining example: LLM calls calendar.today(), sees a
     conflict, then calls email.draft() to notify the other party

5. RESPONSE: LLM composes natural language response
   → Usage Tracker logs tokens + cost
   → Transport sends via Telegram
   → Conversation Manager saves full exchange to Oracle
     (including all intermediate tool calls and results)

6. EVENT BUS: Emit message.completed
```

### Scheduled (Briefing)

```
1. SCHEDULER: Timer fires (6:30 AM)
   → Emit event: schedule.briefing.morning

2. BRIEFING PLUGIN: Calls tools via Tool Registry
   → Only calls tools that are currently registered (graceful degradation):
     Phase 1: system.status only (basic system health)
     Phase 3+: calendar.today(), email.unread_summary() (x4 accounts)
     Phase 3+: news.curated_summary()
     Phase 4+: appstore.overnight_activity()
     Phase 6+: infra.status()

3. COMPOSE: Assemble briefing from tool results
   → Apply template formatting
   → Sections with no data source simply omitted (not shown as errors)

4. TTS (optional): Send text to Fish Speech cloud API
   → Receive audio stream/file
   → If Fish Speech API unavailable: deliver as text-only (TTS is
     enhancement, not requirement — text briefing always delivered)

5. DELIVER: Send via Transport Manager
   → Telegram text message + voice message
```

---

## 6. Deployment Architecture

### Docker Container

```yaml
# docker-compose.yml
services:
  quartermaster:
    build: .
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./config:/app/config
      - ./credentials:/app/credentials
      - ./logs:/app/logs
    environment:
      - QM_ENV=production
      - ORACLE_DSN=localhost:1521/quartermaster_pdb
```

**Key decisions:**
- **Host networking** — simplest path to reach llama-swap (8200), Oracle (1521), and other host services
- **Mounted volumes** — config, credentials, and logs on host filesystem. Credentials never baked into image.
- **Base image:** `python:3.13-slim`
- **Infrastructure control (Phase 6):** SSH key for localhost access with restricted command set

### Observability

Prometheus `/metrics` endpoint (port 9100) exposing:
- LLM calls: count, latency, tokens, cost, local vs cloud split
- Tool invocations: count per tool, success/failure rate, latency
- Plugin health status
- Message volume by transport
- Scheduler execution: on-time, late, failed
- API budget consumed vs remaining
- Queue depth for pending LLM requests

Scraped by existing Prometheus instance on slmbeast, visualized in Grafana.

### Resource Budget

- **Idle:** ~30-50 MB RAM, zero CPU (long-polling wait)
- **Active:** Brief spikes during LLM calls (~100 MB)
- **No GPU usage** — delegates to llama-swap or Claude API
- **Disk:** Oracle PDB + logs, minimal

---

## 7. Oracle PDB Schema

**PDB:** `QUARTERMASTER_PDB`
**Schema user:** `QM`

### Phase 1 Tables

```sql
-- Conversation history
CREATE TABLE qm.conversations (
    conversation_id   RAW(16) DEFAULT sys_guid() PRIMARY KEY,
    transport         VARCHAR2(20) NOT NULL,
    external_chat_id  VARCHAR2(100) NOT NULL,
    created_at        TIMESTAMP DEFAULT systimestamp,
    last_active_at    TIMESTAMP DEFAULT systimestamp,
    metadata          JSON
);

-- Individual turns in a conversation
CREATE TABLE qm.turns (
    turn_id           RAW(16) DEFAULT sys_guid() PRIMARY KEY,
    conversation_id   RAW(16) REFERENCES qm.conversations,
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
```

### Future Phase Tables

| Phase | Tables |
|-------|--------|
| 3 | `qm.email_accounts`, `qm.email_cache`, `qm.calendar_events` |
| 4 | `qm.app_metrics`, `qm.app_reviews`, `qm.revenue_daily` |
| 5 | `qm.social_posts`, `qm.social_metrics`, `qm.content_calendar` |
| 6 | `qm.infra_snapshots`, `qm.aws_costs`, `qm.alert_history` |

Each plugin manages its own tables via a migration system — schema version tracked in `plugin_state`, pending DDL executed on plugin startup.

---

## 8. Security Model

- **Telegram allowlist** — only Brian's Telegram user ID can interact. All other messages silently dropped.
- **Credential storage** — OAuth tokens and API keys in mounted `credentials/` volume (file permissions 600). Never in Oracle, never in the Docker image, never in the repo.
- **Oracle access** — dedicated `QM` schema user with least-privilege grants on its own tables only.
- **Approval as security** — the `confirm` tier prevents LLM hallucinations from triggering external actions without human approval.
- **Config separation** — `settings.yaml` references credential files by path. `settings.example.yaml` ships in the repo with placeholders.
- **Infrastructure control** — SSH key for localhost with restricted command set via `authorized_keys` `command=` restrictions.
- **Public repo safety** — `.gitignore` excludes `credentials/`, `config/settings.yaml`, `logs/`, and any `*.pem`/`*.key` files.

---

## 9. Error Handling & Resilience

### Startup Behavior

- **Oracle unavailable at startup** — the application refuses to start and logs a clear error. Oracle is required for conversation history, plugin state, and scheduling. No degraded-startup mode.
- **Telegram API unreachable at startup** — the application starts but the Telegram transport reports `down` health. The scheduler and webhook endpoint still function. Telegram reconnection is attempted on a backoff schedule.
- **Plugin setup failure** — the failing plugin is marked `down` with logged error. All other plugins continue loading. If a downstream plugin depends on the failed one, it is also skipped.

### Runtime Error Handling

- **Plugin crash during event handling** — caught by the Event Bus, logged with full traceback, plugin marked `degraded`. Does not affect other plugins or the core event loop.
- **LLM call failure** — handled by the routing fallback chain (see Section 3.2). If all backends fail, the user receives a friendly error message via Telegram.
- **Tool execution failure** — the error is returned to the LLM as a tool result (e.g., `{"error": "Gmail API returned 401"}`). The LLM can decide to retry, use a different approach, or inform the user.
- **Oracle connection lost during operation** — the connection pool handles transient disconnects with automatic retry. If Oracle is down for an extended period, the bot continues to handle simple conversational messages (without history) and alerts Brian via Telegram.

### Event Bus Delivery Guarantees

- **At-most-once delivery** — events are dispatched to all registered handlers. If no handler is registered for an event, it is silently dropped (this is normal — not all events have consumers at all times).
- Events are not persisted or queued. If a handler is temporarily unavailable (plugin down), the event is lost. This is acceptable because all critical state is in Oracle, and missed events (e.g., a missed `message.completed`) do not cause data loss.

---

## 10. Testing Strategy

- **Type checking:** `mypy --strict` on all source
- **Linting:** `ruff` with strict config
- **Core services:** Unit tests with mocked dependencies
- **Plugins:** Each tested in isolation against a mock `PluginContext`
- **LLM routing:** Mock llama-swap `/running` responses to test all routing paths
- **Database:** Integration tests against a real Oracle test PDB (`QUARTERMASTER_TEST_PDB`)
- **End-to-end:** Boot full app with test config, send mock Telegram messages, validate flow
- **CI:** All of the above on every commit

---

## 11. Technology Stack

### Core Dependencies

```
python-telegram-bot>=22.0    # Telegram bot framework (async)
httpx                         # Async HTTP client
python-oracledb               # Oracle database driver (Oracle-maintained)
pydantic>=2.0                 # Data validation and settings
pyyaml                        # Configuration
structlog                     # Structured JSON logging
prometheus-client             # Metrics endpoint
anthropic                     # Claude API client
```

### Phase 3+ Dependencies (not needed for MVP)

```
google-api-python-client      # Gmail, Calendar, Play Store, AdMob
google-auth-oauthlib          # Google OAuth
msgraph-sdk                   # Microsoft Graph (O365 email, calendar)
pyjwt                         # App Store Connect JWT auth
cryptography                  # App Store Connect key handling
```

### Dev Dependencies

```
pytest                        # Test framework
pytest-asyncio                # Async test support
mypy                          # Static type checking
ruff                          # Linting and formatting
```

### Production Quality Baseline

- Strict type hints everywhere + `mypy --strict`
- Pydantic models for all data structures (config, messages, tool schemas, API responses)
- Structured logging (`structlog`) — JSON logs, correlation IDs per request
- Comprehensive error handling — plugin crashes isolated from core
- Test suite from day one

---

## 12. Email Integration Design (Phase 3)

Provider-agnostic email layer supporting multiple accounts and providers.

| Account | Provider | API |
|---------|----------|-----|
| Personal Gmail | Google | Gmail API |
| FR generic Gmail | Google | Gmail API |
| FR Brian email | O365 (GoDaddy) | Microsoft Graph API |
| FR Product Support | O365 (GoDaddy) | Microsoft Graph API |

Future: self-hosted email on AWS (IMAP/SMTP).

Each account is a separate config entry with its own OAuth tokens. The email plugins register common tools (`email.unread_summary`, `email.read`, `email.send`, `email.draft`) that accept an `account` parameter.

Reports to Paula (stakeholder, non-interactive) are sent via the FR Gmail account.

---

## 13. Scheduled Events

| Time | Event | Content |
|------|-------|---------|
| 6:30 AM daily | Morning briefing | Email summaries (4 accounts), calendar, curated news, app store overnight activity, infrastructure status |
| 6:30 PM daily | Evening summary | App performance, social media engagement, alerts/issues from the day |
| 12:00 PM Sunday | Weekly roundup | Revenue/analytics across apps + AdMob, social media metrics, outstanding & completed action items |

TTS delivery via Fish Speech cloud API — briefings available as Telegram voice messages for listening on the go.

---

## 14. Social Media Strategy (Phase 5)

Platforms in priority order:

1. **Facebook** — existing FR account, Meta Graph API
2. **Instagram** — existing FR account, Meta Graph API (shared with Facebook)
3. **X/Twitter** — new account, X API v2 (free tier: 1,500 posts/month)
4. **TikTok** — new account, TikTok API

All follow the draft → approve → publish pattern via the Approval Manager.

---

## 15. Infrastructure Control Design (Phase 6)

### Tiered Execution Model

| Tier | LLM Backend | Capabilities | Examples |
|------|------------|--------------|---------|
| Read-only | Local (qwen3.5-27b) | Status checks, log reading, metrics | "What's using the GPU?", "Show Docker status" |
| Light control | Local (qwen3.5-27b) | Service restarts, cache clears | "Restart ComfyUI", "Reload llama-swap" |
| Complex operations | Claude Code headless | Multi-step reasoning, deployments, debugging | "Pull latest and redeploy wine.dine backend" |

The bot spawns Claude Code headless sessions for complex tasks, acting as the conversational front-end while CC does the infrastructure reasoning. Results are reported back via Telegram.

### Monitoring Scope

- **slmbeast:** llama-swap, ComfyUI, Open WebUI, Docker containers, GPU (VRAM/temp), disk space, backup age
- **AWS:** EC2 status, container health, cost tracking
- Webhook endpoint for existing cron scripts to push notifications to the bot

---

## 16. Phased Build Plan

| Phase | Name | Scope | Depends On |
|-------|------|-------|------------|
| 1 | **Core Bot MVP** | Telegram bot, LLM routing, conversation history, basic commands, plugin framework, Oracle PDB, Docker container, Prometheus metrics | — |
| 2 | **MCP Infrastructure** | Quartermaster as MCP client + server, foundation for all integrations | Phase 1 |
| 3 | **Email + Calendar + News** | Gmail (2 accounts), O365 (2 accounts), Google Calendar, O365 Calendar, curated news aggregation, morning/evening briefings with real data, TTS | Phase 2 |
| 4 | **App Store + Revenue** | App Store Connect, Google Play Developer, AdMob, review alerts, daily digest, trend tracking | Phase 2 |
| 5 | **Social Media** | Facebook, Instagram, X, TikTok, content calendar, draft/approve/publish, engagement monitoring | Phase 2 |
| 6 | **Infrastructure Control** | Host monitoring, AWS monitoring, tiered execution (local LLM + CC headless), webhook endpoint | Phase 2 |
| 7 | **WhatsApp** | WAHA Docker container, second transport, shared or separate conversation contexts | Phase 1 (transport only — no MCP tools needed, just a new transport implementation against the Transport Manager interface) |

Note: Phases 3-6 can be built in any order after Phase 2, based on what's most useful day-to-day.

---

## 17. Project Structure

```
quartermaster/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── pyproject.toml
├── CLAUDE.md
├── README.md
│
├── src/
│   └── quartermaster/
│       ├── __init__.py
│       ├── __main__.py
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── app.py              # Application bootstrap, lifecycle
│       │   ├── config.py           # Settings loader (YAML → Pydantic)
│       │   ├── database.py         # Oracle connection pool
│       │   ├── events.py           # Async event bus
│       │   ├── tools.py            # Tool Registry
│       │   ├── scheduler.py        # Cron-like scheduler
│       │   ├── approval.py         # Draft → approve → execute
│       │   ├── usage.py            # API cost tracking + budget
│       │   └── metrics.py          # Prometheus endpoint
│       │
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── router.py           # Smart routing logic
│       │   ├── local.py            # llama-swap client
│       │   ├── anthropic.py        # Claude API client
│       │   ├── headless.py         # Claude Code headless launcher
│       │   └── models.py           # Request/response types
│       │
│       ├── transport/
│       │   ├── __init__.py
│       │   ├── manager.py          # Transport abstraction
│       │   ├── telegram.py         # Telegram handler
│       │   ├── webhook.py          # Inbound webhook server
│       │   └── types.py            # Message, User, etc.
│       │
│       ├── conversation/
│       │   ├── __init__.py
│       │   ├── manager.py          # History, context window
│       │   └── models.py           # Conversation, Turn types
│       │
│       └── plugin/
│           ├── __init__.py
│           ├── base.py             # QuartermasterPlugin base class
│           ├── context.py          # PluginContext
│           ├── loader.py           # Discovery, dependency resolution
│           └── health.py           # Health check types
│
├── plugins/
│   ├── chat/                       # Phase 1
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   └── prompts.py
│   │
│   ├── commands/                   # Phase 1
│   │   ├── __init__.py
│   │   └── plugin.py
│   │
│   ├── briefing/                   # Phase 1 skeleton
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   └── templates.py
│   │
│   ├── gmail/                      # Phase 3
│   ├── outlook/                    # Phase 3
│   ├── calendar/                   # Phase 3
│   ├── news/                       # Phase 3
│   ├── appstore/                   # Phase 4
│   ├── playstore/                  # Phase 4
│   ├── admob/                      # Phase 4
│   ├── facebook/                   # Phase 5
│   ├── instagram/                  # Phase 5
│   ├── x_twitter/                  # Phase 5
│   ├── tiktok/                     # Phase 5
│   ├── infra/                      # Phase 6
│   ├── aws/                        # Phase 6
│   └── whatsapp/                   # Phase 7
│
├── config/
│   ├── settings.yaml               # Main config (mounted, gitignored)
│   └── settings.example.yaml       # Template for public repo
│
├── credentials/                    # OAuth tokens, API keys (gitignored)
│   └── .gitkeep
│
├── logs/                           # Structured JSON logs (gitignored)
│   └── .gitkeep
│
├── tests/
│   ├── conftest.py
│   ├── core/
│   ├── llm/
│   ├── transport/
│   └── plugins/
│
├── scripts/
│   ├── setup_oracle_pdb.sql
│   └── dev.sh
│
└── docs/
    └── superpowers/
        └── specs/
```

---

## 18. Bot Persona

Default system prompt (configurable via `settings.yaml`):

> You are Quartermaster, a personal AI assistant. You are concise, direct, and action-oriented. When you can answer directly, do so. When a task requires a tool, call it without preamble. For actions with external consequences, always present a draft for approval before executing. Keep status reports scannable — use bullet points, not paragraphs. Match the user's tone — brief messages get brief replies.

---

## 19. Open Items for Future Phases

1. **Qwen3.5 tool calling benchmark** — test reliability of function calling via llama-swap before building the tool-calling pipeline. Also test Nemotron models.
2. **Multi-model routing** — start single-model, evaluate whether different tasks benefit from different models after real usage data.
3. **News curation sources and approach** — determine RSS feeds, web search strategy, and summarization pipeline for daily news briefing.
4. **MCP server catalog** — evaluate existing MCP servers for Gmail, Calendar, social media before building custom ones.
5. **Blog series** — narrative format with code excerpts, documenting the build as it progresses.
6. **WhatsApp dedicated SIM** — needed for WAHA to avoid ban risk on personal number.

---

*Designed in a collaborative session, March 24, 2026.*
