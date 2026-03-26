"""Prometheus metrics endpoint."""

import structlog
from aiohttp import web
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = structlog.get_logger()

# LLM metrics
llm_requests_total = Counter(
    "qm_llm_requests_total",
    "Total LLM requests",
    ["provider", "model", "purpose"],
)
llm_request_duration = Histogram(
    "qm_llm_request_duration_seconds",
    "LLM request duration",
    ["provider"],
)
llm_tokens_total = Counter(
    "qm_llm_tokens_total",
    "Total tokens processed",
    ["provider", "direction"],
)
llm_cost_total = Counter(
    "qm_llm_cost_usd_total",
    "Total API cost in USD",
    ["provider"],
)

# Tool metrics
tool_invocations_total = Counter(
    "qm_tool_invocations_total",
    "Total tool invocations",
    ["tool", "status"],
)

# Message metrics
messages_total = Counter(
    "qm_messages_total",
    "Total messages",
    ["transport", "direction"],
)

# Plugin health
plugin_health = Gauge(
    "qm_plugin_health",
    "Plugin health status (1=ok, 0.5=degraded, 0=down)",
    ["plugin"],
)

# Budget
budget_used_usd = Gauge(
    "qm_budget_used_usd",
    "Current month API spend in USD",
)
budget_limit_usd = Gauge(
    "qm_budget_limit_usd",
    "Monthly API budget limit in USD",
)

# MCP Client metrics
mcp_client_status = Gauge(
    "qm_mcp_client_status",
    "MCP client connection status (1=up, 0=down, 0.5=degraded)",
    ["server"],
)
mcp_client_reconnect_total = Counter(
    "qm_mcp_client_reconnect_total",
    "Total MCP client reconnection attempts",
    ["server"],
)
mcp_tool_calls_total = Counter(
    "qm_mcp_tool_calls_total",
    "Total MCP remote tool calls",
    ["server", "tool", "status"],
)
mcp_tool_call_duration = Histogram(
    "qm_mcp_tool_call_duration_seconds",
    "MCP remote tool call duration",
    ["server", "tool"],
)

# MCP Server metrics
mcp_server_requests_total = Counter(
    "qm_mcp_server_requests_total",
    "Total MCP server requests",
    ["method", "status"],
)
mcp_server_connected_clients = Gauge(
    "qm_mcp_server_connected_clients",
    "Number of connected MCP clients",
)
mcp_server_auth_failures_total = Counter(
    "qm_mcp_server_auth_failures_total",
    "Total MCP server authentication failures",
)


async def metrics_handler(request: web.Request) -> web.Response:
    """HTTP handler for /metrics endpoint."""
    return web.Response(
        body=generate_latest(),
        content_type="text/plain",
    )


async def start_metrics_server(port: int) -> web.AppRunner:
    """Start the Prometheus metrics HTTP server."""
    app = web.Application()
    app.router.add_get("/metrics", metrics_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("metrics_server_started", port=port)
    return runner
