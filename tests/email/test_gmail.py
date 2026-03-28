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
    await provider.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gmail_message(
    msg_id: str = "msg1",
    thread_id: str = "thread1",
    subject: str = "Test Subject",
    sender: str = "sender@example.com",
    to: str = "recipient@example.com",
    body_text: str = "Hello world",
    snippet: str = "Hello world",
    label_ids: list[str] | None = None,
    date_str: str = "Mon, 27 Mar 2026 10:00:00 +0000",
) -> dict:
    """Build a minimal mock Gmail API full-message response."""
    if label_ids is None:
        label_ids = ["INBOX"]
    import base64

    encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()
    return {
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": label_ids,
        "snippet": snippet,
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "To", "value": to},
                {"name": "Date", "value": date_str},
            ],
            "mimeType": "text/plain",
            "body": {"data": encoded_body, "size": len(body_text)},
            "parts": [],
        },
    }


# ---------------------------------------------------------------------------
# Task 6: Read operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_unread_summary(credential_file: str) -> None:
    """get_unread_summary returns EmailSummary list; is_read=False for UNREAD messages."""
    provider = GmailProvider(
        account_name="test",
        label="Test Account",
        credential_file=credential_file,
    )
    provider._service = MagicMock()

    raw_msg = _make_gmail_message(
        msg_id="abc123",
        subject="Unread Email",
        sender="alice@example.com",
        label_ids=["INBOX", "UNREAD"],
    )

    # list returns just ids; get returns full message
    svc_msgs = provider._service.users.return_value.messages.return_value
    svc_msgs.list.return_value.execute.return_value = {"messages": [{"id": "abc123"}]}
    svc_msgs.get.return_value.execute.return_value = raw_msg

    summaries = await provider.get_unread_summary(max_results=5)

    assert len(summaries) == 1
    s = summaries[0]
    assert s.id == "abc123"
    assert s.subject == "Unread Email"
    assert s.sender == "alice@example.com"
    assert s.is_read is False

    # Verify query and maxResults were passed correctly
    svc_msgs.list.assert_called_once_with(
        userId="me", q="is:unread", maxResults=5
    )


@pytest.mark.asyncio
async def test_search(credential_file: str) -> None:
    """search passes the query to Gmail API and returns EmailSummary list."""
    provider = GmailProvider(
        account_name="test",
        label="Test Account",
        credential_file=credential_file,
    )
    provider._service = MagicMock()

    raw_msg = _make_gmail_message(msg_id="xyz789", subject="Found It")

    svc_msgs = provider._service.users.return_value.messages.return_value
    svc_msgs.list.return_value.execute.return_value = {"messages": [{"id": "xyz789"}]}
    svc_msgs.get.return_value.execute.return_value = raw_msg

    summaries = await provider.search("from:alice@example.com", max_results=3)

    assert len(summaries) == 1
    assert summaries[0].id == "xyz789"
    assert summaries[0].subject == "Found It"

    svc_msgs.list.assert_called_once_with(
        userId="me", q="from:alice@example.com", maxResults=3
    )


@pytest.mark.asyncio
async def test_read(credential_file: str) -> None:
    """read returns a full EmailMessage with body, thread_id, to, etc."""
    provider = GmailProvider(
        account_name="test",
        label="Test Account",
        credential_file=credential_file,
    )
    provider._service = MagicMock()

    raw_msg = _make_gmail_message(
        msg_id="full1",
        thread_id="thread99",
        subject="Full Message",
        sender="bob@example.com",
        to="me@example.com",
        body_text="This is the body text.",
        snippet="This is the body",
        label_ids=["INBOX"],
    )

    svc_msgs = provider._service.users.return_value.messages.return_value
    svc_msgs.get.return_value.execute.return_value = raw_msg

    msg = await provider.read("full1")

    assert msg.id == "full1"
    assert msg.thread_id == "thread99"
    assert msg.subject == "Full Message"
    assert msg.sender == "bob@example.com"
    assert "me@example.com" in msg.to
    assert msg.body == "This is the body text."
    assert msg.snippet == "This is the body"
    assert msg.is_read is True  # no UNREAD label

    svc_msgs.get.assert_called_once_with(
        userId="me", id="full1", format="full"
    )


# ---------------------------------------------------------------------------
# Task 7: Write operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send(credential_file: str) -> None:
    """send builds MIME message, calls messages.send, returns message_id and status."""
    provider = GmailProvider(
        account_name="test",
        label="Test Account",
        credential_file=credential_file,
    )
    provider._service = MagicMock()

    svc_msgs = provider._service.users.return_value.messages.return_value
    svc_msgs.send.return_value.execute.return_value = {
        "id": "sent_msg_001",
        "threadId": "thread_sent_001",
        "labelIds": ["SENT"],
    }

    result = await provider.send(
        to="bob@example.com",
        subject="Hello Bob",
        body="Hi there!",
    )

    assert result["message_id"] == "sent_msg_001"
    assert result["status"] == "sent"

    svc_msgs.send.assert_called_once()
    call_kwargs = svc_msgs.send.call_args
    assert call_kwargs.kwargs["userId"] == "me"
    assert "raw" in call_kwargs.kwargs["body"]


@pytest.mark.asyncio
async def test_send_with_cc(credential_file: str) -> None:
    """send with cc includes CC header in the MIME message."""
    provider = GmailProvider(
        account_name="test",
        label="Test Account",
        credential_file=credential_file,
    )
    provider._service = MagicMock()

    svc_msgs = provider._service.users.return_value.messages.return_value
    svc_msgs.send.return_value.execute.return_value = {
        "id": "sent_cc_001",
        "threadId": "thread_cc_001",
        "labelIds": ["SENT"],
    }

    result = await provider.send(
        to="bob@example.com",
        subject="CC Test",
        body="CC me in",
        cc="carol@example.com",
    )

    assert result["message_id"] == "sent_cc_001"
    assert result["status"] == "sent"

    # Verify the raw MIME contains a Cc header
    import base64

    call_kwargs = svc_msgs.send.call_args
    raw = call_kwargs.kwargs["body"]["raw"]
    decoded = base64.urlsafe_b64decode(raw + "==").decode()
    assert "carol@example.com" in decoded


@pytest.mark.asyncio
async def test_draft(credential_file: str) -> None:
    """draft calls drafts.create, returns draft_id and status."""
    provider = GmailProvider(
        account_name="test",
        label="Test Account",
        credential_file=credential_file,
    )
    provider._service = MagicMock()

    svc_drafts = provider._service.users.return_value.drafts.return_value
    svc_drafts.create.return_value.execute.return_value = {
        "id": "draft_001",
        "message": {"id": "draft_msg_001", "threadId": "thread_draft_001"},
    }

    result = await provider.draft(
        to="charlie@example.com",
        subject="Draft Test",
        body="Draft body text",
    )

    assert result["draft_id"] == "draft_001"
    assert result["status"] == "drafted"

    svc_drafts.create.assert_called_once()
    call_kwargs = svc_drafts.create.call_args
    assert call_kwargs.kwargs["userId"] == "me"
    assert "raw" in call_kwargs.kwargs["body"]["message"]


@pytest.mark.asyncio
async def test_reply(credential_file: str) -> None:
    """reply reads original, builds reply with In-Reply-To, sends in same thread."""
    provider = GmailProvider(
        account_name="test",
        label="Test Account",
        credential_file=credential_file,
    )
    provider._service = MagicMock()

    original = _make_gmail_message(
        msg_id="orig_001",
        thread_id="thread_reply_001",
        subject="Original Subject",
        sender="alice@example.com",
        to="me@example.com",
        label_ids=["INBOX"],
    )
    # Add Message-ID header to original
    original["payload"]["headers"].append(
        {"name": "Message-ID", "value": "<orig_message_id@example.com>"}
    )

    svc_msgs = provider._service.users.return_value.messages.return_value
    svc_msgs.get.return_value.execute.return_value = original
    svc_msgs.send.return_value.execute.return_value = {
        "id": "reply_sent_001",
        "threadId": "thread_reply_001",
        "labelIds": ["SENT"],
    }

    result = await provider.reply(
        message_id="orig_001",
        body="Thanks for your message!",
    )

    assert result["message_id"] == "reply_sent_001"
    assert result["status"] == "sent"

    # Verify thread_id was used in the send call
    send_call = svc_msgs.send.call_args
    assert send_call.kwargs["body"].get("threadId") == "thread_reply_001"

    # Verify In-Reply-To header in the MIME message
    import base64

    raw = send_call.kwargs["body"]["raw"]
    decoded = base64.urlsafe_b64decode(raw + "==").decode()
    assert "In-Reply-To" in decoded
    assert "<orig_message_id@example.com>" in decoded
