"""Smart LLM routing — local-first with Anthropic fallback."""

from typing import Any

import httpx
import structlog

from quartermaster.core.usage import BudgetStatus, UsageRecord, UsageTracker
from quartermaster.llm.anthropic_client import AnthropicClient
from quartermaster.llm.local import LlamaSwapStatus, LocalLLMClient
from quartermaster.llm.models import LLMRequest, LLMResponse

logger = structlog.get_logger()


class LLMRouter:
    """Routes LLM requests to the best available backend."""

    def __init__(
        self,
        local_client: LocalLLMClient | Any,
        anthropic_client: AnthropicClient | Any | None = None,
        usage_tracker: UsageTracker | Any | None = None,
    ) -> None:
        self._local = local_client
        self._anthropic = anthropic_client
        self._usage = usage_tracker

    async def chat(
        self,
        request: LLMRequest,
        purpose: str = "chat",
        plugin_name: str = "core",
    ) -> LLMResponse:
        """Route a chat request to the best available backend."""
        status = await self._local.check_status()
        logger.debug("llm_routing", llama_swap_status=status.value)

        # Try local first if available
        if status in (LlamaSwapStatus.IDLE, LlamaSwapStatus.PREFERRED_LOADED):
            try:
                response = await self._local.chat(request)
                await self._log_usage(response, "llama-swap", purpose, plugin_name)
                return response
            except httpx.TimeoutException:
                logger.warning("local_llm_timeout", status=status.value)
            except Exception:
                logger.exception("local_llm_error")

        # Try local with swap timeout for OTHER_LOADED
        if status == LlamaSwapStatus.OTHER_LOADED:
            try:
                response = await self._local.chat(request, timeout=120)
                await self._log_usage(response, "llama-swap", purpose, plugin_name)
                return response
            except httpx.TimeoutException:
                logger.warning("local_llm_swap_timeout")
            except Exception:
                logger.exception("local_llm_error")

        # Fall back to Anthropic — check budget first
        if self._anthropic:
            if self._usage:
                budget_status = await self._usage.get_budget_status()
                if budget_status == BudgetStatus.BLOCKED:
                    logger.warning("anthropic_blocked_by_budget")
                    return LLMResponse(
                        content=(
                            "API budget exhausted for this month."
                            " Waiting for local LLM availability."
                        ),
                        model="budget-blocked",
                    )
            try:
                response = await self._anthropic.chat(request)
                await self._log_usage(response, "anthropic", purpose, plugin_name)
                return response
            except Exception:
                logger.exception("anthropic_error")

        # Both failed
        return LLMResponse(
            content="I'm having trouble reaching my backends — try again in a few minutes.",
            model="error",
        )

    async def get_local_status(self) -> LlamaSwapStatus:
        """Check what's currently loaded in llama-swap."""
        return await self._local.check_status()

    async def _log_usage(
        self,
        response: LLMResponse,
        provider: str,
        purpose: str,
        plugin_name: str,
    ) -> None:
        """Log usage if tracker is available."""
        if self._usage:
            await self._usage.log(UsageRecord(
                provider=provider,
                model=response.model,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                estimated_cost=response.estimated_cost,
                purpose=purpose,
                plugin_name=plugin_name,
            ))
