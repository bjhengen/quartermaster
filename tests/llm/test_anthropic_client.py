"""Tests for the Anthropic API client."""

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
