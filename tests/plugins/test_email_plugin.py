"""Tests for the Email plugin."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quartermaster.core.config import EmailAccountConfig, EmailConfig, QuartermasterConfig
from quartermaster.core.tools import ApprovalTier, ToolRegistry
from quartermaster.plugin.context import PluginContext


@pytest.fixture
def outlook_config() -> QuartermasterConfig:
    return QuartermasterConfig(
        email=EmailConfig(
            accounts={
                "fr-brian": EmailAccountConfig(
                    provider="outlook",
                    credential_file="credentials/outlook_brian.json",
                    label="FR Brian",
                ),
            }
        )
    )


@pytest.fixture
def outlook_ctx(outlook_config: QuartermasterConfig, mock_ctx: PluginContext) -> PluginContext:
    return PluginContext(
        config=outlook_config,
        events=mock_ctx.events,
        tools=ToolRegistry(events=mock_ctx.events),
    )


@pytest.fixture
def email_config() -> QuartermasterConfig:
    return QuartermasterConfig(
        email=EmailConfig(
            accounts={
                "personal": EmailAccountConfig(
                    provider="gmail",
                    credential_file="credentials/gmail_personal.json",
                    label="Personal Gmail",
                ),
                "fr": EmailAccountConfig(
                    provider="gmail",
                    credential_file="credentials/gmail_fr.json",
                    label="Friendly Robots",
                ),
            }
        )
    )


@pytest.fixture
def mock_ctx(email_config: QuartermasterConfig) -> PluginContext:
    events = MagicMock()
    events.emit = AsyncMock()
    events.subscribe = MagicMock()
    tools = ToolRegistry(events=events)
    return PluginContext(
        config=email_config,
        events=events,
        tools=tools,
    )


@pytest.mark.asyncio
async def test_plugin_registers_tools(mock_ctx: PluginContext) -> None:
    from plugins.email.plugin import EmailPlugin

    plugin = EmailPlugin()

    with patch("plugins.email.plugin.GmailProvider") as MockGmail:  # noqa: N806
        mock_provider = AsyncMock()
        mock_provider.account_name = "personal"
        mock_provider.label = "Personal Gmail"
        mock_provider.health_check = AsyncMock(return_value=True)
        MockGmail.return_value = mock_provider  # noqa: N806

        await plugin.setup(mock_ctx)

    tool_names = [t.name for t in mock_ctx.tools.list_tools()]
    assert "email.unread_summary" in tool_names
    assert "email.search" in tool_names
    assert "email.read" in tool_names
    assert "email.draft" in tool_names
    assert "email.send" in tool_names
    assert "email.reply" in tool_names


@pytest.mark.asyncio
async def test_send_is_confirm_tier(mock_ctx: PluginContext) -> None:
    from plugins.email.plugin import EmailPlugin

    plugin = EmailPlugin()

    with patch("plugins.email.plugin.GmailProvider") as MockGmail:  # noqa: N806
        mock_provider = AsyncMock()
        mock_provider.account_name = "personal"
        mock_provider.label = "Personal Gmail"
        mock_provider.health_check = AsyncMock(return_value=True)
        MockGmail.return_value = mock_provider  # noqa: N806

        await plugin.setup(mock_ctx)

    send_tool = mock_ctx.tools.get("email.send")
    assert send_tool is not None
    assert send_tool.approval_tier == ApprovalTier.CONFIRM

    reply_tool = mock_ctx.tools.get("email.reply")
    assert reply_tool is not None
    assert reply_tool.approval_tier == ApprovalTier.CONFIRM


@pytest.mark.asyncio
async def test_read_tools_are_autonomous(mock_ctx: PluginContext) -> None:
    from plugins.email.plugin import EmailPlugin

    plugin = EmailPlugin()

    with patch("plugins.email.plugin.GmailProvider") as MockGmail:  # noqa: N806
        mock_provider = AsyncMock()
        mock_provider.account_name = "personal"
        mock_provider.label = "Personal Gmail"
        mock_provider.health_check = AsyncMock(return_value=True)
        MockGmail.return_value = mock_provider  # noqa: N806

        await plugin.setup(mock_ctx)

    for name in ["email.unread_summary", "email.search", "email.read", "email.draft"]:
        tool = mock_ctx.tools.get(name)
        assert tool is not None, f"{name} not registered"
        assert tool.approval_tier == ApprovalTier.AUTONOMOUS, f"{name} should be autonomous"


@pytest.mark.asyncio
async def test_invalid_account_returns_error(mock_ctx: PluginContext) -> None:
    from plugins.email.plugin import EmailPlugin

    plugin = EmailPlugin()

    with patch("plugins.email.plugin.GmailProvider") as MockGmail:  # noqa: N806
        mock_provider = AsyncMock()
        mock_provider.account_name = "personal"
        mock_provider.label = "Personal Gmail"
        mock_provider.health_check = AsyncMock(return_value=True)
        MockGmail.return_value = mock_provider  # noqa: N806

        await plugin.setup(mock_ctx)

    result = await mock_ctx.tools.execute(  # noqa: E501
        "email.read", {"account": "nonexistent", "message_id": "m1"}
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_unread_summary_aggregates_all_accounts(mock_ctx: PluginContext) -> None:
    from plugins.email.plugin import EmailPlugin
    from quartermaster.email.models import EmailSummary

    plugin = EmailPlugin()

    mock_summaries_personal = [
        EmailSummary(  # noqa: E501
            id="p1", subject="Personal", sender="a@b.com", date=None, snippet="...", is_read=False
        ),
    ]
    mock_summaries_fr = [
        EmailSummary(  # noqa: E501
            id="f1", subject="FR", sender="c@d.com", date=None, snippet="...", is_read=False
        ),
    ]

    with patch("plugins.email.plugin.GmailProvider") as MockGmail:  # noqa: N806
        provider1 = AsyncMock()
        provider1.account_name = "personal"
        provider1.label = "Personal Gmail"
        provider1.health_check = AsyncMock(return_value=True)
        provider1.get_unread_summary = AsyncMock(return_value=mock_summaries_personal)

        provider2 = AsyncMock()
        provider2.account_name = "fr"
        provider2.label = "Friendly Robots"
        provider2.health_check = AsyncMock(return_value=True)
        provider2.get_unread_summary = AsyncMock(return_value=mock_summaries_fr)

        MockGmail.side_effect = [provider1, provider2]  # noqa: N806
        await plugin.setup(mock_ctx)

    # Call with no account — should aggregate
    result = await mock_ctx.tools.execute("email.unread_summary", {})
    assert "accounts" in result
    assert len(result["accounts"]) == 2


@pytest.mark.asyncio
async def test_health_all_ok(mock_ctx: PluginContext) -> None:
    """health() returns OK with rich detail dicts when all accounts healthy."""
    from plugins.email.plugin import EmailPlugin

    plugin = EmailPlugin()

    with patch("plugins.email.plugin.GmailProvider") as MockGmail:  # noqa: N806
        provider1 = AsyncMock()
        provider1.account_name = "personal"
        provider1.label = "Personal Gmail"
        provider1.provider_type = "gmail"
        provider1.health_check = AsyncMock(return_value=True)

        provider2 = AsyncMock()
        provider2.account_name = "fr"
        provider2.label = "Friendly Robots"
        provider2.provider_type = "gmail"
        provider2.health_check = AsyncMock(return_value=True)

        MockGmail.side_effect = [provider1, provider2]
        await plugin.setup(mock_ctx)

    report = await plugin.health()
    assert report.status.value == "ok"
    assert "personal" in report.details
    assert report.details["personal"]["status"] == "ok"
    assert report.details["personal"]["label"] == "Personal Gmail"
    assert report.details["personal"]["provider"] == "gmail"


@pytest.mark.asyncio
async def test_health_degraded(mock_ctx: PluginContext) -> None:
    """health() returns DEGRADED when one account fails health_check."""
    from plugins.email.plugin import EmailPlugin

    plugin = EmailPlugin()

    with patch("plugins.email.plugin.GmailProvider") as MockGmail:  # noqa: N806
        provider1 = AsyncMock()
        provider1.account_name = "personal"
        provider1.label = "Personal Gmail"
        provider1.provider_type = "gmail"
        # healthy at connect, then fails health_check
        provider1.health_check = AsyncMock(return_value=False)

        provider2 = AsyncMock()
        provider2.account_name = "fr"
        provider2.label = "Friendly Robots"
        provider2.provider_type = "gmail"
        provider2.health_check = AsyncMock(return_value=True)

        MockGmail.side_effect = [provider1, provider2]
        await plugin.setup(mock_ctx)

    report = await plugin.health()
    assert report.status.value == "degraded"
    assert report.details["personal"]["status"] == "error"
    assert report.details["fr"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_down_no_providers(mock_ctx: PluginContext) -> None:
    """health() returns DOWN when no providers connected."""
    from plugins.email.plugin import EmailPlugin

    # Use config with no accounts so no providers connect
    empty_config = QuartermasterConfig(email=EmailConfig(accounts={}))
    empty_ctx = PluginContext(
        config=empty_config,
        events=mock_ctx.events,
        tools=mock_ctx.tools,
    )

    plugin = EmailPlugin()
    await plugin.setup(empty_ctx)

    report = await plugin.health()
    assert report.status.value == "down"


@pytest.mark.asyncio
async def test_health_reports_correct_provider_type(outlook_ctx: PluginContext) -> None:
    from plugins.email.plugin import EmailPlugin
    plugin = EmailPlugin()
    with patch("plugins.email.plugin.OutlookProvider") as MockOutlook:  # noqa: N806
        provider = AsyncMock()
        provider.account_name = "fr-brian"
        provider.label = "FR Brian"
        provider.provider_type = "outlook"
        provider.health_check = AsyncMock(return_value=True)
        MockOutlook.return_value = provider
        await plugin.setup(outlook_ctx)
    report = await plugin.health()
    assert report.details["fr-brian"]["provider"] == "outlook"
