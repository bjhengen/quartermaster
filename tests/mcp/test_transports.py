"""Tests for MCP transport factory."""

import pytest
from typing import Any

from quartermaster.mcp.config import MCPClientEntry, TransportType
from quartermaster.mcp.transports import MCPTransportFactory


def test_factory_selects_streamable_http() -> None:
    """Factory returns streamable_http transport context for HTTP entries."""
    entry = MCPClientEntry(
        transport=TransportType.STREAMABLE_HTTP,
        url="http://localhost:9200/mcp",
        default_approval_tier="confirm",
    )
    factory = MCPTransportFactory()
    ctx = factory.get_transport_context(entry, server_name="test")
    assert ctx is not None
    assert ctx["type"] == "streamable_http"


def test_factory_selects_sse() -> None:
    """Factory returns SSE transport context for SSE entries."""
    entry = MCPClientEntry(
        transport=TransportType.SSE,
        url="http://example.com",
        default_approval_tier="confirm",
    )
    factory = MCPTransportFactory()
    ctx = factory.get_transport_context(entry, server_name="test")
    assert ctx is not None
    assert ctx["type"] == "sse"


def test_factory_selects_stdio() -> None:
    """Factory returns stdio transport context for stdio entries."""
    entry = MCPClientEntry(
        transport=TransportType.STDIO,
        command="echo",
        args=["hello"],
        default_approval_tier="confirm",
    )
    factory = MCPTransportFactory()
    ctx = factory.get_transport_context(entry, server_name="test")
    assert ctx is not None
    assert ctx["type"] == "stdio"


def test_factory_loads_auth_token(tmp_path: Any) -> None:
    """Factory reads auth token from file for HTTP transports."""
    token_file = tmp_path / "token"
    token_file.write_text("my-secret-token")

    entry = MCPClientEntry(
        transport=TransportType.STREAMABLE_HTTP,
        url="http://localhost:9200/mcp",
        auth_token_file=str(token_file),
        default_approval_tier="confirm",
    )
    factory = MCPTransportFactory()
    ctx = factory.get_transport_context(entry, server_name="test")
    assert ctx["headers"]["Authorization"] == "Bearer my-secret-token"


def test_factory_no_auth_token() -> None:
    """Factory works without auth token."""
    entry = MCPClientEntry(
        transport=TransportType.STREAMABLE_HTTP,
        url="http://localhost:9200/mcp",
        default_approval_tier="confirm",
    )
    factory = MCPTransportFactory()
    ctx = factory.get_transport_context(entry, server_name="test")
    assert "Authorization" not in ctx.get("headers", {})


def test_factory_validates_stdio_command_exists() -> None:
    """Factory checks that stdio command exists on the system."""
    entry = MCPClientEntry(
        transport=TransportType.STDIO,
        command="nonexistent_binary_xyz_12345",
        default_approval_tier="confirm",
    )
    factory = MCPTransportFactory()
    with pytest.raises(FileNotFoundError, match="nonexistent_binary_xyz_12345"):
        factory.get_transport_context(entry, server_name="test")
