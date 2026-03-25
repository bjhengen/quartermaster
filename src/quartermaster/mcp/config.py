"""MCP configuration models."""

from enum import StrEnum

from pydantic import BaseModel, model_validator


class TransportType(StrEnum):
    """MCP transport types."""

    STREAMABLE_HTTP = "streamable_http"
    SSE = "sse"
    STDIO = "stdio"


class ToolOverride(BaseModel):
    """Per-tool configuration override."""

    approval_tier: str | None = None
    enabled: bool = True


class MCPServerConfig(BaseModel):
    """MCP server configuration."""

    enabled: bool = True
    port: int = 9200
    bind: str = "127.0.0.1"
    auth_token_file: str
    allowed_hosts: list[str] = []
    approval_chat_id: str | None = None


class MCPClientEntry(BaseModel):
    """Configuration for a single MCP server connection."""

    transport: TransportType
    url: str | None = None
    command: str | None = None
    args: list[str] = []
    auth_token_file: str | None = None
    default_approval_tier: str = "confirm"
    tool_overrides: dict[str, ToolOverride] = {}
    namespace: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def validate_transport_params(self) -> "MCPClientEntry":
        """Validate that required fields are set for the transport type."""
        if self.transport == TransportType.STDIO:
            if not self.command:
                raise ValueError("stdio transport requires 'command'")
        elif self.transport in (TransportType.STREAMABLE_HTTP, TransportType.SSE) and not self.url:
            raise ValueError(f"{self.transport} transport requires 'url'")
        return self


class MCPConfig(BaseModel):
    """Root MCP configuration."""

    server: MCPServerConfig | None = None
    clients: dict[str, MCPClientEntry] = {}
