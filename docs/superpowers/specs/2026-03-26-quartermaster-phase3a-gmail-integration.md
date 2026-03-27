# Quartermaster Phase 3a — Gmail Integration Design

**Date:** March 26, 2026
**Status:** Approved
**Authors:** Brian Hengen + Claude (design session)
**Phase scope:** Gmail email integration — 2 accounts, full read/write with approval-gated sending

---

## 1. Overview

Phase 3a adds Gmail integration to Quartermaster as the first email provider. Two Gmail accounts (personal and Friendly Robots) are wired into the unified email plugin. The LLM can search, read, draft, and send email — with send and reply gated through the Approval Manager so nothing leaves an inbox without Brian's explicit OK on Telegram.

### Goals

- Provider-agnostic email abstraction that Gmail implements first, O365 slots into later
- Two Gmail accounts operational from day one (forces multi-account design to be correct)
- Read operations are autonomous; send/reply require Telegram approval
- Email tools available in the Tool Registry for briefing plugin and natural language use
- Reuse ledgr's Gmail OAuth patterns and API client code

### Non-Goals

- O365/Microsoft Graph integration (Phase 3b)
- Calendar integration (Phase 3c/3d)
- News aggregation (Phase 3e)
- Enhanced briefings with email data (Phase 3f — briefing plugin template update only)
- Reports to Paula (later workflow once more data sources exist)
- TTS / voice message delivery (Phase 3g)

---

## 2. Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Plugin + provider pattern | Email plugin delegates to provider backends | Clean separation: plugin owns tools, providers own API. Adding O365 = one new file. |
| Provider location | `src/quartermaster/email/` package | Core capability, independently testable, follows QM pattern (core code in src/) |
| Plugin location | `plugins/email/` | Thin orchestration, follows existing plugin pattern |
| Gmail API client | `google-api-python-client` | Same as ledgr, proven, official Google SDK |
| Async wrapping | `asyncio.to_thread()` around sync Google API calls | Google SDK is synchronous; wrapping prevents event loop blocking |
| Credential storage | JSON files in `credentials/` (gitignored) | Consistent with existing Anthropic key and MCP token pattern |
| OAuth setup | Standalone script, run once per account | Reuse ledgr's pattern; outputs credential file directly |
| Token refresh | Provider writes back to credential file | Handles Google's occasional refresh token rotation |
| Send approval | Confirm tier via Approval Manager | Safety gate — nothing sends without Telegram approval |
| Multi-account routing | `account` parameter on all tools | Explicit routing; `unread_summary` aggregates when account omitted |

---

## 3. Configuration

### settings.yaml Structure

```yaml
quartermaster:
  email:
    accounts:
      personal:
        provider: gmail
        credential_file: "credentials/gmail_personal.json"
        label: "Personal Gmail"
      friendly-robots:
        provider: gmail
        credential_file: "credentials/gmail_fr.json"
        label: "Friendly Robots"
```

Each account is a named entry with:
- `provider` — which provider class to instantiate (`gmail`, future: `outlook`)
- `credential_file` — path to JSON file with OAuth credentials
- `label` — human-readable name for display in `/status` and briefings

### Pydantic Config Model

`EmailAccountConfig` added to `core/config.py`:

```python
class EmailAccountConfig(BaseModel):
    provider: str  # "gmail", future: "outlook"
    credential_file: str
    label: str

class EmailConfig(BaseModel):
    accounts: dict[str, EmailAccountConfig] = {}
```

Added to `QuartermasterConfig` as `email: EmailConfig`.

### Credential File Format

```json
{
  "client_id": "...",
  "client_secret": "...",
  "refresh_token": "..."
}
```

Written once by the OAuth setup script. Read at startup by the provider. Updated in-place if refresh token rotates.

---

## 4. Provider Package

New package at `src/quartermaster/email/`:

```
src/quartermaster/email/
├── __init__.py
├── models.py       # EmailSummary, EmailMessage, EmailAccount
├── provider.py     # EmailProvider protocol
└── gmail.py        # GmailProvider implementation
```

### Data Models (`models.py`)

```python
class EmailSummary(BaseModel):
    id: str
    subject: str
    sender: str
    date: datetime | None
    snippet: str
    is_read: bool
    labels: list[str] = []

class EmailMessage(BaseModel):
    id: str
    thread_id: str
    subject: str
    sender: str
    to: list[str]
    cc: list[str] = []
    date: datetime | None
    body: str  # plain text
    snippet: str
    is_read: bool
    labels: list[str] = []
    attachments: list[AttachmentInfo] = []

class AttachmentInfo(BaseModel):
    filename: str
    mime_type: str
    size: int  # bytes
```

### Provider Protocol (`provider.py`)

```python
class EmailProvider(Protocol):
    @property
    def account_name(self) -> str: ...

    @property
    def label(self) -> str: ...

    async def connect(self) -> None: ...

    async def get_unread_summary(self, max_results: int = 20) -> list[EmailSummary]: ...

    async def search(self, query: str, max_results: int = 10) -> list[EmailSummary]: ...

    async def read(self, message_id: str) -> EmailMessage: ...

    async def send(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> dict[str, str]: ...

    async def draft(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> dict[str, str]: ...

    async def reply(self, message_id: str, body: str) -> dict[str, str]: ...

    async def health_check(self) -> bool: ...
```

All methods are async. The protocol defines the contract that any email provider must implement. Return types use the shared models above. `connect()` is called once at startup to authenticate and build the API client. `health_check()` verifies the connection is alive (e.g., a lightweight API call).

### Gmail Provider (`gmail.py`)

Adapted from ledgr's `api/services/gmail.py`:

- `connect()` — loads credentials from JSON file, builds Google API service via `asyncio.to_thread()`
- All API calls wrapped in `asyncio.to_thread()` since the Google SDK is synchronous
- `get_unread_summary()` — queries `is:unread` via Gmail API, returns `list[EmailSummary]`
- `search()` — passes query string directly to Gmail search (supports Gmail search syntax)
- `read()` — fetches full message, parses headers, extracts plain text body
- `send()` — builds MIME message, calls `messages.send()`. Returns `{"message_id": "...", "status": "sent"}`
- `draft()` — builds MIME message, calls `drafts.create()`. Returns `{"draft_id": "...", "status": "drafted"}`
- `reply()` — fetches original message for thread_id and subject, builds reply with `In-Reply-To` and `References` headers, calls `messages.send()`
- Token refresh: if `Credentials.refresh()` yields a new refresh token, writes it back to the credential file

**Scopes required:** `gmail.modify`, `gmail.compose`

---

## 5. Email Plugin

### Plugin Structure

```
plugins/email/
├── __init__.py
└── plugin.py       # EmailPlugin class
```

### Tool Registration

At startup, the plugin:
1. Reads `config.email.accounts`
2. Instantiates the correct provider per account (`gmail` → `GmailProvider`)
3. Calls `provider.connect()` for each account
4. Registers tools into the Tool Registry

| Tool | Approval Tier | Parameters | Description |
|------|--------------|------------|-------------|
| `email.unread_summary` | autonomous | `account` (optional), `max_results` (default 20) | Unread email summaries. Omit account for all accounts aggregated. |
| `email.search` | autonomous | `account`, `query`, `max_results` (default 10) | Search emails using provider-native query syntax |
| `email.read` | autonomous | `account`, `message_id` | Read full email content |
| `email.draft` | autonomous | `account`, `to`, `subject`, `body`, `cc` (optional) | Create a draft email |
| `email.send` | **confirm** | `account`, `to`, `subject`, `body`, `cc` (optional) | Send an email — requires Telegram approval |
| `email.reply` | **confirm** | `account`, `message_id`, `body` | Reply to an email — requires Telegram approval |

### Account Routing

Each tool handler receives the `account` parameter (string matching a key in `config.email.accounts`) and dispatches to the correct provider instance. For `email.unread_summary`, if `account` is omitted or empty, the handler iterates all providers, aggregates results, and labels each summary with the account name.

Invalid account names return `{"error": "Unknown email account: 'foo'"}`.

### Lifecycle

- **setup():** instantiate providers, connect, register tools
- **teardown():** no persistent connections to close (Google API uses HTTP, no persistent socket)
- **health():** calls `provider.health_check()` for each account, reports aggregate status

---

## 6. OAuth Setup Script

`scripts/gmail_oauth_setup.py` — adapted from ledgr's version:

```
python scripts/gmail_oauth_setup.py \
  --credentials path/to/google_oauth_client.json \
  --account-name personal
```

1. Reads the Google Cloud OAuth client JSON (downloaded from Cloud Console)
2. Runs `InstalledAppFlow.run_local_server()` with scopes `gmail.modify` + `gmail.compose`
3. Writes `credentials/gmail_personal.json` with `client_id`, `client_secret`, `refresh_token`
4. Prints confirmation

The same Google Cloud project used for ledgr can be reused — just add the broader scopes in the Cloud Console's OAuth consent screen.

Run once per account. The credential files are gitignored.

---

## 7. Application Bootstrap Changes

### Startup Order

No changes to the core startup sequence. The email plugin is loaded through the existing plugin loader like any other plugin. Providers connect during `plugin.setup()`.

### Config Changes

`QuartermasterConfig` gains an `email: EmailConfig` field (optional, defaults to empty accounts dict). No changes to existing config fields.

### Plugin Discovery

Add `EmailPlugin` to `app.py`'s `_discover_plugins()`:

```python
from plugins.email.plugin import EmailPlugin
self._plugin_loader.register_class(EmailPlugin)
```

### settings.example.yaml

Add the `email` section with placeholder values.

---

## 8. Error Handling

### Per-Account Isolation

Each provider connects independently. If one account's credentials are missing or expired:
- That account is logged as unhealthy and skipped
- Other accounts continue operating normally
- `/status` shows which accounts are up/down
- `email.unread_summary` (all accounts) returns results from healthy accounts only, with a note about any failed accounts

### API Errors

Gmail API errors (rate limits, network failures, permission errors) are caught per-call:
- Returned as `{"error": "..."}` in the tool result dict
- Logged with structlog
- The LLM receives the error and can explain it or retry

### Credential Errors

- Missing credential file at startup → account marked unhealthy, warning logged
- Expired/revoked refresh token → `google.auth.exceptions.RefreshError` caught, account marked unhealthy
- No crash, no retry loop — the account is simply unavailable until credentials are fixed

---

## 9. Monitoring

### Prometheus Metrics

- `qm_email_operations_total` counter (labels: `account`, `operation`, `status`)
  - operation: `unread_summary`, `search`, `read`, `send`, `draft`, `reply`
  - status: `success`, `error`
- `qm_email_operation_duration_seconds` histogram (labels: `account`, `operation`)

### /status Command

```
Email:
  personal (gmail): ok — 3 unread
  friendly-robots (gmail): ok — 12 unread
```

Or on failure:

```
Email:
  personal (gmail): ok — 3 unread
  friendly-robots (gmail): error — RefreshError: token revoked
```

### Health Events

Email plugin emits `plugin.health_changed` events when account status transitions (connected → error, error → connected).

---

## 10. Testing Strategy

### Unit Tests (mocked dependencies)

| File | Coverage |
|------|----------|
| `tests/email/test_models.py` | Pydantic model validation, serialization, edge cases |
| `tests/email/test_gmail.py` | Gmail provider: mock Google API, verify search queries, message parsing, send/draft MIME construction, token refresh write-back |
| `tests/plugins/test_email.py` | Plugin: tool registration, account routing, aggregation, approval tiers, error handling for bad accounts |

### Integration Test

`tests/email/test_gmail_integration.py` — marked `@pytest.mark.integration`, skipped by default:
- Uses a real Gmail test account
- Creates a draft, reads it back, verifies content
- Validates OAuth flow works end-to-end

### Error Handling Tests

- Missing credential file → account skipped, plugin healthy
- Expired refresh token → account marked unhealthy
- API rate limit → error returned in tool result
- Invalid account name → clean error message

---

## 11. Dependencies

### New Python Dependencies

```
google-api-python-client>=2.0.0   # Gmail API
google-auth-oauthlib>=1.0.0       # OAuth2 flow for setup script
google-auth>=2.0.0                 # OAuth2 credentials
```

These are the same packages ledgr uses. Already available in the Python environment.

### New Files Summary

| Component | Files | Type |
|-----------|-------|------|
| Email package | 4 in `src/quartermaster/email/` | New |
| Email plugin | 2 in `plugins/email/` | New |
| OAuth setup | 1 `scripts/gmail_oauth_setup.py` | New |
| Config models | `src/quartermaster/core/config.py` | Modified |
| App bootstrap | `src/quartermaster/core/app.py` | Modified |
| Settings example | `config/settings.example.yaml` | Modified |
| Requirements | `requirements.txt` | Modified |
| Tests | ~4 in `tests/email/` and `tests/plugins/` | New |

---

## 12. Connection to Future Sub-Phases

| Sub-Phase | How It Builds on 3a |
|-----------|-------------------|
| 3b (O365 Email) | New `OutlookProvider` implementing same `EmailProvider` protocol. Config adds `provider: outlook` entries. Plugin unchanged. |
| 3c (Google Calendar) | Reuses same Google OAuth credentials (add calendar scope). Separate `calendar` plugin + provider package. |
| 3f (Enhanced Briefings) | Briefing plugin calls `email.unread_summary` tool — already available after 3a. Template update only. |

The provider abstraction ensures adding O365 is a single new file implementing `EmailProvider`, plus config entries. No changes to the plugin or tool interface.

---

*Designed in a collaborative session, March 26, 2026.*
