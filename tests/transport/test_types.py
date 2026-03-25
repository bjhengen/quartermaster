"""Tests for transport types."""

from quartermaster.transport.types import (
    InboundMessage,
    OutboundMessage,
    TransportType,
)


def test_inbound_message() -> None:
    msg = InboundMessage(
        transport=TransportType.TELEGRAM,
        chat_id="12345",
        user_id="67890",
        text="hello",
    )
    assert msg.transport == TransportType.TELEGRAM
    assert msg.text == "hello"


def test_outbound_message() -> None:
    msg = OutboundMessage(
        transport=TransportType.TELEGRAM,
        chat_id="12345",
        text="response",
    )
    assert msg.text == "response"


def test_outbound_message_with_inline_keyboard() -> None:
    msg = OutboundMessage(
        transport=TransportType.TELEGRAM,
        chat_id="12345",
        text="Approve?",
        inline_keyboard=[
            [{"text": "Yes", "callback_data": "approve:123"}],
            [{"text": "No", "callback_data": "reject:123"}],
        ],
    )
    assert len(msg.inline_keyboard) == 2
