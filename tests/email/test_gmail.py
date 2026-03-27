"""Tests for Gmail provider."""

import json
from unittest.mock import MagicMock, patch

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
