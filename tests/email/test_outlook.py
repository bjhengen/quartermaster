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


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Build a sync-compatible mock httpx response.

    raise_for_status() and json() are sync in httpx, so use MagicMock (not
    AsyncMock) to avoid 'coroutine never awaited' warnings.
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data or {})
    return resp


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

    mock_cache = MagicMock()
    mock_cache.has_state_changed = True
    mock_cache.serialize.return_value = '{"refreshed": true}'

    with (
        patch("quartermaster.email.outlook.PublicClientApplication") as mock_pca,
        patch("quartermaster.email.outlook.SerializableTokenCache", return_value=mock_cache),
        patch.object(provider, "_persist_cache") as mock_persist,
    ):
        mock_app = MagicMock()
        mock_pca.return_value = mock_app
        mock_app.get_accounts.return_value = [{"username": "brian@friendly-robots.com"}]
        mock_app.acquire_token_silent.return_value = {
            "access_token": "refreshed-token",
            "token_type": "Bearer",
        }

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
        mock_http.get = AsyncMock(return_value=_mock_response(200, {"id": "inbox-id"}))
        with patch.object(provider, "_refresh_token_if_needed", new_callable=AsyncMock):
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
    mock_http = AsyncMock()
    mock_http.aclose = AsyncMock()
    provider._http = mock_http
    await provider.close()
    mock_http.aclose.assert_awaited_once()


# ------------------------------------------------------------------
# Read operations (Task 5)
# ------------------------------------------------------------------


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
        account_name="fr-brian",
        label="FR Brian",
        credential_file=credential_file,
    )
    provider._access_token = "mock-token"

    resp_data = {
        "value": [
            _make_graph_message(msg_id="m1", subject="First", is_read=False),
            _make_graph_message(msg_id="m2", subject="Second", is_read=False),
        ]
    }

    with patch.object(provider, "_http") as mock_http:
        mock_http.get = AsyncMock(return_value=_mock_response(200, resp_data))
        with patch.object(provider, "_refresh_token_if_needed", new_callable=AsyncMock):
            result = await provider.get_unread_summary(max_results=5)

    assert len(result) == 2
    assert result[0].id == "m1"
    assert result[0].subject == "First"
    assert result[0].is_read is False


@pytest.mark.asyncio
async def test_search(credential_file: str) -> None:
    provider = OutlookProvider(
        account_name="fr-brian",
        label="FR Brian",
        credential_file=credential_file,
    )
    provider._access_token = "mock-token"

    resp_data = {"value": [_make_graph_message(msg_id="m1", subject="Search Result")]}

    with patch.object(provider, "_http") as mock_http:
        mock_http.get = AsyncMock(return_value=_mock_response(200, resp_data))
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
        account_name="fr-brian",
        label="FR Brian",
        credential_file=credential_file,
    )
    provider._access_token = "mock-token"

    resp_data = _make_graph_message(
        msg_id="m1",
        subject="Full Message",
        body="Full body text.",
    )

    with patch.object(provider, "_http") as mock_http:
        mock_http.get = AsyncMock(return_value=_mock_response(200, resp_data))
        with patch.object(provider, "_refresh_token_if_needed", new_callable=AsyncMock):
            result = await provider.read("m1")

    assert result.id == "m1"
    assert result.subject == "Full Message"
    assert result.body == "Full body text."
    assert result.thread_id == "conv1"
