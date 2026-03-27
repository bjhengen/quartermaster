# Phase 3b — O365 Outlook Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add O365 Outlook email via Microsoft Graph API — 2 accounts, full read/write, implementing the existing EmailProvider protocol.

**Architecture:** `OutlookProvider` in `src/quartermaster/email/outlook.py` uses MSAL for OAuth token management and `httpx.AsyncClient` for Graph API calls. MSAL's `SerializableTokenCache` handles token lifecycle; the provider persists the cache to credential files. The email plugin gains the provider registration and minor protocol additions (`provider_type`, `close()`).

**Tech Stack:** `msal`, `httpx` (existing), Python 3.13, Pydantic v2, structlog, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-27-quartermaster-phase3b-outlook-integration.md`

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `src/quartermaster/email/outlook.py` | `OutlookProvider` — MSAL auth + Graph API client |
| `scripts/outlook_oauth_setup.py` | Device code OAuth setup (run once per account) |
| `tests/email/test_outlook.py` | Outlook provider tests (mocked MSAL + httpx) |

### Modified Files

| File | Changes |
|------|---------|
| `src/quartermaster/email/provider.py` | Add `provider_type` property, `close()` method to protocol |
| `src/quartermaster/email/gmail.py` | Add `provider_type` property, no-op `close()` |
| `plugins/email/plugin.py` | Register OutlookProvider, fix health `"provider"` label, teardown calls `close()` |
| `config/settings.example.yaml` | Add Outlook account examples |
| `requirements.txt` | Add `msal>=1.0.0` |
| `tests/email/test_gmail.py` | Add test for `provider_type` and `close()` |
| `tests/plugins/test_email_plugin.py` | Add mixed-provider routing test |

---

## Task 1: Add `msal` dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add msal to requirements.txt**

Add after the `google-auth-oauthlib` line:

```
msal>=1.0.0
```

- [ ] **Step 2: Install and verify**

Run: `pip install -r requirements.txt`
Expected: Successfully installs msal

- [ ] **Step 3: Verify import**

Run: `python3 -c "from msal import PublicClientApplication, SerializableTokenCache; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add msal dependency for Phase 3b Outlook"
```

---

## Task 2: Add `provider_type` and `close()` to EmailProvider protocol

**Files:**
- Modify: `src/quartermaster/email/provider.py`
- Modify: `src/quartermaster/email/gmail.py`
- Modify: `tests/email/test_gmail.py`

- [ ] **Step 1: Write failing tests for gmail provider_type and close**

Add to `tests/email/test_gmail.py`:

```python
def test_provider_type(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test",
        credential_file=credential_file,
    )
    assert provider.provider_type == "gmail"


@pytest.mark.asyncio
async def test_close_is_noop(credential_file: str) -> None:
    provider = GmailProvider(
        account_name="test",
        label="Test",
        credential_file=credential_file,
    )
    # Should not raise
    await provider.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/email/test_gmail.py::test_provider_type tests/email/test_gmail.py::test_close_is_noop -v`
Expected: FAIL — `provider_type` and `close` not defined

- [ ] **Step 3: Update the EmailProvider protocol**

In `src/quartermaster/email/provider.py`, add to the `EmailProvider` class:

```python
    @property
    def provider_type(self) -> str: ...

    async def close(self) -> None: ...
```

- [ ] **Step 4: Add provider_type and close() to GmailProvider**

In `src/quartermaster/email/gmail.py`, add to the `GmailProvider` class:

```python
    @property
    def provider_type(self) -> str:
        return "gmail"

    async def close(self) -> None:
        """No persistent connections to close for Gmail API."""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/email/test_gmail.py -v`
Expected: All pass (including 2 new tests)

- [ ] **Step 6: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/quartermaster/email/provider.py src/quartermaster/email/gmail.py tests/email/test_gmail.py
git commit -m "feat: add provider_type and close() to EmailProvider protocol"
```

---

## Task 3: Fix plugin health label and teardown

**Files:**
- Modify: `plugins/email/plugin.py`
- Modify: `tests/plugins/test_email_plugin.py`

- [ ] **Step 1: Write failing test for provider_type in health**

This test uses a mock with `provider_type = "outlook"` to prove the health method dynamically reads the property (the current code hard-codes `"gmail"` so this will fail before the fix).

Add to `tests/plugins/test_email_plugin.py` a new fixture and test:

```python
@pytest.fixture
def outlook_config() -> QuartermasterConfig:
    """Config with a single 'outlook' account for testing provider_type."""
    return QuartermasterConfig(
        email=EmailConfig(
            accounts={
                "fr-brian": EmailAccountConfig(
                    provider="outlook",
                    credential_file="credentials/outlook_brian.json",
                    label="FR Brian",
                ),
            }
        )
    )


@pytest.fixture
def outlook_ctx(outlook_config: QuartermasterConfig, mock_ctx: PluginContext) -> PluginContext:
    return PluginContext(
        config=outlook_config,
        events=mock_ctx.events,
        tools=ToolRegistry(events=mock_ctx.events),
    )


@pytest.mark.asyncio
async def test_health_reports_correct_provider_type(outlook_ctx: PluginContext) -> None:
    """health() should report 'outlook' for outlook providers, not hard-coded 'gmail'."""
    from plugins.email.plugin import EmailPlugin

    plugin = EmailPlugin()

    with patch("plugins.email.plugin.OutlookProvider") as MockOutlook:  # noqa: N806
        provider = AsyncMock()
        provider.account_name = "fr-brian"
        provider.label = "FR Brian"
        provider.provider_type = "outlook"
        provider.health_check = AsyncMock(return_value=True)
        MockOutlook.return_value = provider

        await plugin.setup(outlook_ctx)

    report = await plugin.health()
    assert report.details["fr-brian"]["provider"] == "outlook"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/plugins/test_email_plugin.py::test_health_reports_correct_provider_type -v`
Expected: FAIL — `report.details["fr-brian"]["provider"]` is `"gmail"` (hard-coded), not `"outlook"`

- [ ] **Step 3: Update `_providers` type annotation and instantiation**

In `plugins/email/plugin.py`, change the type annotation from `GmailProvider` to the protocol type. At the top, add:

```python
from quartermaster.email.provider import EmailProvider
```

Change in `__init__`:
```python
        self._providers: dict[str, EmailProvider] = {}
```

Change in `setup()` the instantiation line (around line 62) from:
```python
            provider: GmailProvider = provider_cls(
```
to:
```python
            provider = provider_cls(
```

- [ ] **Step 4: Fix health() to use provider.provider_type**

In `plugins/email/plugin.py`, in the `health()` method, change:

```python
                "provider": "gmail",
```

to:

```python
                "provider": provider.provider_type,
```

- [ ] **Step 5: Update existing health tests to set provider_type on mocks**

In `tests/plugins/test_email_plugin.py`, update `test_health_all_ok` and `test_health_degraded` — add `provider_type = "gmail"` to each mock provider (e.g., `provider1.provider_type = "gmail"` and `provider2.provider_type = "gmail"`). Without this, `AsyncMock` returns a mock object for `provider_type` instead of a string, and the assertion fails.

- [ ] **Step 6: Fix teardown() to call provider.close()**

In `plugins/email/plugin.py`, replace the `teardown()` method:

```python
    async def teardown(self) -> None:
        for provider in self._providers.values():
            with contextlib.suppress(Exception):
                await provider.close()
        self._providers.clear()
```

Note: OutlookProvider registration is deferred to Task 7 (after `outlook.py` exists). The `test_health_reports_correct_provider_type` test patches `OutlookProvider` directly so it doesn't need the real import.

- [ ] **Step 7: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add plugins/email/plugin.py tests/plugins/test_email_plugin.py
git commit -m "fix: plugin health uses provider_type, teardown calls close(), type annotations"
```

---

## Task 4: Outlook provider — connect and health_check

**Files:**
- Create: `src/quartermaster/email/outlook.py`
- Create: `tests/email/test_outlook.py`

- [ ] **Step 1: Write failing tests**

Create `tests/email/test_outlook.py`:

```python
"""Tests for Outlook provider."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quartermaster.email.outlook import OutlookProvider


@pytest.fixture
def credential_file(tmp_path):
    """Create a mock Outlook credential file with MSAL token cache."""
    # Minimal MSAL token cache with a refresh token
    cache_data = {
        "AccessToken": {},
        "RefreshToken": {
            "rt_key": {
                "secret": "mock-refresh-token",
                "credential_type": "RefreshToken",
                "home_account_id": "uid.utid",
                "environment": "login.microsoftonline.com",
                "client_id": "test-client-id",
            }
        },
        "Account": {
            "uid.utid-login.microsoftonline.com-uid": {
                "home_account_id": "uid.utid",
                "environment": "login.microsoftonline.com",
                "username": "brian@friendly-robots.com",
                "authority_type": "MSSTS",
                "local_account_id": "uid",
                "realm": "test-tenant-id",
            }
        },
        "IdToken": {},
        "AppMetadata": {},
    }
    cred_data = {
        "client_id": "test-client-id",
        "tenant_id": "test-tenant-id",
        "email_address": "brian@friendly-robots.com",
        "token_cache": json.dumps(cache_data),
    }
    path = tmp_path / "outlook_test.json"
    path.write_text(json.dumps(cred_data))
    return str(path)


@pytest.mark.asyncio
async def test_connect_acquires_token(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian",
        label="FR Brian",
        credential_file=credential_file,
    )
    with patch("quartermaster.email.outlook.PublicClientApplication") as mock_pca:
        mock_app = MagicMock()
        mock_pca.return_value = mock_app
        mock_app.get_accounts.return_value = [{"username": "brian@friendly-robots.com"}]
        mock_app.acquire_token_silent.return_value = {
            "access_token": "mock-access-token",
            "token_type": "Bearer",
        }

        await provider.connect()

        mock_app.acquire_token_silent.assert_called_once()
        assert provider._access_token == "mock-access-token"


@pytest.mark.asyncio
async def test_connect_persists_cache_on_refresh(credential_file: str) -> None:
    """If MSAL refreshes the token during connect, cache is persisted."""
    provider = OutlookProvider(
        account_name="fr-brian",
        label="FR Brian",
        credential_file=credential_file,
    )
    with patch("quartermaster.email.outlook.PublicClientApplication") as mock_pca:
        mock_app = MagicMock()
        mock_pca.return_value = mock_app
        mock_app.get_accounts.return_value = [{"username": "brian@friendly-robots.com"}]
        mock_app.acquire_token_silent.return_value = {
            "access_token": "refreshed-token",
            "token_type": "Bearer",
        }

        # Simulate cache state change (MSAL refreshed the token)
        mock_cache = MagicMock()
        mock_cache.has_state_changed = True
        mock_cache.serialize.return_value = '{"refreshed": true}'
        provider._cache = mock_cache

        with patch.object(provider, "_persist_cache") as mock_persist:
            await provider.connect()
            mock_persist.assert_called_once()


@pytest.mark.asyncio
async def test_connect_fails_no_accounts(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian",
        label="FR Brian",
        credential_file=credential_file,
    )
    with patch("quartermaster.email.outlook.PublicClientApplication") as mock_pca:
        mock_app = MagicMock()
        mock_pca.return_value = mock_app
        mock_app.get_accounts.return_value = []

        with pytest.raises(RuntimeError, match="No accounts found"):
            await provider.connect()


@pytest.mark.asyncio
async def test_health_check_true(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian",
        label="FR Brian",
        credential_file=credential_file,
    )
    provider._access_token = "mock-token"

    with patch.object(provider, "_http") as mock_http:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "inbox-id"}
        mock_http.get = AsyncMock(return_value=mock_response)

        result = await provider.health_check()
        assert result is True


@pytest.mark.asyncio
async def test_health_check_false_no_token(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian",
        label="FR Brian",
        credential_file=credential_file,
    )
    result = await provider.health_check()
    assert result is False


def test_properties(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian",
        label="FR Brian",
        credential_file=credential_file,
    )
    assert provider.account_name == "fr-brian"
    assert provider.label == "FR Brian"
    assert provider.provider_type == "outlook"


@pytest.mark.asyncio
async def test_close(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian",
        label="FR Brian",
        credential_file=credential_file,
    )
    provider._http = AsyncMock()
    provider._http.aclose = AsyncMock()
    await provider.close()
    provider._http.aclose.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/email/test_outlook.py -v`
Expected: FAIL — `OutlookProvider` not found

- [ ] **Step 3: Implement OutlookProvider — connect, health_check, close, properties**

Create `src/quartermaster/email/outlook.py`:

```python
"""Outlook provider — Microsoft Graph API client via MSAL + httpx."""

from __future__ import annotations

import asyncio
import json
import tempfile
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
import structlog
from msal import PublicClientApplication, SerializableTokenCache

from quartermaster.email.models import AttachmentInfo, EmailMessage, EmailSummary

logger = structlog.get_logger()

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPES = [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/User.Read",
    "offline_access",
]


class OutlookProvider:
    """Microsoft Graph email provider using MSAL for auth.

    MSAL handles token lifecycle via SerializableTokenCache.
    httpx.AsyncClient handles Graph API calls (natively async).
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
        self._access_token: str | None = None
        self._http: httpx.AsyncClient | None = None
        self._msal_app: PublicClientApplication | None = None
        self._cache: SerializableTokenCache | None = None
        self._client_id: str = ""
        self._tenant_id: str = ""
        self._email: str = ""

    @property
    def account_name(self) -> str:
        return self._account_name

    @property
    def label(self) -> str:
        return self._label

    @property
    def provider_type(self) -> str:
        return "outlook"

    async def connect(self) -> None:
        """Load credentials, acquire token via MSAL, create httpx client."""
        def _connect() -> str:
            cred_path = Path(self._credential_file)
            cred_data = json.loads(cred_path.read_text())
            self._client_id = cred_data["client_id"]
            self._tenant_id = cred_data["tenant_id"]
            self._email = cred_data.get("email_address", "")

            # Load MSAL token cache
            self._cache = SerializableTokenCache()
            token_cache_str = cred_data.get("token_cache", "")
            if token_cache_str:
                self._cache.deserialize(token_cache_str)

            authority = f"https://login.microsoftonline.com/{self._tenant_id}"
            self._msal_app = PublicClientApplication(
                client_id=self._client_id,
                authority=authority,
                token_cache=self._cache,
            )

            accounts = self._msal_app.get_accounts()
            if not accounts:
                raise RuntimeError(
                    f"No accounts found in MSAL cache for {self._account_name}. "
                    f"Run scripts/outlook_oauth_setup.py to authenticate."
                )

            result = self._msal_app.acquire_token_silent(
                scopes=GRAPH_SCOPES[:2],  # exclude offline_access for silent
                account=accounts[0],
            )
            if result is None or "access_token" not in result:
                error = (result or {}).get("error_description", "unknown error")
                raise RuntimeError(
                    f"Failed to acquire token for {self._account_name}: {error}"
                )

            # Persist cache if tokens were refreshed
            if self._cache.has_state_changed:
                self._persist_cache()

            return result["access_token"]

        self._access_token = await asyncio.to_thread(_connect)
        self._http = httpx.AsyncClient(
            base_url=GRAPH_BASE,
            headers={
                "Prefer": 'outlook.body-content-type="text"',
            },
            timeout=30.0,
        )
        logger.info(
            "outlook_provider_connected",
            account=self._account_name,
            email=self._email,
        )

    async def health_check(self) -> bool:
        """Check if Graph API is accessible."""
        if self._http is None or self._access_token is None:
            return False
        try:
            await self._refresh_token_if_needed()
            resp = await self._http.get(
                "/me/mailFolders/inbox", headers=self._auth_headers()
            )
            return resp.status_code == 200
        except Exception as exc:
            logger.warning(
                "outlook_health_check_failed",
                account=self._account_name,
                error=str(exc),
            )
            return False

    async def close(self) -> None:
        """Close the httpx client."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _refresh_token_if_needed(self) -> None:
        """Re-acquire token via MSAL if expired. Update httpx headers."""
        def _refresh() -> str | None:
            if self._msal_app is None:
                return None
            accounts = self._msal_app.get_accounts()
            if not accounts:
                return None
            result = self._msal_app.acquire_token_silent(
                scopes=GRAPH_SCOPES[:2],
                account=accounts[0],
            )
            if result and "access_token" in result:
                if self._cache and self._cache.has_state_changed:
                    self._persist_cache()
                return result["access_token"]
            return None

        new_token = await asyncio.to_thread(_refresh)
        if new_token:
            self._access_token = new_token

    def _auth_headers(self, **extra: str) -> dict[str, str]:
        """Build per-request auth headers. httpx client headers are immutable."""
        headers = {"Authorization": f"Bearer {self._access_token}"}
        headers.update(extra)
        return headers

    def _persist_cache(self) -> None:
        """Atomically write MSAL cache back to credential file.

        Rebuilds from instance vars — does not re-read the file,
        avoiding race conditions under concurrent requests.
        """
        cred_path = Path(self._credential_file)
        cred_data = {
            "client_id": self._client_id,
            "tenant_id": self._tenant_id,
            "email_address": self._email,
            "token_cache": self._cache.serialize(),
        }
        with tempfile.NamedTemporaryFile(
            mode="w", dir=cred_path.parent, suffix=".tmp", delete=False,
        ) as tmp:
            json.dump(cred_data, tmp, indent=2)
            tmp_path = Path(tmp.name)
        tmp_path.rename(cred_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/email/test_outlook.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Lint check**

Run: `ruff check src/quartermaster/email/outlook.py tests/email/test_outlook.py`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add src/quartermaster/email/outlook.py tests/email/test_outlook.py
git commit -m "feat: OutlookProvider — connect, health_check, close, token management"
```

---

## Task 5: Outlook provider — read operations

**Files:**
- Modify: `src/quartermaster/email/outlook.py`
- Modify: `tests/email/test_outlook.py`

- [ ] **Step 1: Write failing tests for read operations**

Add to `tests/email/test_outlook.py`:

```python
def _make_graph_message(
    msg_id: str = "AAMkAG1",
    subject: str = "Test Subject",
    sender: str = "sender@example.com",
    body: str = "Hello, world!",
    snippet: str = "Hello...",
    is_read: bool = False,
    conversation_id: str = "conv1",
) -> dict:
    """Build a mock Graph API message response."""
    return {
        "id": msg_id,
        "subject": subject,
        "from": {"emailAddress": {"name": "Sender", "address": sender}},
        "toRecipients": [{"emailAddress": {"name": "Me", "address": "me@example.com"}}],
        "ccRecipients": [],
        "receivedDateTime": "2026-03-27T10:00:00Z",
        "bodyPreview": snippet,
        "body": {"contentType": "text", "content": body},
        "isRead": is_read,
        "conversationId": conversation_id,
        "hasAttachments": False,
    }


@pytest.mark.asyncio
async def test_get_unread_summary(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian", label="FR Brian", credential_file=credential_file,
    )
    provider._access_token = "mock-token"

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "value": [
            _make_graph_message(msg_id="m1", subject="First", is_read=False),
            _make_graph_message(msg_id="m2", subject="Second", is_read=False),
        ]
    }

    with patch.object(provider, "_http") as mock_http:
        mock_http.get = AsyncMock(return_value=mock_response)
        with patch.object(provider, "_refresh_token_if_needed", new_callable=AsyncMock):
            result = await provider.get_unread_summary(max_results=5)

    assert len(result) == 2
    assert result[0].id == "m1"
    assert result[0].subject == "First"
    assert result[0].is_read is False


@pytest.mark.asyncio
async def test_search(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian", label="FR Brian", credential_file=credential_file,
    )
    provider._access_token = "mock-token"

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "value": [_make_graph_message(msg_id="m1", subject="Search Result")]
    }

    with patch.object(provider, "_http") as mock_http:
        mock_http.get = AsyncMock(return_value=mock_response)
        with patch.object(provider, "_refresh_token_if_needed", new_callable=AsyncMock):
            result = await provider.search("from:alice@example.com", max_results=5)

    assert len(result) == 1
    assert result[0].subject == "Search Result"

    # Verify ConsistencyLevel header was passed
    call_args = mock_http.get.call_args
    assert call_args.kwargs.get("headers", {}).get("ConsistencyLevel") == "eventual"


@pytest.mark.asyncio
async def test_read(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian", label="FR Brian", credential_file=credential_file,
    )
    provider._access_token = "mock-token"

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _make_graph_message(
        msg_id="m1", subject="Full Message", body="Full body text.",
    )

    with patch.object(provider, "_http") as mock_http:
        mock_http.get = AsyncMock(return_value=mock_response)
        with patch.object(provider, "_refresh_token_if_needed", new_callable=AsyncMock):
            result = await provider.read("m1")

    assert result.id == "m1"
    assert result.subject == "Full Message"
    assert result.body == "Full body text."
    assert result.thread_id == "conv1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/email/test_outlook.py::test_get_unread_summary tests/email/test_outlook.py::test_search tests/email/test_outlook.py::test_read -v`
Expected: FAIL — methods not implemented

- [ ] **Step 3: Implement read operations**

Add to `OutlookProvider` in `outlook.py`:

```python
    async def get_unread_summary(self, max_results: int = 20) -> list[EmailSummary]:
        """Get unread email summaries via Graph API."""
        await self._refresh_token_if_needed()
        resp = await self._http.get(
            "/me/messages",
            params={
                "$filter": "isRead eq false",
                "$top": max_results,
                "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
                "$orderby": "receivedDateTime desc",
            },
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        return [self._parse_summary(msg) for msg in data.get("value", [])]

    async def search(self, query: str, max_results: int = 10) -> list[EmailSummary]:
        """Search emails using Graph KQL search syntax."""
        await self._refresh_token_if_needed()
        resp = await self._http.get(
            "/me/messages",
            params={
                "$search": f'"{query}"',
                "$top": max_results,
            },
            headers=self._auth_headers(ConsistencyLevel="eventual"),
        )
        resp.raise_for_status()
        data = resp.json()
        return [self._parse_summary(msg) for msg in data.get("value", [])]

    async def read(self, message_id: str) -> EmailMessage:
        """Read a full email message."""
        await self._refresh_token_if_needed()
        resp = await self._http.get(
            f"/me/messages/{message_id}", headers=self._auth_headers()
        )
        resp.raise_for_status()
        return self._parse_message(resp.json())

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_summary(msg: dict[str, Any]) -> EmailSummary:
        return EmailSummary(
            id=msg["id"],
            subject=msg.get("subject", ""),
            sender=msg.get("from", {}).get("emailAddress", {}).get("address", ""),
            date=_parse_graph_datetime(msg.get("receivedDateTime")),
            snippet=msg.get("bodyPreview", ""),
            is_read=msg.get("isRead", True),
        )

    @staticmethod
    def _parse_message(msg: dict[str, Any]) -> EmailMessage:
        body_obj = msg.get("body", {})
        body_text = body_obj.get("content", "")
        if body_obj.get("contentType", "").lower() == "html":
            body_text = _strip_html(body_text)

        return EmailMessage(
            id=msg["id"],
            thread_id=msg.get("conversationId", ""),
            subject=msg.get("subject", ""),
            sender=msg.get("from", {}).get("emailAddress", {}).get("address", ""),
            to=[
                r.get("emailAddress", {}).get("address", "")
                for r in msg.get("toRecipients", [])
            ],
            cc=[
                r.get("emailAddress", {}).get("address", "")
                for r in msg.get("ccRecipients", [])
            ],
            date=_parse_graph_datetime(msg.get("receivedDateTime")),
            body=body_text,
            snippet=msg.get("bodyPreview", ""),
            is_read=msg.get("isRead", True),
            attachments=_parse_attachments(msg),
        )
```

Also add these module-level helpers at the bottom of the file:

```python
def _parse_graph_datetime(dt_str: str | None) -> datetime | None:
    """Parse Graph API ISO datetime string."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class _HTMLStripper(HTMLParser):
    """Minimal HTML tag stripper."""

    def __init__(self) -> None:
        super().__init__()
        self._result = StringIO()

    def handle_data(self, data: str) -> None:
        self._result.write(data)

    def get_text(self) -> str:
        return self._result.getvalue()


def _strip_html(html: str) -> str:
    """Strip HTML tags, returning plain text."""
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


def _parse_attachments(msg: dict[str, Any]) -> list[AttachmentInfo]:
    """Parse attachment metadata from Graph API message."""
    if not msg.get("hasAttachments"):
        return []
    attachments: list[AttachmentInfo] = []
    for att in msg.get("attachments", []):
        if att.get("name"):
            attachments.append(AttachmentInfo(
                filename=att["name"],
                mime_type=att.get("contentType", "application/octet-stream"),
                size=att.get("size", 0),
            ))
    return attachments
```

Add the `datetime` import at the top:
```python
from datetime import datetime
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/email/test_outlook.py -v`
Expected: 9 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/email/outlook.py tests/email/test_outlook.py
git commit -m "feat: OutlookProvider read operations — unread_summary, search, read"
```

---

## Task 6: Outlook provider — write operations

**Files:**
- Modify: `src/quartermaster/email/outlook.py`
- Modify: `tests/email/test_outlook.py`

- [ ] **Step 1: Write failing tests for write operations**

Add to `tests/email/test_outlook.py`:

```python
@pytest.mark.asyncio
async def test_send(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian", label="FR Brian", credential_file=credential_file,
    )
    provider._access_token = "mock-token"

    mock_response = AsyncMock()
    mock_response.status_code = 202  # Graph returns 202 for sendMail
    mock_response.json.return_value = {}

    with patch.object(provider, "_http") as mock_http:
        mock_http.post = AsyncMock(return_value=mock_response)
        with patch.object(provider, "_refresh_token_if_needed", new_callable=AsyncMock):
            result = await provider.send(
                to="recipient@example.com",
                subject="Test Email",
                body="This is a test.",
            )

    assert result["status"] == "sent"
    assert result["message_id"] == ""  # Graph sendMail returns no ID
    # Verify the sendMail endpoint was called
    mock_http.post.assert_called_once()
    call_args = mock_http.post.call_args
    assert "/me/sendMail" in call_args.args[0]


@pytest.mark.asyncio
async def test_send_with_cc(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian", label="FR Brian", credential_file=credential_file,
    )
    provider._access_token = "mock-token"

    mock_response = AsyncMock()
    mock_response.status_code = 202

    with patch.object(provider, "_http") as mock_http:
        mock_http.post = AsyncMock(return_value=mock_response)
        with patch.object(provider, "_refresh_token_if_needed", new_callable=AsyncMock):
            result = await provider.send(
                to="recipient@example.com",
                subject="CC Test",
                body="Testing CC.",
                cc="team@example.com",
            )

    assert result["status"] == "sent"
    # Verify CC was in the request body
    body = mock_http.post.call_args.kwargs.get("json", {})
    cc_list = body.get("message", {}).get("ccRecipients", [])
    assert len(cc_list) == 1


@pytest.mark.asyncio
async def test_draft(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian", label="FR Brian", credential_file=credential_file,
    )
    provider._access_token = "mock-token"

    mock_response = AsyncMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": "draft-123"}

    with patch.object(provider, "_http") as mock_http:
        mock_http.post = AsyncMock(return_value=mock_response)
        with patch.object(provider, "_refresh_token_if_needed", new_callable=AsyncMock):
            result = await provider.draft(
                to="recipient@example.com",
                subject="Draft Subject",
                body="Draft body.",
            )

    assert result["draft_id"] == "draft-123"
    assert result["status"] == "drafted"


@pytest.mark.asyncio
async def test_reply(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian", label="FR Brian", credential_file=credential_file,
    )
    provider._access_token = "mock-token"

    mock_response = AsyncMock()
    mock_response.status_code = 202

    with patch.object(provider, "_http") as mock_http:
        mock_http.post = AsyncMock(return_value=mock_response)
        with patch.object(provider, "_refresh_token_if_needed", new_callable=AsyncMock):
            result = await provider.reply(
                message_id="AAMkAG1",
                body="Thanks for the update!",
            )

    assert result["status"] == "sent"
    # Verify the reply endpoint was called
    call_args = mock_http.post.call_args
    assert "/me/messages/AAMkAG1/reply" in call_args.args[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/email/test_outlook.py::test_send tests/email/test_outlook.py::test_draft tests/email/test_outlook.py::test_reply -v`
Expected: FAIL — methods not implemented

- [ ] **Step 3: Implement write operations**

Add to `OutlookProvider` in `outlook.py`:

```python
    async def send(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> dict[str, str]:
        """Send an email via Graph API."""
        await self._refresh_token_if_needed()
        message = self._build_message(to=to, subject=subject, body=body, cc=cc)
        resp = await self._http.post(
            "/me/sendMail",
            json={"message": message, "saveToSentItems": True},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        logger.info(
            "outlook_message_sent",
            account=self._account_name,
            to=to,
            subject=subject,
        )
        # Graph sendMail returns 202 with no body — no message_id available
        return {"message_id": "", "status": "sent"}

    async def draft(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> dict[str, str]:
        """Create a draft email via Graph API."""
        await self._refresh_token_if_needed()
        message = self._build_message(to=to, subject=subject, body=body, cc=cc)
        resp = await self._http.post(
            "/me/messages", json=message, headers=self._auth_headers()
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(
            "outlook_draft_created",
            account=self._account_name,
            to=to,
            subject=subject,
        )
        return {"draft_id": data.get("id", ""), "status": "drafted"}

    async def reply(self, message_id: str, body: str) -> dict[str, str]:
        """Reply to an email via Graph API."""
        await self._refresh_token_if_needed()
        resp = await self._http.post(
            f"/me/messages/{message_id}/reply",
            json={"comment": body},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        logger.info(
            "outlook_reply_sent",
            account=self._account_name,
            message_id=message_id,
        )
        return {"status": "sent"}

    @staticmethod
    def _build_message(
        to: str, subject: str, body: str, cc: str | None = None,
    ) -> dict[str, Any]:
        """Build a Graph API message object."""
        message: dict[str, Any] = {
            "subject": subject,
            "body": {"contentType": "text", "content": body},
            "toRecipients": [
                {"emailAddress": {"address": to}}
            ],
        }
        if cc:
            message["ccRecipients"] = [
                {"emailAddress": {"address": addr.strip()}}
                for addr in cc.split(",")
            ]
        return message
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/email/test_outlook.py -v`
Expected: 13 PASSED

- [ ] **Step 5: Lint check**

Run: `ruff check src/quartermaster/email/outlook.py tests/email/test_outlook.py`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add src/quartermaster/email/outlook.py tests/email/test_outlook.py
git commit -m "feat: OutlookProvider write operations — send, draft, reply"
```

---

## Task 7: Wire plugin, update config, add mixed-provider test

**Files:**
- Modify: `plugins/email/plugin.py` (finalize import)
- Modify: `config/settings.example.yaml`
- Modify: `tests/plugins/test_email_plugin.py`

- [ ] **Step 1: Finalize OutlookProvider import in plugin**

If Task 3 used the conditional import pattern, replace it with the direct import now that `outlook.py` exists:

```python
from quartermaster.email.outlook import OutlookProvider

mapping: dict[str, type] = {
    "gmail": GmailProvider,
    "outlook": OutlookProvider,
}
```

- [ ] **Step 2: Update settings.example.yaml**

Add Outlook account examples in the `email.accounts` section:

```yaml
    # fr-brian:
    #   provider: outlook
    #   credential_file: "credentials/outlook_brian.json"
    #   label: "FR Brian"
    # fr-support:
    #   provider: outlook
    #   credential_file: "credentials/outlook_support.json"
    #   label: "FR Support"
```

- [ ] **Step 3: Add mixed-provider routing test**

Add to `tests/plugins/test_email_plugin.py`:

```python
@pytest.mark.asyncio
async def test_mixed_providers_route_correctly(mock_ctx: PluginContext) -> None:
    """Plugin routes to correct provider when mixing gmail + outlook."""
    from plugins.email.plugin import EmailPlugin
    from quartermaster.email.models import EmailSummary

    plugin = EmailPlugin()

    gmail_summaries = [
        EmailSummary(id="g1", subject="Gmail", sender="a@gmail.com", date=None, snippet="...", is_read=False),
    ]
    outlook_summaries = [
        EmailSummary(id="o1", subject="Outlook", sender="b@outlook.com", date=None, snippet="...", is_read=False),
    ]

    # Need config with both provider types
    mixed_config = QuartermasterConfig(
        email=EmailConfig(
            accounts={
                "personal": EmailAccountConfig(
                    provider="gmail",
                    credential_file="credentials/gmail.json",
                    label="Personal Gmail",
                ),
                "fr-brian": EmailAccountConfig(
                    provider="outlook",
                    credential_file="credentials/outlook.json",
                    label="FR Brian",
                ),
            }
        )
    )
    mixed_ctx = PluginContext(
        config=mixed_config,
        events=mock_ctx.events,
        tools=ToolRegistry(events=mock_ctx.events),
    )

    with patch("plugins.email.plugin.GmailProvider") as MockGmail, \
         patch("plugins.email.plugin.OutlookProvider") as MockOutlook:  # noqa: N806
        gmail_provider = AsyncMock()
        gmail_provider.account_name = "personal"
        gmail_provider.label = "Personal Gmail"
        gmail_provider.provider_type = "gmail"
        gmail_provider.health_check = AsyncMock(return_value=True)
        gmail_provider.get_unread_summary = AsyncMock(return_value=gmail_summaries)
        MockGmail.return_value = gmail_provider

        outlook_provider = AsyncMock()
        outlook_provider.account_name = "fr-brian"
        outlook_provider.label = "FR Brian"
        outlook_provider.provider_type = "outlook"
        outlook_provider.health_check = AsyncMock(return_value=True)
        outlook_provider.get_unread_summary = AsyncMock(return_value=outlook_summaries)
        MockOutlook.return_value = outlook_provider

        await plugin.setup(mixed_ctx)

    # Aggregate all accounts
    result = await mixed_ctx.tools.execute("email.unread_summary", {})
    assert "accounts" in result
    assert len(result["accounts"]) == 2

    # Health should show correct provider types
    report = await plugin.health()
    assert report.details["personal"]["provider"] == "gmail"
    assert report.details["fr-brian"]["provider"] == "outlook"
```

- [ ] **Step 4: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All pass

- [ ] **Step 5: Lint check**

Run: `ruff check src/ plugins/ tests/`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add plugins/email/plugin.py config/settings.example.yaml tests/plugins/test_email_plugin.py
git commit -m "feat: wire OutlookProvider into plugin, add mixed-provider test"
```

---

## Task 8: OAuth setup script

**Files:**
- Create: `scripts/outlook_oauth_setup.py`

- [ ] **Step 1: Create the setup script**

```python
"""
One-time Outlook OAuth2 setup script for Quartermaster.

Uses MSAL device code flow — works on headless servers.

Pre-requisites:
  1. Register an app in Entra ID (https://entra.microsoft.com)
  2. Set as Public client with redirect URI http://localhost
  3. Add API permissions: Mail.ReadWrite, User.Read, offline_access
  4. Enable "Allow public client flows"
  5. Note the Application (client) ID and Directory (tenant) ID

Usage:
  python scripts/outlook_oauth_setup.py \\
    --client-id <app-client-id> \\
    --tenant-id <tenant-id> \\
    --account-name fr-brian
"""

import argparse
import json
import sys
from pathlib import Path

from msal import PublicClientApplication, SerializableTokenCache

SCOPES = [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/User.Read",
    "offline_access",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Outlook OAuth2 setup for Quartermaster (device code flow)"
    )
    parser.add_argument("--client-id", required=True, help="Entra app client ID")
    parser.add_argument("--tenant-id", required=True, help="Entra directory tenant ID")
    parser.add_argument("--account-name", required=True, help="Account name (e.g. 'fr-brian')")
    args = parser.parse_args()

    cache = SerializableTokenCache()
    authority = f"https://login.microsoftonline.com/{args.tenant_id}"
    app = PublicClientApplication(
        client_id=args.client_id,
        authority=authority,
        token_cache=cache,
    )

    # Initiate device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        print(f"Error initiating device flow: {flow.get('error_description', 'unknown')}")
        sys.exit(1)

    print(f"\nTo sign in, open: {flow['verification_uri']}")
    print(f"Enter code: {flow['user_code']}")
    print("Waiting for authentication...\n")

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        print(f"Authentication failed: {result.get('error_description', 'unknown')}")
        sys.exit(1)

    # Get email address from token claims or /me endpoint
    import httpx
    resp = httpx.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {result['access_token']}"},
    )
    email_address = ""
    if resp.status_code == 200:
        user_data = resp.json()
        email_address = user_data.get("mail") or user_data.get("userPrincipalName", "")

    # Save credentials
    project_root = Path(__file__).parent.parent
    output_path = project_root / f"credentials/outlook_{args.account_name}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cred_data = {
        "client_id": args.client_id,
        "tenant_id": args.tenant_id,
        "email_address": email_address,
        "token_cache": cache.serialize(),
    }
    output_path.write_text(json.dumps(cred_data, indent=2))

    print(f"--- Outlook OAuth2 Setup Complete ---")
    print(f"Account: {args.account_name}")
    print(f"Email: {email_address}")
    print(f"Credentials saved to: {output_path}")
    print(f"\nAdd this to your config/settings.yaml:")
    print(f"  {args.account_name}:")
    print(f'    provider: outlook')
    print(f'    credential_file: "{output_path}"')
    print(f'    label: "Your Label Here"')


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('scripts/outlook_oauth_setup.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/outlook_oauth_setup.py
git commit -m "feat: Outlook OAuth setup script (device code flow)"
```

---

## Task 9: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All pass

- [ ] **Step 2: Run lint**

Run: `ruff check src/ plugins/ tests/`
Expected: All checks passed

- [ ] **Step 3: Verify app starts with empty Outlook config**

Add to `config/settings.yaml` (temporarily):

```yaml
      fr-brian:
        provider: outlook
        credential_file: "credentials/outlook_brian.json"
        label: "FR Brian"
```

Run: `timeout 10 python -m quartermaster 2>&1 | head -25`
Expected: App boots, email plugin shows `fr-brian` as unhealthy (credential file doesn't exist yet), other accounts work normally. Then remove the temporary config entry.

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "chore: Phase 3b final verification — all tests passing"
```

---

*Implementation plan for Phase 3b Outlook Integration, March 27, 2026.*
