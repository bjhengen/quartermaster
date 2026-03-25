"""Tests for MCP server authentication middleware."""

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from quartermaster.mcp.auth import BearerTokenAuth


def _make_app(auth: BearerTokenAuth) -> Starlette:
    """Create a test Starlette app with auth middleware."""
    async def hello(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/test", hello)])
    app.add_middleware(auth.as_middleware_class())
    return app


def test_valid_bearer_token() -> None:
    auth = BearerTokenAuth(token="secret-token-123", allowed_hosts=[])
    app = _make_app(auth)
    client = TestClient(app)

    response = client.get("/test", headers={"Authorization": "Bearer secret-token-123"})
    assert response.status_code == 200
    assert response.text == "ok"


def test_missing_auth_header() -> None:
    auth = BearerTokenAuth(token="secret-token-123", allowed_hosts=[])
    app = _make_app(auth)
    client = TestClient(app)

    response = client.get("/test")
    assert response.status_code == 401


def test_wrong_token() -> None:
    auth = BearerTokenAuth(token="secret-token-123", allowed_hosts=[])
    app = _make_app(auth)
    client = TestClient(app)

    response = client.get("/test", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


def test_malformed_auth_header() -> None:
    auth = BearerTokenAuth(token="secret-token-123", allowed_hosts=[])
    app = _make_app(auth)
    client = TestClient(app)

    response = client.get("/test", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401


def test_ip_allowlist_accepted() -> None:
    auth = BearerTokenAuth(
        token="secret-token-123",
        # Starlette TestClient reports host as "testclient" (not a real IP)
        allowed_hosts=["testclient", "127.0.0.1", "192.168.1.0/24"],
    )
    app = _make_app(auth)
    client = TestClient(app)

    response = client.get("/test", headers={"Authorization": "Bearer secret-token-123"})
    assert response.status_code == 200


def test_ip_allowlist_rejected() -> None:
    auth = BearerTokenAuth(
        token="secret-token-123",
        allowed_hosts=["10.0.0.0/8"],  # TestClient is 127.0.0.1, not in this range
    )
    app = _make_app(auth)
    client = TestClient(app)

    response = client.get("/test", headers={"Authorization": "Bearer secret-token-123"})
    assert response.status_code == 403


def test_empty_allowlist_allows_all() -> None:
    auth = BearerTokenAuth(token="secret-token-123", allowed_hosts=[])
    app = _make_app(auth)
    client = TestClient(app)

    response = client.get("/test", headers={"Authorization": "Bearer secret-token-123"})
    assert response.status_code == 200
