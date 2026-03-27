"""Tests for the Anthropic API client."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quartermaster.llm.anthropic_client import AnthropicClient
from quartermaster.llm.models import ChatMessage, LLMRequest


@pytest.mark.asyncio
async def test_chat_returns_response() -> None:
    """Test that chat converts between our types and Anthropic SDK."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(type="text", text="Hello!")]
    mock_message.model = "claude-sonnet-4-20250514"
    mock_message.usage.input_tokens = 10
    mock_message.usage.output_tokens = 20
    mock_message.stop_reason = "end_turn"

    with patch("quartermaster.llm.anthropic_client.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)
        mock_cls.return_value = mock_client

        client = AnthropicClient(api_key="test-key", default_model="claude-sonnet-4-20250514")
        request = LLMRequest(
            messages=[ChatMessage(role="user", content="Hi")],
        )
        response = await client.chat(request)
        assert response.content == "Hello!"
        assert response.tokens_in == 10
        assert response.tokens_out == 20


@pytest.mark.asyncio
async def test_anthropic_converts_tools_to_anthropic_format() -> None:
    """Test that OpenAI-format tools are converted to Anthropic format."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(type="text", text="ok")]
    mock_message.model = "claude-sonnet-4-20250514"
    mock_message.usage.input_tokens = 5
    mock_message.usage.output_tokens = 5
    mock_message.stop_reason = "end_turn"

    with patch("quartermaster.llm.anthropic_client.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)
        mock_cls.return_value = mock_client

        client = AnthropicClient(api_key="test-key")
        request = LLMRequest(
            messages=[ChatMessage(role="user", content="test")],
            tools=[{
                "type": "function",
                "function": {
                    "name": "test.tool",
                    "description": "A test",
                    "parameters": {"type": "object", "properties": {}},
                },
            }],
        )
        await client.chat(request)

        # Verify Anthropic format was used in the call
        call_kwargs = mock_client.messages.create.call_args
        tools = call_kwargs.kwargs.get("tools", [])
        assert tools[0]["name"] == "test.tool"
        assert "input_schema" in tools[0]


def test_convert_messages_extracts_system() -> None:
    """System messages become a separate string."""
    messages = [
        ChatMessage(role="system", content="You are helpful."),
        ChatMessage(role="user", content="Hi"),
    ]
    system, converted = AnthropicClient._convert_messages(messages)
    assert system == "You are helpful."
    assert len(converted) == 1
    assert converted[0]["role"] == "user"


def test_convert_messages_tool_call_format() -> None:
    """Assistant tool calls become content blocks with type=tool_use."""
    messages = [
        ChatMessage(role="user", content="check email"),
        ChatMessage(
            role="assistant",
            tool_calls=[{
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "email.unread_summary",
                    "arguments": "{}",
                },
            }],
        ),
    ]
    _, converted = AnthropicClient._convert_messages(messages)
    assert len(converted) == 2

    assistant_msg = converted[1]
    assert assistant_msg["role"] == "assistant"
    assert isinstance(assistant_msg["content"], list)
    assert assistant_msg["content"][0]["type"] == "tool_use"
    assert assistant_msg["content"][0]["id"] == "call_123"
    assert assistant_msg["content"][0]["name"] == "email.unread_summary"
    assert assistant_msg["content"][0]["input"] == {}


def test_convert_messages_tool_result_format() -> None:
    """Tool results become user messages with type=tool_result blocks."""
    result_data = {"summaries": [{"id": "m1", "subject": "Test"}], "count": 1}
    messages = [
        ChatMessage(role="user", content="check email"),
        ChatMessage(
            role="assistant",
            tool_calls=[{
                "id": "call_123",
                "type": "function",
                "function": {"name": "email.unread_summary", "arguments": "{}"},
            }],
        ),
        ChatMessage(
            role="tool",
            content=json.dumps(result_data),
            tool_call_id="call_123",
            name="email.unread_summary",
        ),
    ]
    _, converted = AnthropicClient._convert_messages(messages)
    assert len(converted) == 3

    tool_result_msg = converted[2]
    assert tool_result_msg["role"] == "user"
    assert isinstance(tool_result_msg["content"], list)
    assert tool_result_msg["content"][0]["type"] == "tool_result"
    assert tool_result_msg["content"][0]["tool_use_id"] == "call_123"


def test_convert_messages_multiple_tool_results_merged() -> None:
    """Multiple consecutive tool results merge into one user message."""
    messages = [
        ChatMessage(role="user", content="check email"),
        ChatMessage(
            role="assistant",
            tool_calls=[
                {"id": "c1", "type": "function", "function": {"name": "tool1", "arguments": "{}"}},
                {"id": "c2", "type": "function", "function": {"name": "tool2", "arguments": "{}"}},
            ],
        ),
        ChatMessage(role="tool", content='{"r": 1}', tool_call_id="c1", name="tool1"),
        ChatMessage(role="tool", content='{"r": 2}', tool_call_id="c2", name="tool2"),
    ]
    _, converted = AnthropicClient._convert_messages(messages)
    # user, assistant, user (merged tool results)
    assert len(converted) == 3
    tool_msg = converted[2]
    assert tool_msg["role"] == "user"
    assert len(tool_msg["content"]) == 2
    assert tool_msg["content"][0]["tool_use_id"] == "c1"
    assert tool_msg["content"][1]["tool_use_id"] == "c2"
