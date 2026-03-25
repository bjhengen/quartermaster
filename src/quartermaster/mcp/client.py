"""MCP Client Manager — connects to external MCP servers and bridges their tools.

Manages the lifecycle of MCP server connections: connecting, registering remote
tools into the local ToolRegistry with server-prefix namespacing, reconnecting
on failure with exponential backoff, and cleanly disconnecting on shutdown.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import structlog
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client

from quartermaster.core.metrics import (
    mcp_client_reconnect_total,
    mcp_client_status,
    mcp_tool_call_duration,
    mcp_tool_calls_total,
)
from quartermaster.core.tools import ApprovalTier, ToolRegistry
from quartermaster.mcp.bridge import mcp_result_to_dict, mcp_tool_to_definition
from quartermaster.mcp.config import MCPClientEntry, MCPConfig, TransportType
from quartermaster.mcp.transports import MCPTransportFactory

if TYPE_CHECKING:
    from quartermaster.core.events import EventBus

logger = structlog.get_logger()

# Reconnection parameters
_RECONNECT_BASE_DELAY = 5.0   # seconds
_RECONNECT_MAX_DELAY = 300.0  # 5 minutes
_RECONNECT_MULTIPLIER = 2.0


class MCPClientManager:
    """Manages connections to external MCP servers.

    For each enabled MCPClientEntry in config, establishes a transport
    connection, fetches available tools, and registers them into the
    ToolRegistry with ``server_name.tool_name`` namespacing.

    Handles reconnection with exponential backoff and cleans up registered
    tools when a server disconnects.
    """

    def __init__(
        self,
        config: MCPConfig,
        tools: ToolRegistry,
        events: EventBus,
    ) -> None:
        self._config = config
        self._tools = tools
        self._events = events
        self._transport_factory = MCPTransportFactory()

        # server_name → {"status": str, "tool_count": int, "error": str|None}
        self._server_statuses: dict[str, dict[str, Any]] = {
            name: {"status": "disconnected", "tool_count": 0, "error": None}
            for name in config.clients
        }

        # server_name → active ClientSession (for call_tool dispatch)
        self._sessions: dict[str, ClientSession] = {}

        # server_name → reconnect background Task
        self._reconnect_tasks: dict[str, asyncio.Task[None]] = {}

        # server_name → transport async context manager (for cleanup)
        self._transport_contexts: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect to all enabled MCP servers."""
        enabled = self._get_enabled_entries()
        if not enabled:
            logger.info("mcp_client_manager_no_servers_enabled")
            return

        for server_name, entry in enabled.items():
            await self._connect_server(server_name, entry)

    async def stop(self) -> None:
        """Disconnect from all servers and clean up resources."""
        # Cancel pending reconnect tasks
        for server_name, task in list(self._reconnect_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._reconnect_tasks.clear()

        # Close sessions (exits the receive loop task group)
        for server_name, session in list(self._sessions.items()):
            try:
                await session.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning(
                    "mcp_session_cleanup_error",
                    server=server_name,
                    error=str(exc),
                )

        # Clean up transport context managers
        for server_name, ctx in list(self._transport_contexts.items()):
            try:
                await ctx.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning(
                    "mcp_transport_cleanup_error",
                    server=server_name,
                    error=str(exc),
                )
        self._transport_contexts.clear()

        # Unregister tools and clear sessions
        for server_name in list(self._sessions.keys()):
            self._unregister_server_tools(server_name)
            self._set_status(server_name, "disconnected")
        self._sessions.clear()

        logger.info("mcp_client_manager_stopped")

    def get_server_statuses(self) -> dict[str, dict[str, Any]]:
        """Return a snapshot of all server connection statuses."""
        return {name: dict(status) for name, status in self._server_statuses.items()}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_enabled_entries(self) -> dict[str, MCPClientEntry]:
        """Return only enabled config entries."""
        return {
            name: entry
            for name, entry in self._config.clients.items()
            if entry.enabled
        }

    def _set_status(
        self,
        server_name: str,
        status: str,
        tool_count: int | None = None,
        error: str | None = None,
    ) -> None:
        """Update the status dict and Prometheus gauge for a server."""
        if server_name not in self._server_statuses:
            self._server_statuses[server_name] = {"status": "disconnected", "tool_count": 0, "error": None}

        self._server_statuses[server_name]["status"] = status
        if error is not None:
            self._server_statuses[server_name]["error"] = error
        if tool_count is not None:
            self._server_statuses[server_name]["tool_count"] = tool_count

        gauge_value = 1.0 if status == "connected" else (0.5 if status == "degraded" else 0.0)
        mcp_client_status.labels(server=server_name).set(gauge_value)

    async def _connect_server(self, server_name: str, entry: MCPClientEntry) -> None:
        """Attempt to connect to a single MCP server and register its tools."""
        logger.info("mcp_client_connecting", server=server_name, transport=entry.transport)
        self._set_status(server_name, "connecting")

        try:
            session = await self._create_session(server_name, entry)
            self._sessions[server_name] = session
            await self._register_server_tools(server_name, session, entry)

            tool_count = len(self._tools.list_by_source(server_name))
            self._set_status(server_name, "connected", tool_count=tool_count)
            logger.info(
                "mcp_client_connected",
                server=server_name,
                tool_count=tool_count,
            )

        except Exception as exc:
            logger.error(
                "mcp_client_connect_failed",
                server=server_name,
                error=str(exc),
            )
            self._set_status(server_name, "disconnected", error=str(exc))
            self._schedule_reconnect(server_name, entry)

    async def _create_session(
        self, server_name: str, entry: MCPClientEntry
    ) -> ClientSession:
        """Create and initialize a ClientSession for the given transport."""
        transport_ctx = self._transport_factory.get_transport_context(entry, server_name)
        transport_type = transport_ctx["type"]

        if transport_type == "streamable_http":
            http_ctx = streamablehttp_client(
                url=transport_ctx["url"],
                headers=transport_ctx.get("headers") or {},
            )
            self._transport_contexts[server_name] = http_ctx
            # streamablehttp_client yields a 3-tuple; extract first two streams
            http_streams: Any = await http_ctx.__aenter__()
            read_stream, write_stream = http_streams[0], http_streams[1]

        elif transport_type == "sse":
            sse_ctx = sse_client(
                url=transport_ctx["url"],
                headers=transport_ctx.get("headers") or {},
            )
            self._transport_contexts[server_name] = sse_ctx
            read_stream, write_stream = await sse_ctx.__aenter__()

        elif transport_type == "stdio":
            server_params: StdioServerParameters = transport_ctx["server_params"]
            stdio_ctx = stdio_client(server=server_params)
            self._transport_contexts[server_name] = stdio_ctx
            read_stream, write_stream = await stdio_ctx.__aenter__()

        else:
            raise ValueError(f"Unknown transport type: {transport_type!r}")

        # ClientSession is an async context manager that starts the receive
        # loop in __aenter__. Without entering it, initialize() hangs waiting
        # for a response that never arrives.
        session = ClientSession(read_stream, write_stream)
        await session.__aenter__()
        await session.initialize()
        return session

    async def _register_server_tools(
        self,
        server_name: str,
        session: ClientSession,
        entry: MCPClientEntry,
    ) -> None:
        """Fetch tools from the server and register them into the ToolRegistry.

        Applies:
        - server-prefix namespacing: ``{server_name}.{tool_name}``
        - default_approval_tier from config
        - per-tool overrides (approval_tier or enabled=False)
        - collision detection: existing tools are never overwritten
        """
        result = await session.list_tools()
        mcp_tools = result.tools

        default_tier = ApprovalTier(entry.default_approval_tier)

        for mcp_tool in mcp_tools:
            tool_name = mcp_tool.name
            namespaced_name = f"{server_name}.{tool_name}"

            # Apply per-tool override
            override = entry.tool_overrides.get(tool_name)
            if override is not None and not override.enabled:
                logger.debug(
                    "mcp_tool_disabled_by_override",
                    server=server_name,
                    tool=tool_name,
                )
                continue

            approval_tier = default_tier
            if override is not None and override.approval_tier is not None:
                approval_tier = ApprovalTier(override.approval_tier)

            # Skip if a tool with this name already exists (collision)
            if self._tools.get(namespaced_name) is not None:
                logger.warning(
                    "mcp_tool_name_collision_skipping_remote",
                    server=server_name,
                    tool=namespaced_name,
                )
                continue

            # Build the handler closure (avoids late-binding bug)
            handler = _make_handler(session, tool_name, server_name)

            tool_def = mcp_tool_to_definition(
                tool=mcp_tool,
                handler=handler,
                server_name=server_name,
                approval_tier=approval_tier,
                namespace=server_name,
            )

            self._tools.register(
                name=tool_def.name,
                description=tool_def.description,
                parameters=tool_def.parameters,
                handler=tool_def.handler,
                approval_tier=tool_def.approval_tier,
                metadata=tool_def.metadata,
                source=tool_def.source,
            )

            logger.debug(
                "mcp_tool_registered",
                server=server_name,
                tool=namespaced_name,
                tier=approval_tier,
            )

    def _unregister_server_tools(self, server_name: str) -> None:
        """Remove all tools registered from a given server."""
        tools = self._tools.list_by_source(server_name)
        for tool in tools:
            try:
                self._tools.unregister(tool.name)
            except KeyError:
                pass
        if tools:
            logger.info(
                "mcp_server_tools_unregistered",
                server=server_name,
                count=len(tools),
            )

    def _schedule_reconnect(
        self, server_name: str, entry: MCPClientEntry, attempt: int = 0
    ) -> None:
        """Schedule a background reconnect task with exponential backoff."""
        delay = min(
            _RECONNECT_BASE_DELAY * (_RECONNECT_MULTIPLIER ** attempt),
            _RECONNECT_MAX_DELAY,
        )

        async def _reconnect_task() -> None:
            await asyncio.sleep(delay)
            mcp_client_reconnect_total.labels(server=server_name).inc()
            logger.info(
                "mcp_client_reconnecting",
                server=server_name,
                attempt=attempt + 1,
                delay=delay,
            )
            try:
                session = await self._create_session(server_name, entry)
                self._sessions[server_name] = session
                await self._register_server_tools(server_name, session, entry)
                tool_count = len(self._tools.list_by_source(server_name))
                self._set_status(server_name, "connected", tool_count=tool_count)
                logger.info(
                    "mcp_client_reconnect_succeeded",
                    server=server_name,
                    attempt=attempt + 1,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "mcp_client_reconnect_failed",
                    server=server_name,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                self._set_status(server_name, "disconnected", error=str(exc))
                # Schedule next attempt
                self._schedule_reconnect(server_name, entry, attempt + 1)

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_reconnect_task())
            self._reconnect_tasks[server_name] = task
        except RuntimeError:
            # No running event loop — skip scheduling (e.g. during testing)
            logger.debug(
                "mcp_reconnect_no_event_loop",
                server=server_name,
            )


# ---------------------------------------------------------------------------
# Module-level closure factory (not a method, to avoid self capture)
# ---------------------------------------------------------------------------

def _make_handler(
    session: ClientSession,
    tool_name: str,
    server_name: str,
) -> Any:
    """Return an async handler that calls the remote tool via the MCP session.

    Using a factory function prevents late-binding issues when creating
    closures inside a loop.
    """

    async def handler(params: dict[str, Any]) -> dict[str, Any]:
        start = time.monotonic()
        status = "success"
        try:
            call_result = await session.call_tool(tool_name, params)
            return mcp_result_to_dict(call_result)
        except Exception as exc:
            status = "error"
            logger.error(
                "mcp_tool_call_error",
                server=server_name,
                tool=tool_name,
                error=str(exc),
            )
            return {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            elapsed = time.monotonic() - start
            mcp_tool_calls_total.labels(
                server=server_name, tool=tool_name, status=status
            ).inc()
            mcp_tool_call_duration.labels(
                server=server_name, tool=tool_name
            ).observe(elapsed)

    return handler
