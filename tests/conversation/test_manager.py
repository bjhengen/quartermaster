"""Tests for conversation management."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from quartermaster.conversation.manager import ConversationManager
from quartermaster.conversation.models import Conversation
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
    mock_db.execute.assert_awaited()


@pytest.mark.asyncio
async def test_save_and_get_context_window(
    mock_db: MagicMock,
    config: ConversationConfig,
) -> None:
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
