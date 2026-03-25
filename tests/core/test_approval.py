"""Tests for the approval manager."""

from unittest.mock import AsyncMock, MagicMock

import pytest

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
    mock_db.fetch_one = AsyncMock(return_value=(
        b"\x01" * 16,
        "social",
        "social.post",
        "Draft tweet",
        '{"text": "hello"}',
        "pending",
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
