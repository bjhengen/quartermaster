"""Anthropic API client wrapper."""

from typing import Any

import structlog
from anthropic import AsyncAnthropic

from quartermaster.llm.models import LLMRequest, LLMResponse, ToolCall

logger = structlog.get_logger()

# Rough cost per million tokens (USD)
COST_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
}


class AnthropicClient:
    """Client for the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._default_model = default_model

    async def chat(self, request: LLMRequest) -> LLMResponse:
        """Send a chat request to Anthropic."""
        model = request.model or self._default_model

        # Convert messages — extract system prompt, convert rest
        system_prompt = ""
        messages: list[dict[str, Any]] = []
        for msg in request.messages:
            if msg.role == "system":
                system_prompt = msg.content or ""
            else:
                m: dict[str, Any] = {"role": msg.role}
                if msg.content is not None:
                    m["content"] = msg.content
                if msg.tool_call_id:
                    m["tool_use_id"] = msg.tool_call_id
                messages.append(m)

        # Convert tools from OpenAI format to Anthropic format
        tools: list[dict[str, Any]] = []
        if request.tools:
            for tool in request.tools:
                fn = tool.get("function", {})
                tools.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {}),
                })

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)

        # Parse response
        content_text: str | None = None
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                content_text = block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))

        # Estimate cost
        cost_rates = COST_PER_MTOK.get(model, {"input": 3.0, "output": 15.0})
        estimated_cost = (
            (response.usage.input_tokens * cost_rates["input"] / 1_000_000)
            + (response.usage.output_tokens * cost_rates["output"] / 1_000_000)
        )

        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            model=model,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            estimated_cost=estimated_cost,
        )
