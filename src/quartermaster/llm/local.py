"""llama-swap local LLM client (OpenAI-compatible API)."""

import json
from enum import StrEnum
from typing import Any

import httpx
import structlog

from quartermaster.llm.models import LLMRequest, LLMResponse, ToolCall

logger = structlog.get_logger()


class LlamaSwapStatus(StrEnum):
    IDLE = "idle"
    PREFERRED_LOADED = "preferred_loaded"
    OTHER_LOADED = "other_loaded"
    UNREACHABLE = "unreachable"


class LocalLLMClient:
    """Client for llama-swap's OpenAI-compatible API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8200/v1",
        preferred_model: str = "qwen3.5-27b",
        timeout: int = 60,
    ) -> None:
        self._base_url = base_url
        self._preferred_model = preferred_model
        self._timeout = timeout
        self._status_url = base_url.rsplit("/v1", 1)[0] + "/running"

    async def check_status(self) -> LlamaSwapStatus:
        """Check what's currently loaded in llama-swap."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self._status_url, timeout=5)
                data = resp.json()
                running = data.get("running", [])

                if not running:
                    return LlamaSwapStatus.IDLE

                loaded_models = [m.get("model", "") for m in running]
                if any(self._preferred_model in m for m in loaded_models):
                    return LlamaSwapStatus.PREFERRED_LOADED

                return LlamaSwapStatus.OTHER_LOADED

        except (httpx.ConnectError, httpx.TimeoutException):
            return LlamaSwapStatus.UNREACHABLE

    async def chat(self, request: LLMRequest, timeout: int | None = None) -> LLMResponse:
        """Send a chat completion request to llama-swap."""
        effective_timeout = timeout or self._timeout

        messages_payload: list[dict[str, Any]] = []
        for msg in request.messages:
            m: dict[str, Any] = {"role": msg.role}
            if msg.content is not None:
                m["content"] = msg.content
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.name:
                m["name"] = msg.name
            messages_payload.append(m)

        payload: dict[str, Any] = {
            "model": request.model or self._preferred_model,
            "messages": messages_payload,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if request.tools:
            payload["tools"] = request.tools

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                timeout=effective_timeout,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

        choice = data["choices"][0]
        message = choice["message"]

        tool_calls: list[ToolCall] = []
        if "tool_calls" in message and message["tool_calls"]:
            for tc in message["tool_calls"]:
                args = tc["function"].get("arguments", "{}")
                if isinstance(args, str):
                    args = json.loads(args)
                tool_calls.append(
                    ToolCall(
                        id=tc["id"],
                        name=tc["function"]["name"],
                        arguments=args,
                    )
                )

        usage: dict[str, Any] = data.get("usage", {})
        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            model=data.get("model", self._preferred_model),
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
        )
