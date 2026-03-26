"""Telegram transport using python-telegram-bot."""

from typing import Any

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from quartermaster.core.events import EventBus
from quartermaster.transport.types import InboundMessage, OutboundMessage, TransportType

logger = structlog.get_logger()


class TelegramTransport:
    """Telegram bot transport via long-polling."""

    transport_type = TransportType.TELEGRAM

    def __init__(
        self,
        bot_token: str,
        allowed_user_ids: list[int],
        events: EventBus,
    ) -> None:
        self._bot_token = bot_token
        self._allowed_user_ids = set(allowed_user_ids)
        self._events = events
        self._app: Application | None = None

    async def start(self) -> None:
        """Initialize and start the Telegram bot."""
        self._app = Application.builder().token(self._bot_token).build()

        self._app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._handle_message,
            )
        )
        self._app.add_handler(
            CommandHandler("start", self._handle_command)
        )
        self._app.add_handler(
            MessageHandler(filters.COMMAND, self._handle_command)
        )
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))

        await self._app.initialize()
        await self._app.start()
        if self._app.updater is not None:
            await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("telegram_started")

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._app:
            if self._app.updater is not None:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("telegram_stopped")

    async def send(self, message: OutboundMessage) -> str:
        """Send a message via Telegram."""
        assert self._app is not None
        bot = self._app.bot

        kwargs: dict[str, Any] = {
            "chat_id": int(message.chat_id),
            "text": message.text,
        }

        if message.reply_to_message_id:
            kwargs["reply_to_message_id"] = int(message.reply_to_message_id)

        if message.inline_keyboard:
            buttons = [
                [
                    InlineKeyboardButton(
                        text=btn["text"], callback_data=btn["callback_data"]
                    )
                    for btn in row
                ]
                for row in message.inline_keyboard
            ]
            kwargs["reply_markup"] = InlineKeyboardMarkup(buttons)

        sent = await bot.send_message(**kwargs)

        if message.voice_data:
            await bot.send_voice(
                chat_id=int(message.chat_id),
                voice=message.voice_data,
            )

        return str(sent.message_id)

    def _is_allowed(self, user_id: int) -> bool:
        """Check if a user is in the allowlist."""
        return user_id in self._allowed_user_ids

    async def _handle_message(self, update: Update, context: Any) -> None:
        """Handle incoming text messages."""
        logger.info(
            "telegram_update_received",
            user_id=update.effective_user.id if update.effective_user else None,
            text=(
                update.effective_message.text[:50]
                if update.effective_message and update.effective_message.text
                else None
            ),
        )
        if not update.effective_user or not update.effective_message:
            return
        if not self._is_allowed(update.effective_user.id):
            logger.warning("telegram_user_not_allowed", user_id=update.effective_user.id)
            return

        assert update.effective_chat is not None
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing",
        )

        inbound = InboundMessage(
            transport=TransportType.TELEGRAM,
            chat_id=str(update.effective_chat.id),
            user_id=str(update.effective_user.id),
            text=update.effective_message.text or "",
            message_id=str(update.effective_message.message_id),
        )

        await self._events.emit("message.received", {"message": inbound})

    async def _handle_command(self, update: Update, context: Any) -> None:
        """Handle incoming commands (forward as messages)."""
        await self._handle_message(update, context)

    async def _handle_callback(self, update: Update, context: Any) -> None:
        """Handle inline keyboard callbacks (approval flow)."""
        query = update.callback_query
        if not query or not query.from_user:
            return
        if not self._is_allowed(query.from_user.id):
            return

        await query.answer()
        await self._events.emit(
            "approval.callback",
            {
                "callback_data": query.data,
                "message_id": str(query.message.message_id) if query.message else "",
                "chat_id": str(query.message.chat.id) if query.message else "",
                "user_id": str(query.from_user.id),
            },
        )
