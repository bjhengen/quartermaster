"""Tests for MCP configuration models."""

import pytest
from pydantic import ValidationError

from quartermaster.mcp.config import (
    MCPClientEntry,
    MCPConfig,
    MCPServerConfig,
    ToolOverride,
    TransportType,
)


def test_transport_type_enum() -> None:
    assert TransportType.STREAMABLE_HTTP == "streamable_http"
    assert TransportType.SSE == "sse"
    assert TransportType.STDIO == "stdio"


def test_server_config_defaults() -> None:
    cfg = MCPServerConfig(auth_token_file="/app/credentials/token")
    assert cfg.enabled is True
    assert cfg.port == 9200
    assert cfg.bind == "127.0.0.1"
    assert cfg.allowed_hosts == []
    assert cfg.approval_chat_id is None


def test_server_config_custom() -> None:
    cfg = MCPServerConfig(
        enabled=True,
        port=9300,
        bind="0.0.0.0",
        auth_token_file="/app/credentials/token",
        allowed_hosts=["127.0.0.1", "192.168.1.0/24"],
        approval_chat_id="123456789",
    )
    assert cfg.port == 9300
    assert cfg.bind == "0.0.0.0"
    assert len(cfg.allowed_hosts) == 2
    assert cfg.approval_chat_id == "123456789"


def test_client_entry_streamable_http() -> None:
    entry = MCPClientEntry(
        transport=TransportType.STREAMABLE_HTTP,
        url="http://localhost:9200/mcp",
        default_approval_tier="confirm",
    )
    assert entry.transport == TransportType.STREAMABLE_HTTP
    assert entry.url == "http://localhost:9200/mcp"
    assert entry.enabled is True
    assert entry.namespace is None
    assert entry.command is None


def test_client_entry_sse() -> None:
    entry = MCPClientEntry(
        transport=TransportType.SSE,
        url="http://memory.friendly-robots.com",
        auth_token_file="/app/credentials/token",
        default_approval_tier="autonomous",
    )
    assert entry.transport == TransportType.SSE
    assert entry.auth_token_file == "/app/credentials/token"


def test_client_entry_stdio() -> None:
    entry = MCPClientEntry(
        transport=TransportType.STDIO,
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/app/data"],
        default_approval_tier="confirm",
    )
    assert entry.transport == TransportType.STDIO
    assert entry.command == "npx"
    assert len(entry.args) == 3


def test_client_entry_stdio_requires_command() -> None:
    with pytest.raises(ValidationError):
        MCPClientEntry(
            transport=TransportType.STDIO,
            default_approval_tier="confirm",
        )


def test_client_entry_http_requires_url() -> None:
    with pytest.raises(ValidationError):
        MCPClientEntry(
            transport=TransportType.STREAMABLE_HTTP,
            default_approval_tier="confirm",
        )


def test_tool_override() -> None:
    override = ToolOverride(approval_tier="autonomous")
    assert override.approval_tier == "autonomous"
    assert override.enabled is True


def test_client_entry_with_overrides() -> None:
    entry = MCPClientEntry(
        transport=TransportType.SSE,
        url="http://example.com",
        default_approval_tier="autonomous",
        tool_overrides={
            "log_lesson": ToolOverride(approval_tier="confirm"),
            "dangerous_tool": ToolOverride(enabled=False),
        },
    )
    assert entry.tool_overrides["log_lesson"].approval_tier == "confirm"
    assert entry.tool_overrides["dangerous_tool"].enabled is False


def test_mcp_config_defaults() -> None:
    cfg = MCPConfig()
    assert cfg.server is None
    assert cfg.clients == {}


def test_mcp_config_full() -> None:
    cfg = MCPConfig(
        server=MCPServerConfig(
            auth_token_file="/app/credentials/token",
            approval_chat_id="123456789",
        ),
        clients={
            "test-server": MCPClientEntry(
                transport=TransportType.STREAMABLE_HTTP,
                url="http://localhost:8080",
                default_approval_tier="confirm",
            ),
        },
    )
    assert cfg.server is not None
    assert "test-server" in cfg.clients


def test_mcp_config_in_quartermaster_config() -> None:
    """MCPConfig is properly nested in QuartermasterConfig."""
    from quartermaster.core.config import QuartermasterConfig

    config = QuartermasterConfig(
        database={"dsn": "x", "user": "x", "password": "x"},
    )
    assert config.mcp is not None
    assert config.mcp.server is None
    assert config.mcp.clients == {}
