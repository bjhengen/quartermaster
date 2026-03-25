"""Application bootstrap and lifecycle management."""

import asyncio
import signal
from pathlib import Path
from typing import Any

import structlog

from quartermaster.conversation.manager import ConversationManager
from quartermaster.core.approval import ApprovalManager
from quartermaster.core.config import QuartermasterConfig, load_config
from quartermaster.core.database import Database
from quartermaster.core.events import EventBus
from quartermaster.core.metrics import start_metrics_server
from quartermaster.core.scheduler import Scheduler
from quartermaster.core.tools import ToolRegistry
from quartermaster.core.usage import UsageTracker
from quartermaster.llm.anthropic_client import AnthropicClient
from quartermaster.llm.local import LocalLLMClient
from quartermaster.llm.router import LLMRouter
from quartermaster.mcp.client import MCPClientManager
from quartermaster.mcp.server import MCPServer
from quartermaster.plugin.context import PluginContext
from quartermaster.plugin.loader import PluginLoader
from quartermaster.transport.manager import TransportManager
from quartermaster.transport.telegram import TelegramTransport

logger = structlog.get_logger()


class QuartermasterApp:
    """Main application — wires everything together."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._config: QuartermasterConfig | None = None
        self._db: Database | None = None
        self._events: EventBus | None = None
        self._tools: ToolRegistry | None = None
        self._usage: UsageTracker | None = None
        self._llm: LLMRouter | None = None
        self._transport: TransportManager | None = None
        self._conversation: ConversationManager | None = None
        self._scheduler: Any = None
        self._approval: Any = None
        self._plugin_loader: PluginLoader | None = None
        self._mcp_client: MCPClientManager | None = None
        self._mcp_server: MCPServer | None = None
        self._metrics_runner: Any = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Initialize and start all services."""
        logger.info("quartermaster_starting")

        self._config = load_config(self._config_path)
        self._events = EventBus()
        self._tools = ToolRegistry(events=self._events)

        self._db = Database(self._config.database)
        await self._db.connect()

        self._usage = UsageTracker(
            db=self._db,
            monthly_budget=self._config.llm.monthly_budget_usd,
            warn_percent=self._config.llm.budget_warn_percent,
            block_percent=self._config.llm.budget_block_percent,
        )

        local_client = LocalLLMClient(
            base_url=self._config.llm.local.base_url,
            preferred_model=self._config.llm.local.preferred_model,
            timeout=self._config.llm.local.timeout_seconds,
        )

        anthropic_client: AnthropicClient | None = None
        if self._config.llm.anthropic:
            api_key_path = Path(self._config.llm.anthropic.api_key_file)
            if api_key_path.exists():
                api_key = api_key_path.read_text().strip()
                anthropic_client = AnthropicClient(
                    api_key=api_key,
                    default_model=self._config.llm.anthropic.default_model,
                )

        self._llm = LLMRouter(
            local_client=local_client,
            anthropic_client=anthropic_client,
            usage_tracker=self._usage,
        )

        self._conversation = ConversationManager(
            db=self._db,
            config=self._config.conversation,
        )

        self._scheduler = Scheduler(
            db=self._db,
            events=self._events,
            grace_minutes=self._config.scheduler.missed_event_grace_minutes,
        )

        self._transport = TransportManager()
        telegram = TelegramTransport(
            bot_token=self._config.telegram_bot_token,
            allowed_user_ids=self._config.allowed_user_ids,
            events=self._events,
        )
        self._transport.register(telegram)

        self._approval = ApprovalManager(
            db=self._db,
            transport=self._transport,
            events=self._events,
            timeout_minutes=self._config.approval.default_timeout_minutes,
        )

        self._metrics_runner = await start_metrics_server(
            self._config.metrics.port
        )

        ctx = PluginContext(
            config=self._config,
            events=self._events,
            tools=self._tools,
            db=self._db,
            llm=self._llm,
            transport=self._transport,
            scheduler=self._scheduler,
            approval=self._approval,
            usage=self._usage,
            conversation=self._conversation,
        )

        self._plugin_loader = PluginLoader()
        self._discover_plugins()
        await self._plugin_loader.load_all(ctx)

        # Start MCP client (connects to external servers, registers tools)
        if self._config.mcp.clients:
            self._mcp_client = MCPClientManager(
                config=self._config.mcp,
                tools=self._tools,
                events=self._events,
            )
            await self._mcp_client.start()
            ctx.mcp_client = self._mcp_client

        # Start MCP server (exposes tools to external clients)
        if self._config.mcp.server and self._config.mcp.server.enabled:
            self._mcp_server = MCPServer(
                config=self._config.mcp.server,
                tools=self._tools,
                events=self._events,
                approval=self._approval,
                transport=self._transport,
            )
            await self._mcp_server.start()

        await self._transport.start_all()
        await self._scheduler.start()

        logger.info("quartermaster_started")

    def _discover_plugins(self) -> None:
        """Discover and register plugin classes."""
        assert self._plugin_loader is not None
        from plugins.briefing.plugin import BriefingPlugin
        from plugins.chat.plugin import ChatPlugin
        from plugins.commands.plugin import CommandsPlugin

        self._plugin_loader.register_class(ChatPlugin)
        self._plugin_loader.register_class(CommandsPlugin)
        self._plugin_loader.register_class(BriefingPlugin)

    async def stop(self) -> None:
        """Gracefully shut down all services."""
        logger.info("quartermaster_stopping")

        if self._scheduler:
            await self._scheduler.stop()
        if self._transport:
            await self._transport.stop_all()
        if self._mcp_server:
            await self._mcp_server.stop()
        if self._mcp_client:
            await self._mcp_client.stop()
        if self._plugin_loader:
            await self._plugin_loader.teardown_all()
        if self._metrics_runner:
            await self._metrics_runner.cleanup()
        if self._db:
            await self._db.close()

        logger.info("quartermaster_stopped")

    async def run(self) -> None:
        """Start the application and wait for shutdown signal."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown_event.set)

        await self.start()
        await self._shutdown_event.wait()
        await self.stop()
