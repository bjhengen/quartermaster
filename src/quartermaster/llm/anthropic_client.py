"""Anthropic API client wrapper.

Converts between the internal OpenAI-style ChatMessage format and
Anthropic's Messages API format.  Key differences:
- System prompt is a top-level kwarg, not a message
- Assistant tool calls are content blocks with type="tool_use"
- Tool results are user messages with content blocks of type="tool_result"
"""

import json
from typing import Any

import structlog
from anthropic import AsyncAnthropic

from quartermaster.llm.models import ChatMessage, LLMRequest, LLMResponse, ToolCall

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

        system_prompt, messages = self._convert_messages(request.messages)
        tools = self._convert_tools(request.tools)

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

    # ------------------------------------------------------------------
    # Format conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_messages(
        messages: list[ChatMessage],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Convert internal ChatMessages to Anthropic format.

        Returns (system_prompt, messages).

        Anthropic differences from OpenAI format:
        - System prompt is extracted as a separate string
        - Assistant messages with tool_calls become content blocks
          with type="tool_use"
        - Tool result messages (role="tool") become user messages
          with content blocks of type="tool_result"
        """
        system_prompt = ""
        converted: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content or ""

            elif msg.role == "assistant" and msg.tool_calls:
                # Assistant message with tool calls → content blocks
                content: list[dict[str, Any]] = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    if isinstance(args, str):
                        args = json.loads(args)
                    content.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": args,
                    })
                converted.append({"role": "assistant", "content": content})

            elif msg.role == "tool":
                # Tool result → user message with tool_result content block
                # Anthropic requires tool results as user messages
                result_content = msg.content or ""
                # Try to parse as JSON for structured content
                try:
                    parsed = json.loads(result_content)
                    result_text = json.dumps(parsed, indent=2, default=str)
                except (json.JSONDecodeError, TypeError):
                    result_text = result_content

                tool_result_block: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id or "",
                    "content": result_text,
                }
                # Merge with previous user message if it's also a tool_result
                if converted and converted[-1].get("role") == "user":
                    last_content = converted[-1].get("content", [])
                    if isinstance(last_content, list):
                        last_content.append(tool_result_block)
                        continue
                converted.append({
                    "role": "user",
                    "content": [tool_result_block],
                })

            elif msg.role == "assistant":
                converted.append({
                    "role": "assistant",
                    "content": msg.content or "",
                })

            elif msg.role == "user":
                converted.append({
                    "role": "user",
                    "content": msg.content or "",
                })

        return system_prompt, converted

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI-format tools to Anthropic format."""
        converted: list[dict[str, Any]] = []
        for tool in tools:
            fn = tool.get("function", {})
            converted.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {}),
            })
        return converted
