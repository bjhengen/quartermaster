"""Email plugin — tool registration and account routing."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog

from quartermaster.core.metrics import email_operation_duration, email_operations_total
from quartermaster.core.tools import ApprovalTier
from quartermaster.email.gmail import GmailProvider
from quartermaster.plugin.base import QuartermasterPlugin
from quartermaster.plugin.health import HealthReport, HealthStatus

if TYPE_CHECKING:
    from quartermaster.email.models import EmailSummary
    from quartermaster.plugin.context import PluginContext

logger = structlog.get_logger()


class EmailPlugin(QuartermasterPlugin):
    """Provides email tools (read, search, draft, send, reply) for all configured accounts."""

    name = "email"
    version = "0.1.0"
    dependencies: list[str] = []

    def __init__(self) -> None:
        self._providers: dict[str, GmailProvider] = {}

    @staticmethod
    def _get_provider_cls(provider_name: str) -> type | None:
        """Look up a provider class by name at call time (not import time).

        Resolved at call time so that unittest.mock patches on
        ``plugins.email.plugin.GmailProvider`` take effect correctly.
        """
        mapping: dict[str, type] = {
            "gmail": GmailProvider,
        }
        return mapping.get(provider_name)

    async def setup(self, ctx: PluginContext) -> None:
        """Instantiate providers for each configured account and register tools."""
        email_cfg = ctx.config.email

        for account_name, account_cfg in email_cfg.accounts.items():
            provider_cls = self._get_provider_cls(account_cfg.provider)
            if provider_cls is None:
                logger.warning(
                    "email_plugin_unknown_provider",
                    account=account_name,
                    provider=account_cfg.provider,
                )
                continue

            provider: GmailProvider = provider_cls(
                account_name=account_name,
                label=account_cfg.label,
                credential_file=account_cfg.credential_file,
            )

            try:
                await provider.connect()
                self._providers[account_name] = provider
                logger.info(
                    "email_plugin_account_connected",
                    account=account_name,
                    label=account_cfg.label,
                )
            except Exception as exc:
                logger.error(
                    "email_plugin_account_connect_failed",
                    account=account_name,
                    error=str(exc),
                )

        self._register_tools(ctx)
        logger.info("email_plugin_ready", accounts=list(self._providers.keys()))

    def _register_tools(self, ctx: PluginContext) -> None:
        """Register all email tools into the ToolRegistry."""
        account_names = list(self._providers.keys())
        account_enum = account_names if account_names else ["(none)"]

        ctx.tools.register(
            name="email.unread_summary",
            description=(
                "Return a summary of unread emails. "
                "If 'account' is omitted, aggregates all configured accounts."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "account": {
                        "type": "string",
                        "enum": account_enum,
                        "description": "Account name to query. Omit to aggregate all.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results per account (default 20).",
                        "default": 20,
                    },
                },
                "required": [],
            },
            handler=self._handle_unread_summary,
            approval_tier=ApprovalTier.AUTONOMOUS,
        )

        ctx.tools.register(
            name="email.search",
            description=(
                "Search emails using a Gmail query string. "
                "If 'account' is omitted, searches all configured accounts."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Gmail search query (e.g. 'from:boss@example.com').",
                    },
                    "account": {
                        "type": "string",
                        "enum": account_enum,
                        "description": "Account name to search. Omit to search all accounts.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results per account (default 10).",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
            handler=self._handle_search,
            approval_tier=ApprovalTier.AUTONOMOUS,
        )

        ctx.tools.register(
            name="email.read",
            description="Read the full content of a specific email message by ID.",
            parameters={
                "type": "object",
                "properties": {
                    "account": {
                        "type": "string",
                        "enum": account_enum,
                        "description": "Account name that owns the message.",
                    },
                    "message_id": {
                        "type": "string",
                        "description": "The Gmail message ID to read.",
                    },
                },
                "required": ["account", "message_id"],
            },
            handler=self._handle_read,
            approval_tier=ApprovalTier.AUTONOMOUS,
        )

        ctx.tools.register(
            name="email.draft",
            description="Save a new email as a draft (does not send).",
            parameters={
                "type": "object",
                "properties": {
                    "account": {
                        "type": "string",
                        "enum": account_enum,
                        "description": "Account to draft from.",
                    },
                    "to": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string", "description": "Email subject."},
                    "body": {"type": "string", "description": "Plain-text email body."},
                    "cc": {
                        "type": "string",
                        "description": "Optional CC email address(es).",
                    },
                },
                "required": ["account", "to", "subject", "body"],
            },
            handler=self._handle_draft,
            approval_tier=ApprovalTier.AUTONOMOUS,
        )

        ctx.tools.register(
            name="email.send",
            description="Compose and send a new email. Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "account": {
                        "type": "string",
                        "enum": account_enum,
                        "description": "Account to send from.",
                    },
                    "to": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string", "description": "Email subject."},
                    "body": {"type": "string", "description": "Plain-text email body."},
                    "cc": {
                        "type": "string",
                        "description": "Optional CC email address(es).",
                    },
                },
                "required": ["account", "to", "subject", "body"],
            },
            handler=self._handle_send,
            approval_tier=ApprovalTier.CONFIRM,
        )

        ctx.tools.register(
            name="email.reply",
            description="Reply to an existing email message. Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "account": {
                        "type": "string",
                        "enum": account_enum,
                        "description": "Account that owns the original message.",
                    },
                    "message_id": {
                        "type": "string",
                        "description": "The Gmail message ID to reply to.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Plain-text reply body.",
                    },
                },
                "required": ["account", "message_id", "body"],
            },
            handler=self._handle_reply,
            approval_tier=ApprovalTier.CONFIRM,
        )

    # -----------------------------------------------------------------------
    # Health
    # -----------------------------------------------------------------------

    async def health(self) -> HealthReport:
        """Return health based on live health_check() calls to each provider."""
        if not self._providers:
            return HealthReport(
                status=HealthStatus.DOWN,
                message="No email accounts connected.",
            )

        results: dict[str, bool] = {}
        for account_name, provider in self._providers.items():
            results[account_name] = await provider.health_check()

        healthy = [k for k, v in results.items() if v]
        unhealthy = [k for k, v in results.items() if not v]

        if len(unhealthy) == 0:
            return HealthReport(
                status=HealthStatus.OK,
                message=f"All {len(healthy)} account(s) healthy.",
                details=results,
            )
        elif len(healthy) == 0:
            return HealthReport(
                status=HealthStatus.DOWN,
                message=f"All {len(unhealthy)} account(s) are down.",
                details=results,
            )
        else:
            return HealthReport(
                status=HealthStatus.DEGRADED,
                message=f"{len(healthy)} healthy, {len(unhealthy)} down.",
                details=results,
            )

    async def teardown(self) -> None:
        self._providers.clear()

    # -----------------------------------------------------------------------
    # Metrics helper
    # -----------------------------------------------------------------------

    async def _timed_operation(
        self,
        account: str,
        operation: str,
        coro: Any,
    ) -> Any:
        """Execute a coroutine, recording duration and success/failure metrics."""
        start = time.monotonic()
        status = "success"
        try:
            result = await coro
            return result
        except Exception:
            status = "error"
            raise
        finally:
            elapsed = time.monotonic() - start
            email_operations_total.labels(
                account=account, operation=operation, status=status
            ).inc()
            email_operation_duration.labels(
                account=account, operation=operation
            ).observe(elapsed)

    # -----------------------------------------------------------------------
    # Serialisation helper
    # -----------------------------------------------------------------------

    @staticmethod
    def _serialize_summaries(
        result: list[EmailSummary] | dict[str, Any],
        account: str,
    ) -> dict[str, Any]:
        """Wrap a list[EmailSummary] (or an error dict) into a consistent dict."""
        if isinstance(result, dict):
            # Already an error dict
            return result
        serialized = [s.model_dump(mode="json") for s in result]
        return {
            "account": account,
            "summaries": serialized,
            "count": len(serialized),
        }

    # -----------------------------------------------------------------------
    # Tool handlers
    # -----------------------------------------------------------------------

    def _resolve_account(
        self, params: dict[str, Any]
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Return (account_name, None) or (None, error_dict) for account routing."""
        account = params.get("account")
        if account is None:
            return None, None
        if account not in self._providers:
            known = list(self._providers.keys())
            return None, {"error": f"Unknown account '{account}'. Known accounts: {known}"}
        return account, None

    async def _handle_unread_summary(self, params: dict[str, Any]) -> dict[str, Any]:
        account, error = self._resolve_account(params)
        if error:
            return error

        max_results: int = params.get("max_results", 20)

        if account is not None:
            # Single account
            provider = self._providers[account]
            result = await self._timed_operation(
                account,
                "unread_summary",
                provider.get_unread_summary(max_results=max_results),
            )
            return self._serialize_summaries(result, account)

        # Aggregate all accounts
        account_results = []
        for acc_name, provider in self._providers.items():
            try:
                summaries = await self._timed_operation(
                    acc_name,
                    "unread_summary",
                    provider.get_unread_summary(max_results=max_results),
                )
                account_results.append(self._serialize_summaries(summaries, acc_name))
            except Exception as exc:
                account_results.append({
                    "account": acc_name,
                    "error": str(exc),
                    "summaries": [],
                    "count": 0,
                })

        total = sum(r.get("count", 0) for r in account_results)
        return {"accounts": account_results, "total": total}

    async def _handle_search(self, params: dict[str, Any]) -> dict[str, Any]:
        query: str = params.get("query", "")
        max_results: int = params.get("max_results", 10)
        account, error = self._resolve_account(params)
        if error:
            return error

        if account is not None:
            # Single account
            provider = self._providers[account]
            result = await self._timed_operation(
                account,
                "search",
                provider.search(query, max_results=max_results),
            )
            return self._serialize_summaries(result, account)

        # Aggregate all accounts
        account_results = []
        for acc_name, provider in self._providers.items():
            try:
                summaries = await self._timed_operation(
                    acc_name,
                    "search",
                    provider.search(query, max_results=max_results),
                )
                account_results.append(self._serialize_summaries(summaries, acc_name))
            except Exception as exc:
                account_results.append({
                    "account": acc_name,
                    "error": str(exc),
                    "summaries": [],
                    "count": 0,
                })

        total = sum(r.get("count", 0) for r in account_results)
        return {"accounts": account_results, "total": total}

    async def _handle_read(self, params: dict[str, Any]) -> dict[str, Any]:
        account, error = self._resolve_account(params)
        if error:
            return error
        if account is None:
            return {"error": "Parameter 'account' is required for email.read."}

        message_id: str = params.get("message_id", "")
        provider = self._providers[account]
        message = await self._timed_operation(
            account,
            "read",
            provider.read(message_id),
        )
        return message.model_dump(mode="json")

    async def _handle_draft(self, params: dict[str, Any]) -> dict[str, Any]:
        account, error = self._resolve_account(params)
        if error:
            return error
        if account is None:
            return {"error": "Parameter 'account' is required for email.draft."}

        provider = self._providers[account]
        result = await self._timed_operation(
            account,
            "draft",
            provider.draft(
                to=params["to"],
                subject=params["subject"],
                body=params["body"],
                cc=params.get("cc"),
            ),
        )
        return result

    async def _handle_send(self, params: dict[str, Any]) -> dict[str, Any]:
        account, error = self._resolve_account(params)
        if error:
            return error
        if account is None:
            return {"error": "Parameter 'account' is required for email.send."}

        provider = self._providers[account]
        result = await self._timed_operation(
            account,
            "send",
            provider.send(
                to=params["to"],
                subject=params["subject"],
                body=params["body"],
                cc=params.get("cc"),
            ),
        )
        return result

    async def _handle_reply(self, params: dict[str, Any]) -> dict[str, Any]:
        account, error = self._resolve_account(params)
        if error:
            return error
        if account is None:
            return {"error": "Parameter 'account' is required for email.reply."}

        message_id: str = params.get("message_id", "")
        body: str = params.get("body", "")
        provider = self._providers[account]
        result = await self._timed_operation(
            account,
            "reply",
            provider.reply(message_id=message_id, body=body),
        )
        return result
