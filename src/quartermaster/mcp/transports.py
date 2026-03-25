"""Transport factory — config-driven MCP client transport selection.

Sits above the MCP SDK's transport implementations. Given a config
entry, produces the parameters needed to create an SDK transport
connection. The actual connection lifecycle is managed by the
MCPClientManager.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import structlog
from mcp.client.stdio import StdioServerParameters

from quartermaster.mcp.config import MCPClientEntry, TransportType

logger = structlog.get_logger()


class MCPTransportFactory:
    """Creates transport connection parameters from config entries."""

    def get_transport_context(
        self, entry: MCPClientEntry, server_name: str
    ) -> dict[str, Any]:
        """Build transport context dict for a config entry.

        Returns a dict with 'type' and transport-specific parameters
        that the MCPClientManager uses to establish connections.
        """
        match entry.transport:
            case TransportType.STREAMABLE_HTTP:
                return self._streamable_http_context(entry, server_name)
            case TransportType.SSE:
                return self._sse_context(entry, server_name)
            case TransportType.STDIO:
                return self._stdio_context(entry, server_name)

    def _streamable_http_context(
        self, entry: MCPClientEntry, server_name: str
    ) -> dict[str, Any]:
        headers = self._load_auth_headers(entry)
        return {
            "type": "streamable_http",
            "url": entry.url,
            "headers": headers,
            "server_name": server_name,
        }

    def _sse_context(
        self, entry: MCPClientEntry, server_name: str
    ) -> dict[str, Any]:
        headers = self._load_auth_headers(entry)
        return {
            "type": "sse",
            "url": entry.url,
            "headers": headers,
            "server_name": server_name,
        }

    def _stdio_context(
        self, entry: MCPClientEntry, server_name: str
    ) -> dict[str, Any]:
        assert entry.command is not None
        # Validate command exists
        if not shutil.which(entry.command):
            raise FileNotFoundError(
                f"stdio command not found: {entry.command}. "
                f"Ensure it is installed and available in PATH."
            )
        return {
            "type": "stdio",
            "server_params": StdioServerParameters(
                command=entry.command,
                args=entry.args,
            ),
            "server_name": server_name,
        }

    @staticmethod
    def _load_auth_headers(entry: MCPClientEntry) -> dict[str, str]:
        """Load auth token from file if configured."""
        headers: dict[str, str] = {}
        if entry.auth_token_file:
            token_path = Path(entry.auth_token_file)
            if token_path.exists():
                token = token_path.read_text().strip()
                headers["Authorization"] = f"Bearer {token}"
            else:
                logger.warning(
                    "mcp_auth_token_file_missing",
                    file=entry.auth_token_file,
                )
        return headers
