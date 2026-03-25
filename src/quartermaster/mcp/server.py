"""MCP Server — exposes Quartermaster's Tool Registry via Streamable HTTP.

External MCP clients (e.g. Claude Desktop, other agents) connect here to
discover and invoke the tools registered in the local ToolRegistry.

Architecture:
- Uses mcp.server.lowlevel.server.Server with list_tools/call_tool decorators
- Uses StreamableHTTPSessionManager for Streamable HTTP transport
- Wrapped in a Starlette app with BearerTokenAuth middleware
- Started via programmatic uvicorn as an asyncio Task
- Subscribes to tools.registry_changed to log tool changes
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import uvicorn
from mcp.server.lowlevel.server import Server as MCPServerImpl
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount

from quartermaster.core.approval import ApprovalRequest, ApprovalStatus
from quartermaster.core.metrics import mcp_server_requests_total
from quartermaster.core.tools import ApprovalTier, ToolRegistry
from quartermaster.mcp.auth import BearerTokenAuth
from quartermaster.mcp.bridge import definition_to_mcp_tool, dict_to_mcp_result
from quartermaster.transport.types import TransportType

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.types import TextContent
    from mcp.types import Tool as MCPTool

    from quartermaster.mcp.config import MCPServerConfig

logger = structlog.get_logger()

# Approval wait timeout: 1 hour — production wiring passes this explicitly.
_APPROVAL_TIMEOUT_SECS = 3600.0

# Constructor default: small so unit tests that don't fire the resolved event
# complete quickly.  Production bootstrap passes approval_timeout_secs=3600.0.
_DEFAULT_APPROVAL_TIMEOUT_SECS = 0.05


class MCPServer:
    """Exposes Quartermaster's ToolRegistry to external MCP clients via Streamable HTTP.

    Lifecycle:
        server = MCPServer(config, tools, events, approval, transport)
        await server.start()
        ...
        await server.stop()
    """

    def __init__(
        self,
        config: MCPServerConfig,
        tools: ToolRegistry,
        events: Any,
        approval: Any,
        transport: Any,
        approval_timeout_secs: float = _DEFAULT_APPROVAL_TIMEOUT_SECS,
    ) -> None:
        self._config = config
        self._tools = tools
        self._events = events
        self._approval = approval
        self._transport = transport
        self._approval_timeout_secs = approval_timeout_secs

        # Underlying MCP server instance
        self._mcp_impl = MCPServerImpl(name="quartermaster", version="1.0.0")
        self._session_manager: StreamableHTTPSessionManager | None = None

        # uvicorn server handle for graceful shutdown
        self._uvicorn_server: uvicorn.Server | None = None
        self._serve_task: asyncio.Task[None] | None = None

        # Register MCP protocol handlers
        self._register_mcp_handlers()

        # Subscribe to tool registry changes
        self._events.subscribe("tools.registry_changed", self._on_tools_changed)

        logger.info("mcp_server_init", port=config.port, bind=config.bind)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Load auth token, build Starlette app, and start uvicorn."""
        if not self._config.enabled:
            logger.info("mcp_server_disabled")
            return

        # Load auth token
        token = Path(self._config.auth_token_file).read_text().strip()

        # Build auth middleware
        auth = BearerTokenAuth(token=token, allowed_hosts=self._config.allowed_hosts)

        # Create session manager
        self._session_manager = StreamableHTTPSessionManager(
            app=self._mcp_impl,
            stateless=False,
        )

        # Build Starlette app with lifespan + auth middleware
        session_manager = self._session_manager

        @contextlib.asynccontextmanager
        async def lifespan(app: Starlette) -> AsyncIterator[None]:
            async with session_manager.run():
                logger.info("mcp_server_session_manager_started")
                yield
            logger.info("mcp_server_session_manager_stopped")

        starlette_app = Starlette(
            lifespan=lifespan,
            routes=[
                Mount("/mcp", app=session_manager.handle_request),
            ],
        )
        starlette_app.add_middleware(auth.as_middleware_class())

        # Configure uvicorn
        uvi_config = uvicorn.Config(
            app=starlette_app,
            host=self._config.bind,
            port=self._config.port,
            log_level="warning",
        )
        self._uvicorn_server = uvicorn.Server(uvi_config)

        # Start in background task
        self._serve_task = asyncio.get_event_loop().create_task(
            self._uvicorn_server.serve()
        )

        logger.info(
            "mcp_server_started",
            host=self._config.bind,
            port=self._config.port,
        )

    async def stop(self) -> None:
        """Signal uvicorn to exit and await cleanup."""
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True

        if self._serve_task is not None and not self._serve_task.done():
            try:
                await asyncio.wait_for(self._serve_task, timeout=10.0)
            except (TimeoutError, asyncio.CancelledError):
                self._serve_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._serve_task

        logger.info("mcp_server_stopped")

    # ------------------------------------------------------------------
    # MCP protocol handler registration
    # ------------------------------------------------------------------

    def _register_mcp_handlers(self) -> None:
        """Register list_tools and call_tool handlers on the MCP impl."""

        @self._mcp_impl.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
        async def handle_list_tools() -> list[MCPTool]:
            mcp_server_requests_total.labels(method="list_tools", status="ok").inc()
            tools = self._get_mcp_tools()
            logger.debug("mcp_server_list_tools", count=len(tools))
            return tools

        @self._mcp_impl.call_tool()  # type: ignore[untyped-decorator]
        async def handle_call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent]:
            mcp_server_requests_total.labels(method="call_tool", status="ok").inc()
            result = await self._handle_tool_call(name, arguments or {})
            return dict_to_mcp_result(result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_mcp_tools(self) -> list[MCPTool]:
        """Translate the ToolRegistry into a list of MCP Tool objects."""
        return [definition_to_mcp_tool(defn) for defn in self._tools.list_tools()]

    async def _handle_tool_call(
        self, name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch a tool call respecting approval tiers.

        - AUTONOMOUS → execute directly
        - CONFIRM → route to ApprovalManager, wait for resolution
        - NOTIFY → execute, fire-and-forget notification
        """
        defn = self._tools.get(name)
        if defn is None:
            logger.warning("mcp_server_unknown_tool", tool=name)
            return {"error": f"Unknown tool: {name!r}"}

        tier = defn.approval_tier

        if tier == ApprovalTier.AUTONOMOUS:
            return await self._tools.execute(name, params)

        if tier == ApprovalTier.CONFIRM:
            return await self._handle_confirm_tier(defn.name, params)

        if tier == ApprovalTier.NOTIFY:
            result = await self._tools.execute(name, params)
            # Fire-and-forget: emit notification event (best effort)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._events.emit(
                        "mcp.tool_executed",
                        {"tool": name, "params": params, "result": result},
                    )
                )
            except RuntimeError:
                pass
            return result

        # Unknown tier — execute autonomously as a safe fallback
        logger.warning("mcp_server_unknown_tier", tool=name, tier=str(tier))
        return await self._tools.execute(name, params)

    async def _handle_confirm_tier(
        self, tool_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Send an approval request and wait for resolution.

        Creates an asyncio.Event keyed on the approval_id returned by
        ApprovalManager.request_approval(). The event bus fires
        'approval.resolved' when the user approves or rejects via Telegram.

        Waits up to approval_timeout_secs (default: 0.05s in tests,
        pass 3600.0 in production).
        """
        chat_id = self._config.approval_chat_id or ""
        if not chat_id:
            logger.warning("mcp_server_confirm_no_chat_id", tool=tool_name)
            return {"error": "No approval_chat_id configured for confirm-tier tools"}

        draft = (
            f"Tool `{tool_name}` called with:\n```\n"
            f"{json.dumps(params, default=str, indent=2)}\n```"
        )

        req = ApprovalRequest(
            plugin_name="mcp_server",
            tool_name=tool_name,
            draft_content=draft,
            action_payload={"tool": tool_name, "params": params},
            chat_id=chat_id,
            transport=TransportType.TELEGRAM,
        )

        try:
            approval_id = await self._approval.request_approval(req)
        except Exception as exc:
            logger.error(
                "mcp_server_approval_request_failed", tool=tool_name, error=str(exc)
            )
            return {"error": f"Failed to request approval: {exc}"}

        # Wait for approval.resolved event
        resolved_event = asyncio.Event()
        resolved_status: dict[str, str] = {}

        async def on_resolved(data: dict[str, Any]) -> None:
            if data.get("approval_id") == approval_id:
                resolved_status["status"] = data.get("status", "")
                resolved_event.set()

        self._events.subscribe("approval.resolved", on_resolved)
        try:
            await asyncio.wait_for(
                resolved_event.wait(), timeout=self._approval_timeout_secs
            )
        except TimeoutError:
            logger.warning(
                "mcp_server_approval_timeout",
                tool=tool_name,
                approval_id=approval_id,
            )
            return {"error": "Approval timed out"}
        finally:
            self._events.unsubscribe("approval.resolved", on_resolved)

        status = resolved_status.get("status", "")
        if status == ApprovalStatus.APPROVED:
            logger.info(
                "mcp_server_approval_approved",
                tool=tool_name,
                approval_id=approval_id,
            )
            return await self._tools.execute(tool_name, params)

        logger.info(
            "mcp_server_approval_rejected",
            tool=tool_name,
            approval_id=approval_id,
            status=status,
        )
        return {"error": f"Tool call rejected (status={status!r})"}

    async def _on_tools_changed(self, data: dict[str, Any]) -> None:
        """Log tool registry changes. Future: send MCP notifications to clients."""
        action = data.get("action", "changed")
        tool = data.get("tool", "unknown")
        logger.info("mcp_server_tools_changed", action=action, tool=tool)
        # TODO: send ToolListChangedNotification to connected clients when
        # mcp library exposes server-push notification API.
