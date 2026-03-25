"""Tests for the smart LLM router."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from quartermaster.core.usage import BudgetStatus
from quartermaster.llm.local import LlamaSwapStatus
from quartermaster.llm.models import ChatMessage, LLMRequest, LLMResponse
from quartermaster.llm.router import LLMRouter


@pytest.fixture
def mock_local() -> MagicMock:
    client = MagicMock()
    client.check_status = AsyncMock(return_value=LlamaSwapStatus.PREFERRED_LOADED)
    client.chat = AsyncMock(return_value=LLMResponse(
        content="local response",
        tool_calls=[],
        model="qwen3.5-27b",
        tokens_in=10,
        tokens_out=20,
    ))
    return client


@pytest.fixture
def mock_anthropic() -> MagicMock:
    client = MagicMock()
    client.chat = AsyncMock(return_value=LLMResponse(
        content="cloud response",
        tool_calls=[],
        model="claude-sonnet-4-20250514",
        tokens_in=10,
        tokens_out=20,
        estimated_cost=0.001,
    ))
    return client


@pytest.fixture
def mock_usage() -> MagicMock:
    tracker = MagicMock()
    tracker.log = AsyncMock()
    tracker.get_budget_status = AsyncMock(return_value=BudgetStatus.OK)
    return tracker


@pytest.mark.asyncio
async def test_routes_to_local_when_preferred_loaded(
    mock_local: MagicMock,
    mock_anthropic: MagicMock,
    mock_usage: MagicMock,
) -> None:
    router = LLMRouter(
        local_client=mock_local,
        anthropic_client=mock_anthropic,
        usage_tracker=mock_usage,
    )
    request = LLMRequest(messages=[ChatMessage(role="user", content="hi")])
    response = await router.chat(request)
    assert response.content == "local response"
    mock_local.chat.assert_awaited_once()
    mock_anthropic.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_routes_to_local_when_idle(
    mock_local: MagicMock,
    mock_anthropic: MagicMock,
    mock_usage: MagicMock,
) -> None:
    mock_local.check_status = AsyncMock(return_value=LlamaSwapStatus.IDLE)
    router = LLMRouter(
        local_client=mock_local,
        anthropic_client=mock_anthropic,
        usage_tracker=mock_usage,
    )
    request = LLMRequest(messages=[ChatMessage(role="user", content="hi")])
    response = await router.chat(request)
    assert response.content == "local response"


@pytest.mark.asyncio
async def test_falls_back_to_anthropic_when_unreachable(
    mock_local: MagicMock,
    mock_anthropic: MagicMock,
    mock_usage: MagicMock,
) -> None:
    mock_local.check_status = AsyncMock(return_value=LlamaSwapStatus.UNREACHABLE)
    router = LLMRouter(
        local_client=mock_local,
        anthropic_client=mock_anthropic,
        usage_tracker=mock_usage,
    )
    request = LLMRequest(messages=[ChatMessage(role="user", content="hi")])
    response = await router.chat(request)
    assert response.content == "cloud response"
    mock_anthropic.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_falls_back_on_local_timeout(
    mock_local: MagicMock,
    mock_anthropic: MagicMock,
    mock_usage: MagicMock,
) -> None:
    mock_local.check_status = AsyncMock(return_value=LlamaSwapStatus.PREFERRED_LOADED)
    mock_local.chat = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    router = LLMRouter(
        local_client=mock_local,
        anthropic_client=mock_anthropic,
        usage_tracker=mock_usage,
    )
    request = LLMRequest(messages=[ChatMessage(role="user", content="hi")])
    response = await router.chat(request)
    assert response.content == "cloud response"


@pytest.mark.asyncio
async def test_usage_logged_for_cloud_calls(
    mock_local: MagicMock,
    mock_anthropic: MagicMock,
    mock_usage: MagicMock,
) -> None:
    mock_local.check_status = AsyncMock(return_value=LlamaSwapStatus.UNREACHABLE)
    router = LLMRouter(
        local_client=mock_local,
        anthropic_client=mock_anthropic,
        usage_tracker=mock_usage,
    )
    request = LLMRequest(messages=[ChatMessage(role="user", content="hi")])
    await router.chat(request)
    mock_usage.log.assert_awaited_once()
