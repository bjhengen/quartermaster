"""Chat plugin — basic LLM conversation handling."""

import json
from typing import Any

import structlog

from plugins.chat.prompts import DEFAULT_PERSONA
from quartermaster.conversation.models import Turn
from quartermaster.llm.models import ChatMessage, LLMRequest, LLMResponse
from quartermaster.plugin.base import QuartermasterPlugin
from quartermaster.plugin.context import PluginContext
from quartermaster.plugin.health import HealthReport, HealthStatus
from quartermaster.transport.types import InboundMessage, OutboundMessage

logger = structlog.get_logger()

# Maximum characters for a tool result before truncation.
# ~8K chars ≈ ~2K tokens — leaves room for system prompt, conversation
# history, tool schemas, and LLM response within a 32K context window.
_MAX_TOOL_RESULT_CHARS = 8000

# Maximum items to keep when truncating list-based tool results.
# Truncates at the domain level (fewer items) rather than mid-JSON.
_MAX_RESULT_LIST_ITEMS = 10


def _truncate_tool_result(result_json: str, tool_name: str) -> str:
    """Truncate a tool result to fit within context window limits.

    Strategy: try domain-aware truncation first (reduce list items),
    fall back to character truncation if that's not possible.
    Always produces valid JSON when possible.
    """
    if len(result_json) <= _MAX_TOOL_RESULT_CHARS:
        return result_json

    # Try domain-aware truncation: find lists in the result and trim them
    try:
        data = json.loads(result_json)
        if _truncate_lists_in_place(data):
            truncated = json.dumps(data, default=str)
            if len(truncated) <= _MAX_TOOL_RESULT_CHARS:
                logger.info(
                    "tool_result_truncated_smart",
                    tool=tool_name,
                    original_len=len(result_json),
                    truncated_to=len(truncated),
                )
                return truncated
    except (json.JSONDecodeError, TypeError):
        pass

    # Fall back: character truncation as last resort
    logger.info(
        "tool_result_truncated_hard",
        tool=tool_name,
        original_len=len(result_json),
        truncated_to=_MAX_TOOL_RESULT_CHARS,
    )
    return (
        result_json[:_MAX_TOOL_RESULT_CHARS]
        + "\n... [truncated — result too large for context window]"
    )


def _truncate_lists_in_place(data: Any, max_items: int = _MAX_RESULT_LIST_ITEMS) -> bool:
    """Recursively find and truncate lists in a data structure.

    Returns True if any truncation was performed.
    """
    truncated = False
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list) and len(value) > max_items:
                original_len = len(value)
                data[key] = value[:max_items]
                data[key].append(
                    {"_truncated": True, "_showing": max_items, "_total": original_len}
                )
                truncated = True
            elif isinstance(value, (dict, list)):
                truncated = _truncate_lists_in_place(value, max_items) or truncated
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                truncated = _truncate_lists_in_place(item, max_items) or truncated
    return truncated


class ChatPlugin(QuartermasterPlugin):
    """Handles basic conversational messages."""

    name = "chat"
    version = "0.1.0"
    dependencies: list[str] = []

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None
        self._persona: str = DEFAULT_PERSONA

    async def setup(self, ctx: PluginContext) -> None:
        self._ctx = ctx
        # Use persona from config if available
        if hasattr(ctx.config, "persona") and ctx.config.persona:
            self._persona = ctx.config.persona

        ctx.events.subscribe("message.received", self._handle_message)
        logger.info("chat_plugin_ready")

    async def teardown(self) -> None:
        pass

    async def health(self) -> HealthReport:
        return HealthReport(status=HealthStatus.OK)

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle an incoming message by routing through the LLM."""
        assert self._ctx is not None
        message: InboundMessage = data["message"]

        # Skip command messages — let the commands plugin handle those
        if message.text.startswith("/"):
            return

        # Get or create conversation
        conv = await self._ctx.conversation.get_or_create(
            message.transport.value, message.chat_id
        )

        # Build context window
        history = await self._ctx.conversation.get_context_window(conv)

        # Build LLM request
        messages: list[ChatMessage] = [ChatMessage(role="system", content=self._persona)]
        messages.extend(history)
        messages.append(ChatMessage(role="user", content=message.text))

        # Get available tools
        tool_schemas = self._ctx.tools.get_tool_schemas()

        request = LLMRequest(messages=messages, tools=tool_schemas)

        # Route through LLM
        response = await self._ctx.llm.chat(request, purpose="chat", plugin_name="chat")

        # Handle tool calls if present
        if response.tool_calls:
            await self._handle_tool_calls(response, messages, message, conv)
            return

        # Send response
        await self._ctx.transport.send(
            OutboundMessage(
                transport=message.transport,
                chat_id=message.chat_id,
                text=response.content or "I couldn't generate a response.",
            )
        )

        # Save conversation turns
        await self._ctx.conversation.save_turn(
            conv,
            Turn(role="user", content=message.text),
        )
        await self._ctx.conversation.save_turn(
            conv,
            Turn(
                role="assistant",
                content=response.content,
                llm_backend=response.model,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                estimated_cost=response.estimated_cost,
            ),
        )

    async def _handle_tool_calls(
        self,
        response: LLMResponse,
        messages: list[ChatMessage],
        original_message: InboundMessage,
        conv: Any,
    ) -> None:
        """Execute tool calls and get final LLM response."""
        assert self._ctx is not None
        max_iterations = 5
        current_response = response

        for _ in range(max_iterations):
            if not current_response.tool_calls:
                break

            # Execute each tool call
            for tool_call in current_response.tool_calls:
                result: dict[str, Any] = await self._ctx.tools.execute(
                    tool_call.name, tool_call.arguments
                )
                logger.info(
                    "tool_executed",
                    tool=tool_call.name,
                    has_error="error" in result,
                )

                # Add tool call and result to messages
                messages.append(
                    ChatMessage(
                        role="assistant",
                        tool_calls=[
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.name,
                                    "arguments": json.dumps(tool_call.arguments),
                                },
                            }
                        ],
                    )
                )
                result_json = _truncate_tool_result(
                    json.dumps(result, default=str), tool_call.name
                )
                messages.append(
                    ChatMessage(
                        role="tool",
                        content=result_json,
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                )

            # Get next LLM response
            tool_schemas = self._ctx.tools.get_tool_schemas()
            request = LLMRequest(messages=messages, tools=tool_schemas)
            current_response = await self._ctx.llm.chat(
                request, purpose="tool-followup", plugin_name="chat"
            )

        # Send final response
        final_text = current_response.content or "Done."
        await self._ctx.transport.send(
            OutboundMessage(
                transport=original_message.transport,
                chat_id=original_message.chat_id,
                text=final_text,
            )
        )
