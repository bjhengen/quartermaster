"""Conversation history and context window management."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

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
        cutoff = datetime.now(UTC) - timedelta(
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

        await self._db.execute(
            """UPDATE qm.conversations
               SET last_active_at = systimestamp
               WHERE conversation_id = :conv_id""",
            {"conv_id": conv.conversation_id},
        )

    async def force_new_conversation(self, transport: str, chat_id: str) -> None:
        """Force the next message to start a new conversation."""
        await self._db.execute(
            """UPDATE qm.conversations
               SET last_active_at = systimestamp - NUMTODSINTERVAL(:hours, 'HOUR')
               WHERE transport = :transport
                 AND external_chat_id = :chat_id
                 AND last_active_at > systimestamp - NUMTODSINTERVAL(:hours2, 'HOUR')""",
            {
                "hours": self._config.idle_timeout_hours + 1,
                "transport": transport,
                "chat_id": chat_id,
                "hours2": self._config.idle_timeout_hours,
            },
        )

    async def get_context_window(self, conv: Conversation) -> list[ChatMessage]:
        """Load recent turns and build the context window."""
        # Subquery fetches the N most recent turns (DESC), outer query returns
        # them in chronological order (ASC) for LLM context assembly.
        raw_rows = await self._db.fetch_all(
            """SELECT turn_id, role, content, tool_calls, tool_results,
                      llm_backend, tokens_in, tokens_out
               FROM (
                   SELECT turn_id, role, content, tool_calls, tool_results,
                          llm_backend, tokens_in, tokens_out, created_at
                   FROM qm.turns
                   WHERE conversation_id = :conv_id
                   ORDER BY created_at DESC
                   FETCH FIRST :max_turns ROWS ONLY
               )
               ORDER BY created_at ASC""",
            {
                "conv_id": conv.conversation_id,
                "max_turns": self._config.context_window_max_turns,
            },
        )

        rows = list(raw_rows)

        messages: list[ChatMessage] = []
        total_tokens = 0
        max_tokens = self._config.context_window_max_tokens

        for row in rows:
            role = row[1]
            content = row[2]
            tool_calls_raw = row[3]

            msg = ChatMessage(role=role, content=content)
            if tool_calls_raw:
                parsed = (
                    json.loads(tool_calls_raw)
                    if isinstance(tool_calls_raw, str)
                    else tool_calls_raw
                )
                msg.tool_calls = parsed

            msg_text = (content or "") + str(tool_calls_raw or "")
            estimated_tokens = len(msg_text) // 4
            total_tokens += estimated_tokens
            messages.append(msg)

        while total_tokens > max_tokens and len(messages) > 1:
            removed = messages.pop(0)
            removed_text = (removed.content or "") + str(removed.tool_calls or "")
            total_tokens -= len(removed_text) // 4

        return messages
