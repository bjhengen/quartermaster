"""MCP server authentication — bearer token + IP allowlist.

Designed as pluggable middleware. The current implementation uses
bearer tokens. Future implementations (mTLS, OAuth) can implement
the same interface.
"""

from __future__ import annotations

import hmac
import ipaddress
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from quartermaster.core.metrics import mcp_server_auth_failures_total

# Type alias for the Starlette call_next callable used in BaseHTTPMiddleware
_CallNext = Callable[[Request], Awaitable[Response]]

logger = structlog.get_logger()


class BearerTokenAuth:
    """Bearer token + IP allowlist authentication."""

    def __init__(self, token: str, allowed_hosts: list[str]) -> None:
        self._token = token
        self._allowed_hosts = set(allowed_hosts)
        self._networks = self._parse_networks(allowed_hosts)

    def as_middleware_class(self) -> type[BaseHTTPMiddleware]:
        """Return a Starlette middleware class bound to this auth instance."""
        auth = self

        class AuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next: _CallNext) -> Response:
                return await auth.check_request(request, call_next)

        return AuthMiddleware

    async def check_request(self, request: Request, call_next: _CallNext) -> Response:
        """Validate auth token and IP allowlist."""
        client_ip = request.client.host if request.client else "unknown"

        # Check IP allowlist (if configured)
        if self._allowed_hosts and not self._check_host(client_ip):
            logger.warning("mcp_auth_ip_rejected", client_ip=client_ip)
            mcp_server_auth_failures_total.inc()
            return Response(status_code=403)

        # Check bearer token
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning("mcp_auth_missing_token", client_ip=client_ip)
            mcp_server_auth_failures_total.inc()
            return Response(status_code=401)

        token = auth_header[7:]  # Strip "Bearer "
        if not hmac.compare_digest(token, self._token):
            logger.warning("mcp_auth_invalid_token", client_ip=client_ip)
            mcp_server_auth_failures_total.inc()
            return Response(status_code=401)

        return await call_next(request)

    def _check_host(self, client_host: str) -> bool:
        """Check if client host is in the allowlist (IP networks or literal hostnames)."""
        # Literal hostname match (e.g. "testclient", "localhost")
        if client_host in self._allowed_hosts:
            return True
        # IP / CIDR range match
        try:
            addr = ipaddress.ip_address(client_host)
            return any(addr in network for network in self._networks)
        except ValueError:
            return False

    @staticmethod
    def _parse_networks(hosts: list[str]) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        """Parse host strings into network objects."""
        networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for host in hosts:
            try:
                networks.append(ipaddress.ip_network(host, strict=False))
            except ValueError:
                logger.warning("mcp_auth_invalid_host", host=host)
        return networks
