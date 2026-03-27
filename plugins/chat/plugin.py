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
                tool_def = self._ctx.tools.get(tool_call.name)
                if tool_def and tool_def.approval_tier.value == "confirm":
                    # TODO: Route through approval manager (Task for later)
                    result: dict[str, Any] = {
                        "status": "approval_required",
                        "message": "This action needs approval.",
                    }
                else:
                    result = await self._ctx.tools.execute(
                        tool_call.name, tool_call.arguments
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
                result_json = json.dumps(result, default=str)
                if len(result_json) > _MAX_TOOL_RESULT_CHARS:
                    logger.info(
                        "tool_result_truncated",
                        tool=tool_call.name,
                        original_len=len(result_json),
                        truncated_to=_MAX_TOOL_RESULT_CHARS,
                    )
                    result_json = (
                        result_json[:_MAX_TOOL_RESULT_CHARS]
                        + '\n... [truncated — result too large for context window]'
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
