"""Commands plugin — /status, /models, /help, /spend, /new."""

from typing import Any

import structlog

from quartermaster.plugin.base import QuartermasterPlugin
from quartermaster.plugin.context import PluginContext
from quartermaster.plugin.health import HealthReport, HealthStatus
from quartermaster.transport.types import InboundMessage, OutboundMessage

logger = structlog.get_logger()


class CommandsPlugin(QuartermasterPlugin):
    """Handles bot commands."""

    name = "commands"
    version = "0.1.0"
    dependencies: list[str] = []

    def __init__(self) -> None:
        self._ctx: PluginContext | None = None
        self.commands: dict[str, str] = {
            "status": "System status overview",
            "models": "Show available LLM models",
            "help": "Show this help message",
            "spend": "Show API spend for this month",
            "new": "Start a new conversation",
        }

    async def setup(self, ctx: PluginContext) -> None:
        self._ctx = ctx
        ctx.events.subscribe("message.received", self._handle_message)
        logger.info("commands_plugin_ready")

    async def teardown(self) -> None:
        pass

    async def health(self) -> HealthReport:
        return HealthReport(status=HealthStatus.OK)

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle commands from incoming messages."""
        assert self._ctx is not None
        message: InboundMessage = data["message"]

        if not message.text.startswith("/"):
            return

        parts = message.text.split()
        command = parts[0][1:].lower()  # Strip / prefix

        handler = {
            "status": self._cmd_status,
            "models": self._cmd_models,
            "help": self._cmd_help,
            "spend": self._cmd_spend,
            "new": self._cmd_new,
        }.get(command)

        if handler:
            await handler(message)

    async def _cmd_status(self, msg: InboundMessage) -> None:
        """System status overview."""
        assert self._ctx is not None
        status_lines = ["**Quartermaster Status**\n"]

        # LLM status
        local_status = await self._ctx.llm.get_local_status()
        status_lines.append(f"• LLM: {local_status.value}")

        # Budget
        if self._ctx.usage:
            summary = await self._ctx.usage.get_spend_summary()
            status_lines.append(
                f"• Budget: ${summary['monthly_spend']}/{summary['monthly_budget']}"
                f" ({summary['percent_used']}%)"
            )

        # MCP status
        if self._ctx.mcp_client:
            status_lines.append("\n**MCP Clients:**")
            for name, status in self._ctx.mcp_client.get_server_statuses().items():
                status_lines.append(
                    f"  {name}: {status['status']}"
                    f" — {status.get('tool_count', 0)} tools"
                )

        # MCP server status
        tools = self._ctx.tools.list_tools()
        tool_count = len(tools)
        if hasattr(self._ctx, "config") and self._ctx.config.mcp.server.enabled:
            port = self._ctx.config.mcp.server.port
            status_lines.append(
                f"\n**MCP Server:**\n"
                f"  Streamable HTTP on :{port} — {tool_count} tools exposed"
            )

        # Plugin health (email, etc.)
        if self._ctx.plugin_loader:
            health_reports = await self._ctx.plugin_loader.check_health()
            for plugin_name, report in health_reports.items():
                if not report.details:
                    continue
                status_lines.append(f"\n**{plugin_name.title()}:**")
                for detail_name, detail in report.details.items():
                    if isinstance(detail, dict):
                        label = detail.get("label", detail_name)
                        provider = detail.get("provider", "")
                        acct_status = detail.get("status", "unknown")
                        error = detail.get("error", "")
                        line = f"  {label} ({provider}): {acct_status}"
                        if error:
                            line += f" — {error}"
                        status_lines.append(line)

        await self._send(msg, "\n".join(status_lines))

    async def _cmd_models(self, msg: InboundMessage) -> None:
        """Show available LLM models."""
        assert self._ctx is not None
        local_status = await self._ctx.llm.get_local_status()
        lines = [
            "**Available Models**\n",
            f"• Local (llama-swap): {local_status.value}",
            "• Anthropic: claude-sonnet-4, claude-haiku-4.5",
        ]
        await self._send(msg, "\n".join(lines))

    async def _cmd_help(self, msg: InboundMessage) -> None:
        """Show help message."""
        lines = ["**Commands**\n"]
        for cmd, desc in self.commands.items():
            lines.append(f"/{cmd} — {desc}")
        await self._send(msg, "\n".join(lines))

    async def _cmd_spend(self, msg: InboundMessage) -> None:
        """Show API spend."""
        assert self._ctx is not None
        if not self._ctx.usage:
            await self._send(msg, "Usage tracking not configured.")
            return
        summary = await self._ctx.usage.get_spend_summary()
        text = (
            f"**API Spend (This Month)**\n"
            f"• Spent: ${summary['monthly_spend']:.2f}\n"
            f"• Budget: ${summary['monthly_budget']:.2f}\n"
            f"• Used: {summary['percent_used']}%\n"
            f"• Status: {summary['status']}"
        )
        await self._send(msg, text)

    async def _cmd_new(self, msg: InboundMessage) -> None:
        """Start a new conversation."""
        assert self._ctx is not None
        await self._ctx.conversation.force_new_conversation(
            msg.transport.value, msg.chat_id
        )
        await self._send(msg, "New conversation started.")

    async def _send(self, msg: InboundMessage, text: str) -> None:
        """Send a response message."""
        assert self._ctx is not None
        await self._ctx.transport.send(
            OutboundMessage(
                transport=msg.transport,
                chat_id=msg.chat_id,
                text=text,
            )
        )
