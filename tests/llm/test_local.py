"""Tests for the llama-swap local LLM client."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from quartermaster.llm.local import LlamaSwapStatus, LocalLLMClient
from quartermaster.llm.models import (
    ChatMessage,
    LLMRequest,
    LLMResponse,
)


def test_llm_request_model() -> None:
    req = LLMRequest(
        messages=[ChatMessage(role="user", content="hello")],
        tools=[],
    )
    assert req.messages[0].role == "user"


def test_llm_response_model() -> None:
    resp = LLMResponse(
        content="Hello!",
        tool_calls=[],
        model="qwen3.5-27b",
        tokens_in=5,
        tokens_out=10,
    )
    assert resp.content == "Hello!"
    assert resp.tokens_in == 5


@pytest.mark.asyncio
async def test_check_status_idle() -> None:
    mock_response = httpx.Response(
        200,
        json={"running": []},
        request=httpx.Request("GET", "http://localhost:8200/running"),
    )
    with patch("quartermaster.llm.local.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        client = LocalLLMClient(base_url="http://localhost:8200/v1", preferred_model="qwen3.5-27b")
        status = await client.check_status()
        assert status == LlamaSwapStatus.IDLE


@pytest.mark.asyncio
async def test_check_status_preferred_loaded() -> None:
    mock_response = httpx.Response(
        200,
        json={"running": [{"model": "qwen3.5-27b", "state": "ready"}]},
        request=httpx.Request("GET", "http://localhost:8200/running"),
    )
    with patch("quartermaster.llm.local.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        client = LocalLLMClient(base_url="http://localhost:8200/v1", preferred_model="qwen3.5-27b")
        status = await client.check_status()
        assert status == LlamaSwapStatus.PREFERRED_LOADED
