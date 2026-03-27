# Phase 3a — Gmail Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Gmail integration with 2 accounts, full read/write, approval-gated sending, and provider-agnostic email abstraction.

**Architecture:** Email provider package (`src/quartermaster/email/`) with protocol + Gmail implementation. Thin email plugin (`plugins/email/`) registers tools into the Tool Registry. All Gmail API calls wrapped in `asyncio.to_thread()`. Send/reply use `confirm` approval tier.

**Tech Stack:** `google-api-python-client`, `google-auth`, `google-auth-oauthlib`, Python 3.13, Pydantic v2, structlog, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-26-quartermaster-phase3a-gmail-integration.md`

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `src/quartermaster/email/__init__.py` | Package init, re-exports |
| `src/quartermaster/email/models.py` | `AttachmentInfo`, `EmailSummary`, `EmailMessage` Pydantic models |
| `src/quartermaster/email/provider.py` | `EmailProvider` protocol |
| `src/quartermaster/email/gmail.py` | `GmailProvider` — Gmail API client with async wrapping |
| `plugins/email/__init__.py` | Plugin package init |
| `plugins/email/plugin.py` | `EmailPlugin` — tool registration, account routing |
| `scripts/gmail_oauth_setup.py` | OAuth setup script (run once per account) |
| `tests/email/__init__.py` | Test package init |
| `tests/email/test_models.py` | Email model tests |
| `tests/email/test_gmail.py` | Gmail provider tests (mocked Google API) |
| `tests/plugins/test_email_plugin.py` | Email plugin tests (mocked providers) |

Note: `tests/email/test_gmail_integration.py` (integration test against real Gmail) is listed in the spec but not created in this plan. It requires real OAuth credentials and is run manually — not part of the automated test suite.

### Modified Files

| File | Changes |
|------|---------|
| `src/quartermaster/core/config.py` | Add `EmailAccountConfig`, `EmailConfig` models; add `email` field to `QuartermasterConfig` |
| `src/quartermaster/core/metrics.py` | Add email Prometheus metrics |
| `src/quartermaster/core/app.py` | Register `EmailPlugin` in `_discover_plugins()`, wire `plugin_loader` into `PluginContext` |
| `src/quartermaster/plugin/context.py` | Add `plugin_loader` field |
| `plugins/commands/plugin.py` | Add plugin health iteration to `/status` command output |
| `config/settings.example.yaml` | Add `email` section with placeholder config |
| `requirements.txt` | Add Google API dependencies |

---

## Task 1: Add Google API dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add dependencies to requirements.txt**

Add after the `mcp` line:

```
google-api-python-client>=2.0.0
google-auth>=2.0.0
google-auth-oauthlib>=1.0.0
```

- [ ] **Step 2: Install and verify**

Run: `pip install -r requirements.txt`
Expected: Successfully installs (packages likely already present from ledgr work)

- [ ] **Step 3: Verify imports**

Run: `python3 -c "from google.oauth2.credentials import Credentials; from googleapiclient.discovery import build; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add Google API dependencies for Phase 3a email"
```

---

## Task 2: Email config models

**Files:**
- Modify: `src/quartermaster/core/config.py`
- Create: `tests/core/test_email_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/core/test_email_config.py`:

```python
"""Tests for email configuration models."""

from quartermaster.core.config import EmailAccountConfig, EmailConfig, QuartermasterConfig


def test_email_account_config() -> None:
    account = EmailAccountConfig(
        provider="gmail",
        credential_file="credentials/gmail_personal.json",
        label="Personal Gmail",
    )
    assert account.provider == "gmail"
    assert account.credential_file == "credentials/gmail_personal.json"
    assert account.label == "Personal Gmail"


def test_email_config_defaults() -> None:
    config = EmailConfig()
    assert config.accounts == {}


def test_email_config_with_accounts() -> None:
    config = EmailConfig(
        accounts={
            "personal": EmailAccountConfig(
                provider="gmail",
                credential_file="credentials/gmail_personal.json",
                label="Personal Gmail",
            ),
            "fr": EmailAccountConfig(
                provider="gmail",
                credential_file="credentials/gmail_fr.json",
                label="Friendly Robots",
            ),
        }
    )
    assert len(config.accounts) == 2
    assert config.accounts["personal"].label == "Personal Gmail"
    assert config.accounts["fr"].provider == "gmail"


def test_quartermaster_config_has_email() -> None:
    config = QuartermasterConfig()
    assert hasattr(config, "email")
    assert config.email.accounts == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_email_config.py -v`
Expected: FAIL — `EmailAccountConfig` and `EmailConfig` not found

- [ ] **Step 3: Implement config models**

Add to `src/quartermaster/core/config.py` before `QuartermasterConfig`:

```python
class EmailAccountConfig(BaseModel):
    """Configuration for a single email account."""

    provider: str  # "gmail", future: "outlook"
    credential_file: str
    label: str


class EmailConfig(BaseModel):
    """Email integration configuration."""

    accounts: dict[str, EmailAccountConfig] = {}
```

Add `email` field to `QuartermasterConfig`:

```python
    email: EmailConfig = Field(default_factory=EmailConfig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_email_config.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass (existing tests unaffected by new optional field)

- [ ] **Step 6: Commit**

```bash
git add src/quartermaster/core/config.py tests/core/test_email_config.py
git commit -m "feat: email config models — EmailAccountConfig, EmailConfig"
```

---

## Task 3: Email data models

**Files:**
- Create: `src/quartermaster/email/__init__.py`
- Create: `src/quartermaster/email/models.py`
- Create: `tests/email/__init__.py`
- Create: `tests/email/test_models.py`

- [ ] **Step 1: Write failing tests**

Create `tests/email/__init__.py` (empty) and `tests/email/test_models.py`:

```python
"""Tests for email data models."""

from datetime import datetime, timezone

from quartermaster.email.models import AttachmentInfo, EmailMessage, EmailSummary


def test_email_summary_minimal() -> None:
    summary = EmailSummary(
        id="msg123",
        subject="Test Subject",
        sender="alice@example.com",
        date=None,
        snippet="Hello world...",
        is_read=False,
    )
    assert summary.id == "msg123"
    assert summary.labels == []  # default
    assert summary.is_read is False


def test_email_summary_with_date() -> None:
    dt = datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc)
    summary = EmailSummary(
        id="msg456",
        subject="Meeting Tomorrow",
        sender="bob@example.com",
        date=dt,
        snippet="Don't forget...",
        is_read=True,
        labels=["INBOX", "IMPORTANT"],
    )
    assert summary.date == dt
    assert len(summary.labels) == 2


def test_attachment_info() -> None:
    attachment = AttachmentInfo(
        filename="report.pdf",
        mime_type="application/pdf",
        size=1024,
    )
    assert attachment.filename == "report.pdf"
    assert attachment.size == 1024


def test_email_message_full() -> None:
    msg = EmailMessage(
        id="msg789",
        thread_id="thread001",
        subject="Important Update",
        sender="ceo@company.com",
        to=["brian@example.com"],
        cc=["team@example.com"],
        date=datetime(2026, 3, 26, 12, 0, tzinfo=timezone.utc),
        body="Full email body text here.",
        snippet="Full email body...",
        is_read=False,
        labels=["INBOX"],
        attachments=[
            AttachmentInfo(filename="doc.pdf", mime_type="application/pdf", size=2048),
        ],
    )
    assert msg.thread_id == "thread001"
    assert len(msg.to) == 1
    assert len(msg.attachments) == 1
    assert msg.attachments[0].filename == "doc.pdf"


def test_email_message_minimal() -> None:
    msg = EmailMessage(
        id="m1",
        thread_id="t1",
        subject="Hi",
        sender="a@b.com",
        to=["c@d.com"],
        date=None,
        body="",
        snippet="",
        is_read=True,
    )
    assert msg.cc == []  # default
    assert msg.attachments == []  # default


def test_email_summary_serialization() -> None:
    summary = EmailSummary(
        id="msg1",
        subject="Test",
        sender="a@b.com",
        date=None,
        snippet="...",
        is_read=False,
    )
    data = summary.model_dump()
    assert data["id"] == "msg1"
    assert data["is_read"] is False
    # Round-trip
    restored = EmailSummary.model_validate(data)
    assert restored == summary
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/email/test_models.py -v`
Expected: FAIL — `quartermaster.email.models` not found

- [ ] **Step 3: Implement models**

Create `src/quartermaster/email/__init__.py`:

```python
"""Email provider abstraction and implementations."""
```

Create `src/quartermaster/email/models.py`:

```python
"""Email data models — provider-agnostic."""

from datetime import datetime

from pydantic import BaseModel


class AttachmentInfo(BaseModel):
    """Metadata about an email attachment."""

    filename: str
    mime_type: str
    size: int  # bytes


class EmailSummary(BaseModel):
    """Lightweight email summary for listings."""

    id: str
    subject: str
    sender: str
    date: datetime | None
    snippet: str
    is_read: bool
    labels: list[str] = []


class EmailMessage(BaseModel):
    """Full email message with body and attachments."""

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/email/test_models.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/email/ tests/email/
git commit -m "feat: email data models — EmailSummary, EmailMessage, AttachmentInfo"
```

---

## Task 4: Email provider protocol

**Files:**
- Create: `src/quartermaster/email/provider.py`

- [ ] **Step 1: Create the protocol**

```python
"""Email provider protocol — defines the contract for all email backends."""

from __future__ import annotations

from typing import Protocol

from quartermaster.email.models import EmailMessage, EmailSummary


class EmailProvider(Protocol):
    """Protocol that all email providers must implement."""

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

- [ ] **Step 2: Verify import**

Run: `python3 -c "from quartermaster.email.provider import EmailProvider; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Lint check**

Run: `ruff check src/quartermaster/email/`
Expected: All checks passed

- [ ] **Step 4: Commit**

```bash
git add src/quartermaster/email/provider.py
git commit -m "feat: EmailProvider protocol — contract for email backends"
```

---

## Task 5: Gmail provider — connect and health_check

**Files:**
- Create: `src/quartermaster/email/gmail.py`
- Create: `tests/email/test_gmail.py`

- [ ] **Step 1: Write failing tests for connect and health_check**

Create `tests/email/test_gmail.py`:

```python
"""Tests for Gmail provider."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quartermaster.email.gmail import GmailProvider


@pytest.fixture
def credential_file(tmp_path):
    cred_data = {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "refresh_token": "test-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
    }
    path = tmp_path / "gmail_test.json"
    path.write_text(json.dumps(cred_data))
    return str(path)


@pytest.mark.asyncio
async def test_connect_builds_service(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test Account",
        credential_file=credential_file,
    )
    with patch("quartermaster.email.gmail.build") as mock_build, \
         patch("quartermaster.email.gmail.Credentials") as mock_creds_cls:
        mock_creds = MagicMock()
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds
        mock_creds.valid = True
        mock_build.return_value = MagicMock()

        await provider.connect()

        mock_creds_cls.from_authorized_user_file.assert_called_once_with(
            credential_file,
        )
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)


@pytest.mark.asyncio
async def test_connect_refreshes_expired_token(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test Account",
        credential_file=credential_file,
    )
    with patch("quartermaster.email.gmail.build") as mock_build, \
         patch("quartermaster.email.gmail.Credentials") as mock_creds_cls, \
         patch("quartermaster.email.gmail.GoogleRequest"):
        mock_creds = MagicMock()
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "test-refresh-token"
        mock_build.return_value = MagicMock()

        await provider.connect()

        mock_creds.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_true(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test Account",
        credential_file=credential_file,
    )
    provider._service = MagicMock()
    mock_profile = MagicMock()
    mock_profile.execute.return_value = {"emailAddress": "test@gmail.com"}
    provider._service.users.return_value.getProfile.return_value = mock_profile

    result = await provider.health_check()
    assert result is True


@pytest.mark.asyncio
async def test_health_check_false_no_service(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test Account",
        credential_file=credential_file,
    )
    result = await provider.health_check()
    assert result is False


def test_properties(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="personal",
        label="Personal Gmail",
        credential_file=credential_file,
    )
    assert provider.account_name == "personal"
    assert provider.label == "Personal Gmail"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/email/test_gmail.py -v`
Expected: FAIL — `GmailProvider` not found

- [ ] **Step 3: Implement GmailProvider (connect + health_check)**

Create `src/quartermaster/email/gmail.py`:

```python
"""Gmail provider — Gmail API client with async wrapping."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import structlog
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from quartermaster.email.models import EmailMessage, EmailSummary

logger = structlog.get_logger()

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.modify"


class GmailProvider:
    """Gmail API provider with async wrapping.

    All Google API calls are synchronous. This provider wraps them in
    asyncio.to_thread() to avoid blocking the event loop.
    """

    def __init__(
        self,
        account_name: str,
        label: str,
        credential_file: str,
    ) -> None:
        self._account_name = account_name
        self._label = label
        self._credential_file = credential_file
        self._service: Any = None
        self._creds: Credentials | None = None

    @property
    def account_name(self) -> str:
        return self._account_name

    @property
    def label(self) -> str:
        return self._label

    async def connect(self) -> None:
        """Load credentials, refresh if needed, build Gmail service."""
        def _connect() -> None:
            self._creds = Credentials.from_authorized_user_file(
                self._credential_file,
            )
            if not self._creds.valid:
                if self._creds.expired and self._creds.refresh_token:
                    self._creds.refresh(GoogleRequest())
                    self._persist_credentials()
                else:
                    raise RuntimeError(
                        f"Gmail credentials invalid for {self._account_name} "
                        f"and cannot be refreshed"
                    )
            self._service = build("gmail", "v1", credentials=self._creds)

        await asyncio.to_thread(_connect)
        logger.info(
            "gmail_provider_connected",
            account=self._account_name,
        )

    async def health_check(self) -> bool:
        """Check if the Gmail service is functional."""
        if self._service is None:
            return False
        try:
            def _check() -> dict[str, Any]:
                return (
                    self._service.users()
                    .getProfile(userId="me")
                    .execute()
                )

            await asyncio.to_thread(_check)
            return True
        except Exception as exc:
            logger.warning(
                "gmail_health_check_failed",
                account=self._account_name,
                error=str(exc),
            )
            return False

    def _persist_credentials(self) -> None:
        """Atomically write refreshed credentials back to file."""
        cred_path = Path(self._credential_file)
        data = json.loads(self._creds.to_json())
        # Atomic write: temp file + rename
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=cred_path.parent,
            suffix=".tmp",
            delete=False,
        ) as tmp:
            json.dump(data, tmp, indent=2)
            tmp_path = Path(tmp.name)
        tmp_path.rename(cred_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/email/test_gmail.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Lint check**

Run: `ruff check src/quartermaster/email/gmail.py tests/email/test_gmail.py`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add src/quartermaster/email/gmail.py tests/email/test_gmail.py
git commit -m "feat: GmailProvider — connect, health_check, credential persistence"
```

---

## Task 6: Gmail provider — read operations (unread_summary, search, read)

**Files:**
- Modify: `src/quartermaster/email/gmail.py`
- Modify: `tests/email/test_gmail.py`

- [ ] **Step 1: Write failing tests for read operations**

Add to `tests/email/test_gmail.py`:

```python
import base64


def _make_gmail_message(
    msg_id: str = "msg1",
    thread_id: str = "thread1",
    subject: str = "Test Subject",
    sender: str = "sender@example.com",
    to: str = "me@example.com",
    body_text: str = "Hello, world!",
    snippet: str = "Hello...",
    label_ids: list[str] | None = None,
) -> dict:
    """Build a mock Gmail API message response."""
    encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()
    return {
        "id": msg_id,
        "threadId": thread_id,
        "snippet": snippet,
        "labelIds": label_ids or ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "To", "value": to},
                {"name": "Date", "value": "Wed, 26 Mar 2026 10:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {"data": encoded_body},
            "parts": [],
        },
    }


@pytest.mark.asyncio
async def test_get_unread_summary(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test",
        credential_file=credential_file,
    )
    mock_service = MagicMock()
    provider._service = mock_service

    # messages.list returns message IDs
    mock_list = MagicMock()
    mock_list.execute.return_value = {
        "messages": [{"id": "msg1"}, {"id": "msg2"}]
    }
    mock_service.users.return_value.messages.return_value.list.return_value = mock_list

    # messages.get returns full messages
    mock_get = MagicMock()
    mock_get.execute.side_effect = [
        _make_gmail_message(msg_id="msg1", subject="First"),
        _make_gmail_message(msg_id="msg2", subject="Second", label_ids=["INBOX"]),
    ]
    mock_service.users.return_value.messages.return_value.get.return_value = mock_get

    result = await provider.get_unread_summary(max_results=5)
    assert len(result) == 2
    assert result[0].id == "msg1"
    assert result[0].subject == "First"
    assert result[0].is_read is False  # has UNREAD label
    assert result[1].is_read is True   # no UNREAD label


@pytest.mark.asyncio
async def test_search(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test",
        credential_file=credential_file,
    )
    mock_service = MagicMock()
    provider._service = mock_service

    mock_list = MagicMock()
    mock_list.execute.return_value = {"messages": [{"id": "msg1"}]}
    mock_service.users.return_value.messages.return_value.list.return_value = mock_list

    mock_get = MagicMock()
    mock_get.execute.return_value = _make_gmail_message(
        msg_id="msg1", subject="Search Result"
    )
    mock_service.users.return_value.messages.return_value.get.return_value = mock_get

    result = await provider.search("from:alice@example.com", max_results=5)
    assert len(result) == 1
    assert result[0].subject == "Search Result"

    # Verify the query was passed to Gmail
    mock_service.users.return_value.messages.return_value.list.assert_called_once_with(
        userId="me", q="from:alice@example.com", maxResults=5
    )


@pytest.mark.asyncio
async def test_read(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test",
        credential_file=credential_file,
    )
    mock_service = MagicMock()
    provider._service = mock_service

    mock_get = MagicMock()
    mock_get.execute.return_value = _make_gmail_message(
        msg_id="msg1",
        subject="Full Message",
        body_text="This is the full body.",
    )
    mock_service.users.return_value.messages.return_value.get.return_value = mock_get

    result = await provider.read("msg1")
    assert result.id == "msg1"
    assert result.subject == "Full Message"
    assert result.body == "This is the full body."
    assert result.sender == "sender@example.com"
    assert result.thread_id == "thread1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/email/test_gmail.py::test_get_unread_summary tests/email/test_gmail.py::test_search tests/email/test_gmail.py::test_read -v`
Expected: FAIL — methods not implemented

- [ ] **Step 3: Implement read operations**

Add these methods to `GmailProvider` in `src/quartermaster/email/gmail.py`:

```python
    async def get_unread_summary(self, max_results: int = 20) -> list[EmailSummary]:
        """Get unread email summaries."""
        return await self.search("is:unread", max_results=max_results)

    async def search(self, query: str, max_results: int = 10) -> list[EmailSummary]:
        """Search emails using Gmail query syntax."""
        def _search() -> list[dict[str, Any]]:
            result = (
                self._service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )
            msg_ids = result.get("messages", [])
            messages = []
            for msg_ref in msg_ids:
                msg = (
                    self._service.users()
                    .messages()
                    .get(userId="me", id=msg_ref["id"], format="full")
                    .execute()
                )
                messages.append(msg)
            return messages

        raw_messages = await asyncio.to_thread(_search)
        return [self._parse_summary(msg) for msg in raw_messages]

    async def read(self, message_id: str) -> EmailMessage:
        """Read a full email message."""
        def _read() -> dict[str, Any]:
            return (
                self._service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

        raw = await asyncio.to_thread(_read)
        return self._parse_message(raw)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_summary(self, raw: dict[str, Any]) -> EmailSummary:
        """Parse a raw Gmail message into an EmailSummary."""
        headers = self._extract_headers(raw)
        return EmailSummary(
            id=raw["id"],
            subject=headers.get("Subject", ""),
            sender=headers.get("From", ""),
            date=self._parse_date(headers.get("Date")),
            snippet=raw.get("snippet", ""),
            is_read="UNREAD" not in raw.get("labelIds", []),
            labels=raw.get("labelIds", []),
        )

    def _parse_message(self, raw: dict[str, Any]) -> EmailMessage:
        """Parse a raw Gmail message into a full EmailMessage."""
        headers = self._extract_headers(raw)
        payload = raw.get("payload", {})
        return EmailMessage(
            id=raw["id"],
            thread_id=raw.get("threadId", ""),
            subject=headers.get("Subject", ""),
            sender=headers.get("From", ""),
            to=self._parse_address_list(headers.get("To", "")),
            cc=self._parse_address_list(headers.get("Cc", "")),
            date=self._parse_date(headers.get("Date")),
            body=self._extract_text_body(payload),
            snippet=raw.get("snippet", ""),
            is_read="UNREAD" not in raw.get("labelIds", []),
            labels=raw.get("labelIds", []),
            attachments=self._extract_attachments(payload),
        )

    @staticmethod
    def _extract_headers(raw: dict[str, Any]) -> dict[str, str]:
        headers: dict[str, str] = {}
        for h in raw.get("payload", {}).get("headers", []):
            headers[h["name"]] = h["value"]
        return headers

    @staticmethod
    def _parse_date(date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except Exception:
            return None

    @staticmethod
    def _parse_address_list(addr_str: str) -> list[str]:
        if not addr_str:
            return []
        return [a.strip() for a in addr_str.split(",") if a.strip()]

    @staticmethod
    def _extract_text_body(payload: dict[str, Any]) -> str:
        """Recursively extract plain text from email payload."""
        import base64

        mime = payload.get("mimeType", "")
        if mime == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        for part in payload.get("parts", []):
            text = GmailProvider._extract_text_body(part)
            if text:
                return text

        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return ""

    @staticmethod
    def _extract_attachments(payload: dict[str, Any]) -> list:
        """Extract attachment metadata from email payload."""
        from quartermaster.email.models import AttachmentInfo

        attachments: list[AttachmentInfo] = []
        for part in payload.get("parts", []):
            filename = part.get("filename")
            if filename:
                attachments.append(
                    AttachmentInfo(
                        filename=filename,
                        mime_type=part.get("mimeType", "application/octet-stream"),
                        size=part.get("body", {}).get("size", 0),
                    )
                )
        return attachments
```

Also add these imports at the top of the file (after `from __future__ import annotations`):

```python
import base64
from datetime import datetime
from email.utils import parsedate_to_datetime
```

And remove the inline `import base64` from `_extract_text_body` and `from email.utils import parsedate_to_datetime` from `_parse_date` — they should use the top-level imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/email/test_gmail.py -v`
Expected: 8 PASSED (5 from Task 5 + 3 new)

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/email/gmail.py tests/email/test_gmail.py
git commit -m "feat: GmailProvider read operations — unread_summary, search, read"
```

---

## Task 7: Gmail provider — write operations (send, draft, reply)

**Files:**
- Modify: `src/quartermaster/email/gmail.py`
- Modify: `tests/email/test_gmail.py`

- [ ] **Step 1: Write failing tests for write operations**

Add to `tests/email/test_gmail.py`:

```python
@pytest.mark.asyncio
async def test_send(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test",
        credential_file=credential_file,
    )
    mock_service = MagicMock()
    provider._service = mock_service

    mock_send = MagicMock()
    mock_send.execute.return_value = {"id": "sent_msg1"}
    mock_service.users.return_value.messages.return_value.send.return_value = mock_send

    result = await provider.send(
        to="recipient@example.com",
        subject="Test Email",
        body="This is a test.",
    )
    assert result["message_id"] == "sent_msg1"
    assert result["status"] == "sent"

    # Verify send was called with a raw message
    mock_service.users.return_value.messages.return_value.send.assert_called_once()


@pytest.mark.asyncio
async def test_send_with_cc(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test",
        credential_file=credential_file,
    )
    mock_service = MagicMock()
    provider._service = mock_service

    mock_send = MagicMock()
    mock_send.execute.return_value = {"id": "sent_msg2"}
    mock_service.users.return_value.messages.return_value.send.return_value = mock_send

    result = await provider.send(
        to="recipient@example.com",
        subject="CC Test",
        body="Testing CC.",
        cc="team@example.com",
    )
    assert result["status"] == "sent"


@pytest.mark.asyncio
async def test_draft(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test",
        credential_file=credential_file,
    )
    mock_service = MagicMock()
    provider._service = mock_service

    mock_create = MagicMock()
    mock_create.execute.return_value = {"id": "draft1", "message": {"id": "msg1"}}
    mock_service.users.return_value.drafts.return_value.create.return_value = mock_create

    result = await provider.draft(
        to="recipient@example.com",
        subject="Draft Subject",
        body="Draft body.",
    )
    assert result["draft_id"] == "draft1"
    assert result["status"] == "drafted"


@pytest.mark.asyncio
async def test_reply(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test",
        credential_file=credential_file,
    )
    mock_service = MagicMock()
    provider._service = mock_service

    # Mock reading the original message for thread_id and headers
    mock_get = MagicMock()
    mock_get.execute.return_value = _make_gmail_message(
        msg_id="original1",
        thread_id="thread1",
        subject="Original Subject",
        sender="alice@example.com",
    )
    mock_service.users.return_value.messages.return_value.get.return_value = mock_get

    # Mock sending the reply
    mock_send = MagicMock()
    mock_send.execute.return_value = {"id": "reply_msg1", "threadId": "thread1"}
    mock_service.users.return_value.messages.return_value.send.return_value = mock_send

    result = await provider.reply(
        message_id="original1",
        body="Thanks for the update!",
    )
    assert result["message_id"] == "reply_msg1"
    assert result["status"] == "sent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/email/test_gmail.py::test_send tests/email/test_gmail.py::test_draft tests/email/test_gmail.py::test_reply -v`
Expected: FAIL — methods not implemented

- [ ] **Step 3: Implement write operations**

Add these methods to `GmailProvider` in `src/quartermaster/email/gmail.py`:

```python
    async def send(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> dict[str, str]:
        """Send an email."""
        raw = self._build_mime_message(to=to, subject=subject, body=body, cc=cc)

        def _send() -> dict[str, Any]:
            return (
                self._service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )

        result = await asyncio.to_thread(_send)
        logger.info(
            "gmail_message_sent",
            account=self._account_name,
            to=to,
            subject=subject,
        )
        return {"message_id": result["id"], "status": "sent"}

    async def draft(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> dict[str, str]:
        """Create a draft email."""
        raw = self._build_mime_message(to=to, subject=subject, body=body, cc=cc)

        def _draft() -> dict[str, Any]:
            return (
                self._service.users()
                .drafts()
                .create(userId="me", body={"message": {"raw": raw}})
                .execute()
            )

        result = await asyncio.to_thread(_draft)
        logger.info(
            "gmail_draft_created",
            account=self._account_name,
            to=to,
            subject=subject,
        )
        return {"draft_id": result["id"], "status": "drafted"}

    async def reply(self, message_id: str, body: str) -> dict[str, str]:
        """Reply to an existing email."""
        # Read original message for thread context
        original = await self.read(message_id)

        reply_subject = original.subject
        if not reply_subject.lower().startswith("re:"):
            reply_subject = f"Re: {reply_subject}"

        raw = self._build_mime_message(
            to=original.sender,
            subject=reply_subject,
            body=body,
            in_reply_to=message_id,
            references=message_id,
        )

        def _send_reply() -> dict[str, Any]:
            return (
                self._service.users()
                .messages()
                .send(
                    userId="me",
                    body={"raw": raw, "threadId": original.thread_id},
                )
                .execute()
            )

        result = await asyncio.to_thread(_send_reply)
        logger.info(
            "gmail_reply_sent",
            account=self._account_name,
            to=original.sender,
            thread_id=original.thread_id,
        )
        return {"message_id": result["id"], "status": "sent"}

    @staticmethod
    def _build_mime_message(
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> str:
        """Build a base64url-encoded MIME message."""
        import base64
        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        return base64.urlsafe_b64encode(msg.as_bytes()).decode()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/email/test_gmail.py -v`
Expected: 12 PASSED (8 previous + 4 new)

- [ ] **Step 5: Lint check**

Run: `ruff check src/quartermaster/email/ tests/email/`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add src/quartermaster/email/gmail.py tests/email/test_gmail.py
git commit -m "feat: GmailProvider write operations — send, draft, reply"
```

---

## Task 8: Email Prometheus metrics

**Files:**
- Modify: `src/quartermaster/core/metrics.py`

- [ ] **Step 1: Add email metrics**

Add to `src/quartermaster/core/metrics.py` after the MCP Server metrics block:

```python
# Email metrics
email_operations_total = Counter(
    "qm_email_operations_total",
    "Total email operations",
    ["account", "operation", "status"],
)
email_operation_duration = Histogram(
    "qm_email_operation_duration_seconds",
    "Email operation duration",
    ["account", "operation"],
)
```

- [ ] **Step 2: Verify import**

Run: `python3 -c "from quartermaster.core.metrics import email_operations_total, email_operation_duration; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/quartermaster/core/metrics.py
git commit -m "feat: add email Prometheus metrics"
```

---

## Task 9: Email plugin — tool registration and account routing

**Files:**
- Create: `plugins/email/__init__.py`
- Create: `plugins/email/plugin.py`
- Create: `tests/plugins/test_email_plugin.py`

- [ ] **Step 1: Write failing tests**

Create `tests/plugins/test_email_plugin.py`:

```python
"""Tests for the Email plugin."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quartermaster.core.config import EmailAccountConfig, EmailConfig, QuartermasterConfig
from quartermaster.core.tools import ApprovalTier, ToolRegistry
from quartermaster.plugin.context import PluginContext


@pytest.fixture
def email_config() -> QuartermasterConfig:
    return QuartermasterConfig(
        email=EmailConfig(
            accounts={
                "personal": EmailAccountConfig(
                    provider="gmail",
                    credential_file="credentials/gmail_personal.json",
                    label="Personal Gmail",
                ),
                "fr": EmailAccountConfig(
                    provider="gmail",
                    credential_file="credentials/gmail_fr.json",
                    label="Friendly Robots",
                ),
            }
        )
    )


@pytest.fixture
def mock_ctx(email_config: QuartermasterConfig) -> PluginContext:
    events = MagicMock()
    events.emit = AsyncMock()
    events.subscribe = MagicMock()
    tools = ToolRegistry(events=events)
    return PluginContext(
        config=email_config,
        events=events,
        tools=tools,
    )


@pytest.mark.asyncio
async def test_plugin_registers_tools(mock_ctx: PluginContext) -> None:
    from plugins.email.plugin import EmailPlugin

    plugin = EmailPlugin()

    with patch("plugins.email.plugin.GmailProvider") as MockGmail:
        mock_provider = AsyncMock()
        mock_provider.account_name = "personal"
        mock_provider.label = "Personal Gmail"
        mock_provider.health_check = AsyncMock(return_value=True)
        MockGmail.return_value = mock_provider

        await plugin.setup(mock_ctx)

    tool_names = [t.name for t in mock_ctx.tools.list_tools()]
    assert "email.unread_summary" in tool_names
    assert "email.search" in tool_names
    assert "email.read" in tool_names
    assert "email.draft" in tool_names
    assert "email.send" in tool_names
    assert "email.reply" in tool_names


@pytest.mark.asyncio
async def test_send_is_confirm_tier(mock_ctx: PluginContext) -> None:
    from plugins.email.plugin import EmailPlugin

    plugin = EmailPlugin()

    with patch("plugins.email.plugin.GmailProvider") as MockGmail:
        mock_provider = AsyncMock()
        mock_provider.account_name = "personal"
        mock_provider.label = "Personal Gmail"
        mock_provider.health_check = AsyncMock(return_value=True)
        MockGmail.return_value = mock_provider

        await plugin.setup(mock_ctx)

    send_tool = mock_ctx.tools.get("email.send")
    assert send_tool is not None
    assert send_tool.approval_tier == ApprovalTier.CONFIRM

    reply_tool = mock_ctx.tools.get("email.reply")
    assert reply_tool is not None
    assert reply_tool.approval_tier == ApprovalTier.CONFIRM


@pytest.mark.asyncio
async def test_read_tools_are_autonomous(mock_ctx: PluginContext) -> None:
    from plugins.email.plugin import EmailPlugin

    plugin = EmailPlugin()

    with patch("plugins.email.plugin.GmailProvider") as MockGmail:
        mock_provider = AsyncMock()
        mock_provider.account_name = "personal"
        mock_provider.label = "Personal Gmail"
        mock_provider.health_check = AsyncMock(return_value=True)
        MockGmail.return_value = mock_provider

        await plugin.setup(mock_ctx)

    for name in ["email.unread_summary", "email.search", "email.read", "email.draft"]:
        tool = mock_ctx.tools.get(name)
        assert tool is not None, f"{name} not registered"
        assert tool.approval_tier == ApprovalTier.AUTONOMOUS, f"{name} should be autonomous"


@pytest.mark.asyncio
async def test_invalid_account_returns_error(mock_ctx: PluginContext) -> None:
    from plugins.email.plugin import EmailPlugin

    plugin = EmailPlugin()

    with patch("plugins.email.plugin.GmailProvider") as MockGmail:
        mock_provider = AsyncMock()
        mock_provider.account_name = "personal"
        mock_provider.label = "Personal Gmail"
        mock_provider.health_check = AsyncMock(return_value=True)
        MockGmail.return_value = mock_provider

        await plugin.setup(mock_ctx)

    result = await mock_ctx.tools.execute("email.read", {"account": "nonexistent", "message_id": "m1"})
    assert "error" in result


@pytest.mark.asyncio
async def test_unread_summary_aggregates_all_accounts(mock_ctx: PluginContext) -> None:
    from plugins.email.plugin import EmailPlugin
    from quartermaster.email.models import EmailSummary

    plugin = EmailPlugin()

    mock_summaries_personal = [
        EmailSummary(id="p1", subject="Personal", sender="a@b.com", date=None, snippet="...", is_read=False),
    ]
    mock_summaries_fr = [
        EmailSummary(id="f1", subject="FR", sender="c@d.com", date=None, snippet="...", is_read=False),
    ]

    with patch("plugins.email.plugin.GmailProvider") as MockGmail:
        provider1 = AsyncMock()
        provider1.account_name = "personal"
        provider1.label = "Personal Gmail"
        provider1.health_check = AsyncMock(return_value=True)
        provider1.get_unread_summary = AsyncMock(return_value=mock_summaries_personal)

        provider2 = AsyncMock()
        provider2.account_name = "fr"
        provider2.label = "Friendly Robots"
        provider2.health_check = AsyncMock(return_value=True)
        provider2.get_unread_summary = AsyncMock(return_value=mock_summaries_fr)

        MockGmail.side_effect = [provider1, provider2]
        await plugin.setup(mock_ctx)

    # Call with no account — should aggregate
    result = await mock_ctx.tools.execute("email.unread_summary", {})
    assert "accounts" in result
    assert len(result["accounts"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/plugins/test_email_plugin.py -v`
Expected: FAIL — `plugins.email.plugin` not found

- [ ] **Step 3: Implement the plugin**

Create `plugins/email/__init__.py` (empty).

Create `plugins/email/plugin.py`:

```python
"""Email plugin — unified email tool registration and account routing."""

from __future__ import annotations

import time
from typing import Any

import structlog

from quartermaster.core.metrics import email_operation_duration, email_operations_total
from quartermaster.core.tools import ApprovalTier
from quartermaster.email.gmail import GmailProvider
from quartermaster.email.provider import EmailProvider
from quartermaster.plugin.base import QuartermasterPlugin
from quartermaster.plugin.context import PluginContext
from quartermaster.plugin.health import HealthReport, HealthStatus

logger = structlog.get_logger()

# Provider registry — maps provider name to class
_PROVIDER_CLASSES: dict[str, type] = {
    "gmail": GmailProvider,
}


class EmailPlugin(QuartermasterPlugin):
    """Unified email plugin with provider-agnostic tool interface."""

    name = "email"
    version = "0.1.0"
    dependencies: list[str] = []

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None
        self._providers: dict[str, EmailProvider] = {}
        self._account_status: dict[str, dict[str, Any]] = {}

    async def setup(self, ctx: PluginContext) -> None:
        self._ctx = ctx

        # Instantiate and connect providers
        for account_name, account_cfg in ctx.config.email.accounts.items():
            provider_cls = _PROVIDER_CLASSES.get(account_cfg.provider)
            if provider_cls is None:
                logger.warning(
                    "email_unknown_provider",
                    account=account_name,
                    provider=account_cfg.provider,
                )
                self._account_status[account_name] = {
                    "status": "error",
                    "error": f"Unknown provider: {account_cfg.provider}",
                    "label": account_cfg.label,
                    "provider": account_cfg.provider,
                }
                continue

            provider = provider_cls(
                account_name=account_name,
                label=account_cfg.label,
                credential_file=account_cfg.credential_file,
            )
            try:
                await provider.connect()
                self._providers[account_name] = provider
                self._account_status[account_name] = {
                    "status": "ok",
                    "label": account_cfg.label,
                    "provider": account_cfg.provider,
                }
                logger.info(
                    "email_account_connected",
                    account=account_name,
                    provider=account_cfg.provider,
                )
            except Exception as exc:
                logger.error(
                    "email_account_connect_failed",
                    account=account_name,
                    error=str(exc),
                )
                self._account_status[account_name] = {
                    "status": "error",
                    "error": str(exc),
                    "label": account_cfg.label,
                    "provider": account_cfg.provider,
                }

        # Register tools
        self._register_tools(ctx)
        logger.info("email_plugin_ready", accounts=len(self._providers))

    async def teardown(self) -> None:
        pass

    async def health(self) -> HealthReport:
        total = len(self._account_status)
        if total == 0:
            return HealthReport(status=HealthStatus.OK, message="No email accounts configured")

        # Live health check each connected provider
        for name, provider in self._providers.items():
            try:
                is_healthy = await provider.health_check()
                self._account_status[name]["status"] = "ok" if is_healthy else "error"
                if not is_healthy:
                    self._account_status[name]["error"] = "health check failed"
            except Exception as exc:
                self._account_status[name]["status"] = "error"
                self._account_status[name]["error"] = str(exc)

        healthy = sum(
            1 for s in self._account_status.values() if s["status"] == "ok"
        )

        if healthy == total:
            status = HealthStatus.OK
        elif healthy > 0:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.DOWN

        return HealthReport(
            status=status,
            message=f"{healthy}/{total} accounts connected",
            details=dict(self._account_status),
        )

    def _register_tools(self, ctx: PluginContext) -> None:
        """Register email tools into the Tool Registry."""
        ctx.tools.register(
            name="email.unread_summary",
            description="Get unread email summaries. Omit 'account' for all accounts.",
            parameters={
                "type": "object",
                "properties": {
                    "account": {
                        "type": "string",
                        "description": "Account name (optional — omit for all accounts)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results per account",
                        "default": 20,
                    },
                },
            },
            handler=self._handle_unread_summary,
            approval_tier=ApprovalTier.AUTONOMOUS,
        )

        ctx.tools.register(
            name="email.search",
            description="Search emails. Omit 'account' to search all accounts.",
            parameters={
                "type": "object",
                "properties": {
                    "account": {
                        "type": "string",
                        "description": "Account name (optional — omit for all accounts)",
                    },
                    "query": {"type": "string", "description": "Search query (Gmail syntax)"},
                    "max_results": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
            handler=self._handle_search,
            approval_tier=ApprovalTier.AUTONOMOUS,
        )

        ctx.tools.register(
            name="email.read",
            description="Read a full email message.",
            parameters={
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "Account name"},
                    "message_id": {"type": "string", "description": "Message ID"},
                },
                "required": ["account", "message_id"],
            },
            handler=self._handle_read,
            approval_tier=ApprovalTier.AUTONOMOUS,
        )

        ctx.tools.register(
            name="email.draft",
            description="Create a draft email.",
            parameters={
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "Account to send from"},
                    "to": {"type": "string", "description": "Recipient email"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body (plain text)"},
                    "cc": {"type": "string", "description": "CC recipients (optional)"},
                },
                "required": ["account", "to", "subject", "body"],
            },
            handler=self._handle_draft,
            approval_tier=ApprovalTier.AUTONOMOUS,
        )

        ctx.tools.register(
            name="email.send",
            description="Send an email. Requires approval.",
            parameters={
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "Account to send from"},
                    "to": {"type": "string", "description": "Recipient email"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body (plain text)"},
                    "cc": {"type": "string", "description": "CC recipients (optional)"},
                },
                "required": ["account", "to", "subject", "body"],
            },
            handler=self._handle_send,
            approval_tier=ApprovalTier.CONFIRM,
        )

        ctx.tools.register(
            name="email.reply",
            description="Reply to an email. Requires approval.",
            parameters={
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "Account to reply from"},
                    "message_id": {"type": "string", "description": "Original message ID"},
                    "body": {"type": "string", "description": "Reply body (plain text)"},
                },
                "required": ["account", "message_id", "body"],
            },
            handler=self._handle_reply,
            approval_tier=ApprovalTier.CONFIRM,
        )

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    def _get_provider(self, account: str) -> EmailProvider | None:
        return self._providers.get(account)

    async def _timed_operation(
        self, account: str, operation: str, coro: Any
    ) -> dict[str, Any]:
        """Execute an operation with metrics tracking."""
        start = time.monotonic()
        status = "success"
        try:
            result = await coro
            return result
        except Exception as exc:
            status = "error"
            logger.error(
                "email_operation_error",
                account=account,
                operation=operation,
                error=str(exc),
            )
            return {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            elapsed = time.monotonic() - start
            email_operations_total.labels(
                account=account, operation=operation, status=status
            ).inc()
            email_operation_duration.labels(
                account=account, operation=operation
            ).observe(elapsed)

    def _serialize_summaries(
        self, result: Any, account: str
    ) -> dict[str, Any]:
        """Wrap a list[EmailSummary] or error dict into a consistent dict return."""
        if isinstance(result, dict):
            return result  # error dict passthrough
        return {
            "account": account,
            "summaries": [s.model_dump() for s in result],
            "count": len(result),
        }

    async def _handle_unread_summary(self, params: dict[str, Any]) -> dict[str, Any]:
        account = params.get("account")
        max_results = params.get("max_results", 20)

        if account:
            provider = self._get_provider(account)
            if provider is None:
                return {"error": f"Unknown email account: {account!r}"}
            result = await self._timed_operation(
                account,
                "unread_summary",
                provider.get_unread_summary(max_results=max_results),
            )
            return self._serialize_summaries(result, account)

        # Aggregate all accounts
        results: dict[str, Any] = {"accounts": {}}
        for name, provider in self._providers.items():
            result = await self._timed_operation(
                name,
                "unread_summary",
                provider.get_unread_summary(max_results=max_results),
            )
            results["accounts"][name] = self._serialize_summaries(result, name)
        return results

    async def _handle_search(self, params: dict[str, Any]) -> dict[str, Any]:
        account = params.get("account")
        query = params["query"]
        max_results = params.get("max_results", 10)

        if account:
            provider = self._get_provider(account)
            if provider is None:
                return {"error": f"Unknown email account: {account!r}"}
            result = await self._timed_operation(
                account,
                "search",
                provider.search(query=query, max_results=max_results),
            )
            return self._serialize_summaries(result, account)

        # Aggregate all accounts
        results: dict[str, Any] = {"accounts": {}}
        for name, provider in self._providers.items():
            result = await self._timed_operation(
                name,
                "search",
                provider.search(query=query, max_results=max_results),
            )
            results["accounts"][name] = self._serialize_summaries(result, name)
        return results

    async def _handle_read(self, params: dict[str, Any]) -> dict[str, Any]:
        account = params["account"]
        provider = self._get_provider(account)
        if provider is None:
            return {"error": f"Unknown email account: {account!r}"}
        return await self._timed_operation(
            account, "read", provider.read(message_id=params["message_id"])
        )

    async def _handle_draft(self, params: dict[str, Any]) -> dict[str, Any]:
        account = params["account"]
        provider = self._get_provider(account)
        if provider is None:
            return {"error": f"Unknown email account: {account!r}"}
        return await self._timed_operation(
            account,
            "draft",
            provider.draft(
                to=params["to"],
                subject=params["subject"],
                body=params["body"],
                cc=params.get("cc"),
            ),
        )

    async def _handle_send(self, params: dict[str, Any]) -> dict[str, Any]:
        account = params["account"]
        provider = self._get_provider(account)
        if provider is None:
            return {"error": f"Unknown email account: {account!r}"}
        return await self._timed_operation(
            account,
            "send",
            provider.send(
                to=params["to"],
                subject=params["subject"],
                body=params["body"],
                cc=params.get("cc"),
            ),
        )

    async def _handle_reply(self, params: dict[str, Any]) -> dict[str, Any]:
        account = params["account"]
        provider = self._get_provider(account)
        if provider is None:
            return {"error": f"Unknown email account: {account!r}"}
        return await self._timed_operation(
            account,
            "reply",
            provider.reply(
                message_id=params["message_id"],
                body=params["body"],
            ),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/plugins/test_email_plugin.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Lint check**

Run: `ruff check plugins/email/ tests/plugins/test_email_plugin.py`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add plugins/email/ tests/plugins/test_email_plugin.py
git commit -m "feat: email plugin — tool registration, account routing, metrics"
```

---

## Task 10: Wire plugin into app bootstrap and update config

**Files:**
- Modify: `src/quartermaster/core/app.py`
- Modify: `config/settings.example.yaml`

- [ ] **Step 1: Add EmailPlugin to app.py**

In `_discover_plugins()`, add:

```python
from plugins.email.plugin import EmailPlugin
self._plugin_loader.register_class(EmailPlugin)
```

- [ ] **Step 2: Update settings.example.yaml**

Add the `email` section after the `mcp` section:

```yaml
  # Email integration
  email:
    accounts: {}
    # Example:
    # personal:
    #   provider: gmail
    #   credential_file: "credentials/gmail_personal.json"
    #   label: "Personal Gmail"
    # friendly-robots:
    #   provider: gmail
    #   credential_file: "credentials/gmail_fr.json"
    #   label: "Friendly Robots"
```

- [ ] **Step 3: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 4: Lint check**

Run: `ruff check src/ plugins/ tests/`
Expected: All checks passed

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/core/app.py config/settings.example.yaml
git commit -m "feat: wire EmailPlugin into app bootstrap, update example config"
```

---

## Task 11: /status command — plugin health iteration

**Files:**
- Modify: `src/quartermaster/plugin/context.py`
- Modify: `src/quartermaster/core/app.py`
- Modify: `plugins/commands/plugin.py`

- [ ] **Step 1: Add plugin_loader to PluginContext**

In `src/quartermaster/plugin/context.py`, add a new field:

```python
    plugin_loader: Any = None  # PluginLoader
```

- [ ] **Step 2: Wire plugin_loader into PluginContext in app.py**

In `src/quartermaster/core/app.py`, after `self._plugin_loader = PluginLoader()`, set:

```python
        ctx = PluginContext(
            ...
            plugin_loader=self._plugin_loader,
        )
```

Note: `plugin_loader` is set on the `PluginContext` before `load_all()` is called. The email plugin won't access it during `setup()` — it's used by the commands plugin at `/status` runtime.

- [ ] **Step 3: Add plugin health to /status command**

In `plugins/commands/plugin.py`, in `_cmd_status()`, after the MCP server section, add:

```python
        # Plugin health (email, etc.)
        if self._ctx.plugin_loader:
            health_reports = await self._ctx.plugin_loader.check_health()
            for plugin_name, report in health_reports.items():
                # Skip plugins with no interesting health data
                if not report.details:
                    continue
                status_lines.append(f"\n**{plugin_name.title()}:**")
                for detail_name, detail in report.details.items():
                    if isinstance(detail, dict):
                        label = detail.get("label", detail_name)
                        provider = detail.get("provider", "")
                        acct_status = detail.get("status", "unknown")
                        error = detail.get("error", "")
                        line = f"  {label} ({provider}): {acct_status}"
                        if error:
                            line += f" — {error}"
                        status_lines.append(line)
```

- [ ] **Step 4: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/plugin/context.py src/quartermaster/core/app.py plugins/commands/plugin.py
git commit -m "feat: add plugin health iteration to /status command"
```

---

## Task 12: OAuth setup script

**Files:**
- Create: `scripts/gmail_oauth_setup.py`

- [ ] **Step 1: Create the setup script**

```python
"""
One-time Gmail OAuth2 setup script for Quartermaster.

Usage:
  1. Create a Google Cloud project at https://console.cloud.google.com
  2. Enable the Gmail API
  3. Create OAuth2 credentials (Desktop application type)
  4. Download credentials JSON
  5. Run: python scripts/gmail_oauth_setup.py --credentials <path> --account-name <name>
  6. Complete the browser auth flow
  7. Credential file written to credentials/gmail_<account_name>.json

Scope: gmail.modify (read, compose, send, draft — everything except permanent deletion)
"""

import argparse
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gmail OAuth2 setup for Quartermaster"
    )
    parser.add_argument(
        "--credentials",
        required=True,
        help="Path to Google OAuth client credentials JSON",
    )
    parser.add_argument(
        "--account-name",
        required=True,
        help="Account name (e.g., 'personal', 'friendly-robots')",
    )
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(args.credentials, SCOPES)
    creds = flow.run_local_server(port=0)

    project_root = Path(__file__).parent.parent
    output_path = project_root / f"credentials/gmail_{args.account_name}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write the full credential JSON (includes token_uri, scopes, etc.)
    cred_data = json.loads(creds.to_json())
    output_path.write_text(json.dumps(cred_data, indent=2))

    print(f"\n--- Gmail OAuth2 Setup Complete ---")
    print(f"Account: {args.account_name}")
    print(f"Credentials saved to: {output_path}")
    print(f"\nAdd this to your config/settings.yaml:")
    print(f"  {args.account_name}:")
    print(f'    provider: gmail')
    print(f'    credential_file: "{output_path}"')
    print(f'    label: "Your Label Here"')


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('scripts/gmail_oauth_setup.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/gmail_oauth_setup.py
git commit -m "feat: Gmail OAuth setup script for Quartermaster"
```

---

## Task 13: Final verification — full test suite + lint

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass (existing + new email tests)

- [ ] **Step 2: Run lint**

Run: `ruff check src/ plugins/ tests/`
Expected: All checks passed

- [ ] **Step 3: Run mypy (if configured)**

Run: `mypy src/quartermaster/email/`
Expected: No errors (or pre-existing only)

- [ ] **Step 4: Verify app starts with email config**

Add the email section to `config/settings.yaml` (with no accounts configured):

```yaml
  email:
    accounts: {}
```

Run: `timeout 10 python -m quartermaster 2>&1 | head -20`
Expected: App boots, `email_plugin_ready` appears with `accounts=0`

- [ ] **Step 5: Commit any final fixes**

```bash
git add -A
git commit -m "chore: Phase 3a final verification — all tests passing, lint clean"
```

---

*Implementation plan for Phase 3a Gmail Integration, March 26, 2026.*
