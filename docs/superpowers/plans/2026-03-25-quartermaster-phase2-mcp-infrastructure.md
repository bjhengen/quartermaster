# Quartermaster Phase 2 — MCP Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bidirectional MCP infrastructure — Quartermaster as both MCP client (consuming external tools) and MCP server (exposing tools to Claude Code).

**Architecture:** Transport-agnostic MCP layer using the official `mcp` Python SDK (v1.26.0). A bridge module translates between MCP tool schemas and QM's ToolDefinition. The MCP client manager connects to configured servers and registers their tools into the existing Tool Registry with server-prefix namespacing. The MCP server exposes all registered tools via Streamable HTTP with bearer token + IP allowlist auth.

**Tech Stack:** `mcp>=1.0.0,<2.0.0` (bundles starlette, uvicorn, httpx-sse), Python 3.13, Pydantic v2, structlog, prometheus-client, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-25-quartermaster-phase2-mcp-infrastructure.md`

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `src/quartermaster/mcp/__init__.py` | Package init, re-exports |
| `src/quartermaster/mcp/config.py` | `MCPConfig`, `MCPServerConfig`, `MCPClientEntry` Pydantic models |
| `src/quartermaster/mcp/bridge.py` | Bidirectional MCP ↔ QM ToolDefinition translation |
| `src/quartermaster/mcp/auth.py` | Bearer token + IP allowlist ASGI middleware |
| `src/quartermaster/mcp/transports.py` | Transport factory — config → connected SDK session |
| `src/quartermaster/mcp/client.py` | `MCPClientManager` — connects to servers, bridges tools |
| `src/quartermaster/mcp/server.py` | `MCPServer` — Starlette/uvicorn ASGI app exposing tools |
| `tests/mcp/__init__.py` | Test package init |
| `tests/mcp/test_config.py` | Config model validation tests |
| `tests/mcp/test_bridge.py` | Schema translation tests |
| `tests/mcp/test_auth.py` | Auth middleware tests |
| `tests/mcp/test_transports.py` | Transport factory tests |
| `tests/mcp/test_client.py` | Client manager tests |
| `tests/mcp/test_server.py` | Server tests |
| `tests/mcp/test_integration.py` | Loopback integration test |
| `tests/mcp/conftest.py` | Shared MCP test fixtures |
| `tests/fixtures/echo_server.py` | Minimal stdio MCP test server |

### Modified Files

| File | Changes |
|------|---------|
| `src/quartermaster/core/tools.py` | Add `source` field, `unregister()`, `list_by_source()`, optional `EventBus`, `is_remote` property |
| `src/quartermaster/core/config.py` | Add `MCPConfig` to `QuartermasterConfig` |
| `src/quartermaster/core/app.py` | Wire MCP client + server into startup/shutdown |
| `src/quartermaster/core/metrics.py` | Add MCP client/server Prometheus metrics |
| `src/quartermaster/plugin/context.py` | Add optional `mcp_client` field |
| `plugins/commands/plugin.py` | Add MCP status to `/status` command output |
| `config/settings.example.yaml` | Add `mcp` section |
| `requirements.txt` | Add `mcp>=1.0.0,<2.0.0` |
| `tests/core/test_tools.py` | Update for new constructor, add unregister/source tests |

---

## Task 1: Add `mcp` dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add mcp to requirements.txt**

Add after the `croniter` line:

```
mcp>=1.0.0,<2.0.0
```

- [ ] **Step 2: Install and verify**

Run: `pip install -r requirements.txt`
Expected: Successfully installs `mcp` and its dependencies (starlette, uvicorn, httpx-sse, etc.)

- [ ] **Step 3: Verify import works**

Run: `python3 -c "from mcp.server import Server; from mcp.client.session import ClientSession; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add mcp SDK dependency for Phase 2"
```

---

## Task 2: MCP config models

**Files:**
- Create: `src/quartermaster/mcp/__init__.py`
- Create: `src/quartermaster/mcp/config.py`
- Modify: `src/quartermaster/core/config.py`
- Create: `tests/mcp/__init__.py`
- Create: `tests/mcp/test_config.py`

- [ ] **Step 1: Create test file with failing tests**

Create `tests/mcp/__init__.py` (empty) and `tests/mcp/test_config.py`:

```python
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
            # command missing — should fail
        )


def test_client_entry_http_requires_url() -> None:
    with pytest.raises(ValidationError):
        MCPClientEntry(
            transport=TransportType.STREAMABLE_HTTP,
            default_approval_tier="confirm",
            # url missing — should fail
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

    # Default — mcp section exists with defaults
    config = QuartermasterConfig(
        database={"dsn": "x", "user": "x", "password": "x"},
    )
    assert config.mcp is not None
    assert config.mcp.server is None
    assert config.mcp.clients == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mcp/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quartermaster.mcp'`

- [ ] **Step 3: Implement config models**

Create `src/quartermaster/mcp/__init__.py`:

```python
"""MCP infrastructure — client, server, and bridge."""
```

Create `src/quartermaster/mcp/config.py`:

```python
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
        elif self.transport in (TransportType.STREAMABLE_HTTP, TransportType.SSE):
            if not self.url:
                raise ValueError(f"{self.transport} transport requires 'url'")
        return self


class MCPConfig(BaseModel):
    """Root MCP configuration."""

    server: MCPServerConfig | None = None
    clients: dict[str, MCPClientEntry] = {}
```

- [ ] **Step 4: Wire MCPConfig into QuartermasterConfig**

In `src/quartermaster/core/config.py`, add the import and field:

```python
# Add import at top
from quartermaster.mcp.config import MCPConfig

# Add field to QuartermasterConfig class (after logging field)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/mcp/test_config.py -v`
Expected: All 12 tests PASS

- [ ] **Step 6: Run full test suite to check no regressions**

Run: `pytest tests/ -v`
Expected: All existing tests still pass

- [ ] **Step 7: Type check**

Run: `mypy src/quartermaster/mcp/config.py`
Expected: Success

- [ ] **Step 8: Commit**

```bash
git add src/quartermaster/mcp/__init__.py src/quartermaster/mcp/config.py \
        src/quartermaster/core/config.py \
        tests/mcp/__init__.py tests/mcp/test_config.py
git commit -m "feat: MCP config models — server, client entry, transport types"
```

---

## Task 3: Tool Registry enhancements

**Files:**
- Modify: `src/quartermaster/core/tools.py`
- Modify: `tests/core/test_tools.py`

- [ ] **Step 1: Write failing tests for new features**

Add to `tests/core/test_tools.py`:

```python
from unittest.mock import AsyncMock, MagicMock


def test_tool_definition_source_default() -> None:
    """New tools default to source='local'."""
    registry = ToolRegistry()

    async def handler(params: dict) -> dict:
        return {}

    registry.register(name="test.tool", description="Test", parameters={}, handler=handler)
    tool = registry.get("test.tool")
    assert tool is not None
    assert tool.source == "local"


def test_tool_definition_source_custom() -> None:
    """Tools can be registered with a custom source."""
    registry = ToolRegistry()

    async def handler(params: dict) -> dict:
        return {}

    registry.register(
        name="remote.tool", description="Remote", parameters={},
        handler=handler, source="claude-memory",
    )
    tool = registry.get("remote.tool")
    assert tool is not None
    assert tool.source == "claude-memory"
    assert tool.is_remote is True


def test_tool_definition_is_remote_property() -> None:
    """is_remote is True for non-local sources."""
    registry = ToolRegistry()

    async def handler(params: dict) -> dict:
        return {}

    registry.register(name="local.tool", description="Local", parameters={}, handler=handler)
    registry.register(
        name="remote.tool", description="Remote", parameters={},
        handler=handler, source="some-server",
    )
    assert registry.get("local.tool").is_remote is False
    assert registry.get("remote.tool").is_remote is True


@pytest.mark.asyncio
async def test_unregister_tool() -> None:
    """unregister() removes a tool from the registry."""
    registry = ToolRegistry()

    async def handler(params: dict) -> dict:
        return {}

    registry.register(name="temp.tool", description="Temporary", parameters={}, handler=handler)
    assert registry.get("temp.tool") is not None

    registry.unregister("temp.tool")
    assert registry.get("temp.tool") is None


def test_unregister_nonexistent_raises() -> None:
    """unregister() raises KeyError for unknown tools."""
    registry = ToolRegistry()
    with pytest.raises(KeyError, match="no.such.tool"):
        registry.unregister("no.such.tool")


def test_list_by_source() -> None:
    """list_by_source() filters tools by their source."""
    registry = ToolRegistry()

    async def handler(params: dict) -> dict:
        return {}

    registry.register(name="a.local", description="A", parameters={}, handler=handler)
    registry.register(
        name="b.remote", description="B", parameters={},
        handler=handler, source="server-b",
    )
    registry.register(
        name="c.remote", description="C", parameters={},
        handler=handler, source="server-b",
    )
    registry.register(
        name="d.other", description="D", parameters={},
        handler=handler, source="server-d",
    )

    local_tools = registry.list_by_source("local")
    assert len(local_tools) == 1
    assert local_tools[0].name == "a.local"

    server_b_tools = registry.list_by_source("server-b")
    assert len(server_b_tools) == 2
    names = {t.name for t in server_b_tools}
    assert names == {"b.remote", "c.remote"}


@pytest.mark.asyncio
async def test_register_emits_event() -> None:
    """register() emits tools.registry_changed when EventBus provided."""
    events = MagicMock()
    events.emit = AsyncMock()
    registry = ToolRegistry(events=events)

    async def handler(params: dict) -> dict:
        return {}

    registry.register(name="test.tool", description="Test", parameters={}, handler=handler)
    events.emit.assert_called_once_with(
        "tools.registry_changed", {"action": "registered", "tool": "test.tool"}
    )


@pytest.mark.asyncio
async def test_unregister_emits_event() -> None:
    """unregister() emits tools.registry_changed when EventBus provided."""
    events = MagicMock()
    events.emit = AsyncMock()
    registry = ToolRegistry(events=events)

    async def handler(params: dict) -> dict:
        return {}

    registry.register(name="test.tool", description="Test", parameters={}, handler=handler)
    events.emit.reset_mock()

    registry.unregister("test.tool")
    events.emit.assert_called_once_with(
        "tools.registry_changed", {"action": "unregistered", "tool": "test.tool"}
    )


def test_no_event_emission_without_eventbus() -> None:
    """register/unregister work without EventBus (backward compat)."""
    registry = ToolRegistry()  # no events

    async def handler(params: dict) -> dict:
        return {}

    # Should not raise
    registry.register(name="test.tool", description="Test", parameters={}, handler=handler)
    registry.unregister("test.tool")
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `pytest tests/core/test_tools.py -v -k "source or unregister or list_by_source or emits_event or without_eventbus"`
Expected: FAIL — `source` not recognized, `unregister` not found

- [ ] **Step 3: Implement Tool Registry changes**

Replace the full content of `src/quartermaster/core/tools.py`:

```python
"""Tool Registry — the central nervous system of Quartermaster."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from quartermaster.core.events import EventBus

logger = structlog.get_logger()

ToolHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


class ApprovalTier(StrEnum):
    """Approval tiers for tool execution."""

    AUTONOMOUS = "autonomous"
    CONFIRM = "confirm"
    NOTIFY = "notify"


@dataclass
class ToolDefinition:
    """A registered tool in the registry."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    approval_tier: ApprovalTier = ApprovalTier.AUTONOMOUS
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "local"

    @property
    def is_remote(self) -> bool:
        """True if this tool comes from a remote MCP server."""
        return self.source != "local"


class ToolRegistry:
    """Central registry for all tools.

    Tools are registered by plugins at startup. The LLM Router
    queries the registry for available tool schemas, and the
    Tool Executor dispatches calls through the registry.
    """

    def __init__(self, events: EventBus | None = None) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._events = events

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: ToolHandler,
        approval_tier: ApprovalTier = ApprovalTier.AUTONOMOUS,
        metadata: dict[str, Any] | None = None,
        source: str = "local",
    ) -> None:
        """Register a tool."""
        if name in self._tools:
            raise ValueError(f"Tool '{name}' already registered")
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            approval_tier=approval_tier,
            metadata=metadata or {},
            source=source,
        )
        logger.info("tool_registered", tool=name, tier=approval_tier.value, source=source)
        self._emit_event("registered", name)

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        del self._tools[name]
        logger.info("tool_unregistered", tool=name)
        self._emit_event("unregistered", name)

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_by_source(self, source: str) -> list[ToolDefinition]:
        """List tools filtered by source."""
        return [t for t in self._tools.values() if t.source == source]

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get tool schemas in OpenAI function-calling format.

        Returns a list compatible with both llama-swap (OpenAI format)
        and Anthropic's tool_use format.
        """
        schemas: list[dict[str, Any]] = []
        for tool in self._tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return schemas

    async def execute(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name.

        Returns the tool's result dict. If the tool raises an exception,
        returns an error dict instead (so the LLM can handle it).
        """
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' not found")
        try:
            return await tool.handler(params)
        except Exception as e:
            logger.exception("tool_execution_error", tool=name)
            return {"error": f"{type(e).__name__}: {e}"}

    def _emit_event(self, action: str, tool_name: str) -> None:
        """Emit a tools.registry_changed event if EventBus is available."""
        if self._events is None:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._events.emit(
                    "tools.registry_changed",
                    {"action": action, "tool": tool_name},
                )
            )
        except RuntimeError:
            # No running event loop (e.g., during sync test setup)
            pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_tools.py -v`
Expected: All tests PASS (old and new)

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Type check**

Run: `mypy src/quartermaster/core/tools.py`
Expected: Success

- [ ] **Step 7: Commit**

```bash
git add src/quartermaster/core/tools.py tests/core/test_tools.py
git commit -m "feat: Tool Registry — add source, unregister, list_by_source, event emission"
```

---

## Task 4: Bridge module

**Files:**
- Create: `src/quartermaster/mcp/bridge.py`
- Create: `tests/mcp/test_bridge.py`

- [ ] **Step 1: Write failing tests**

Create `tests/mcp/test_bridge.py`:

```python
"""Tests for MCP ↔ QM tool schema bridge."""

import pytest

from mcp.types import Tool as MCPTool

from quartermaster.core.tools import ApprovalTier, ToolDefinition
from quartermaster.mcp.bridge import (
    mcp_tool_to_definition,
    definition_to_mcp_tool,
    mcp_result_to_dict,
    dict_to_mcp_result,
)


def test_mcp_tool_to_definition_basic() -> None:
    """Translate a basic MCP tool to a QM ToolDefinition."""
    mcp_tool = MCPTool(
        name="search",
        description="Search the memory",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    )

    async def mock_handler(params: dict) -> dict:
        return {}

    defn = mcp_tool_to_definition(
        tool=mcp_tool,
        handler=mock_handler,
        server_name="claude-memory",
        approval_tier=ApprovalTier.AUTONOMOUS,
    )

    assert defn.name == "claude-memory.search"
    assert defn.description == "Search the memory"
    assert defn.parameters["properties"]["query"]["type"] == "string"
    assert defn.source == "claude-memory"
    assert defn.approval_tier == ApprovalTier.AUTONOMOUS
    assert defn.is_remote is True


def test_mcp_tool_to_definition_custom_namespace() -> None:
    """Custom namespace overrides server name prefix."""
    mcp_tool = MCPTool(
        name="search",
        description="Search",
        inputSchema={"type": "object", "properties": {}},
    )

    async def mock_handler(params: dict) -> dict:
        return {}

    defn = mcp_tool_to_definition(
        tool=mcp_tool,
        handler=mock_handler,
        server_name="claude-memory",
        approval_tier=ApprovalTier.CONFIRM,
        namespace="mem",
    )

    assert defn.name == "mem.search"
    assert defn.source == "claude-memory"


def test_mcp_tool_to_definition_no_description() -> None:
    """MCP tool with no description gets a default."""
    mcp_tool = MCPTool(
        name="do_thing",
        inputSchema={"type": "object", "properties": {}},
    )

    async def mock_handler(params: dict) -> dict:
        return {}

    defn = mcp_tool_to_definition(
        tool=mcp_tool,
        handler=mock_handler,
        server_name="test",
        approval_tier=ApprovalTier.CONFIRM,
    )

    assert defn.description != ""  # Should have a default


def test_definition_to_mcp_tool() -> None:
    """Translate a QM ToolDefinition to an MCP Tool."""
    async def handler(params: dict) -> dict:
        return {}

    defn = ToolDefinition(
        name="commands.system_status",
        description="Get system status",
        parameters={
            "type": "object",
            "properties": {
                "verbose": {"type": "boolean", "default": False},
            },
            "required": [],
        },
        handler=handler,
    )

    mcp_tool = definition_to_mcp_tool(defn)

    assert mcp_tool.name == "commands.system_status"
    assert mcp_tool.description == "Get system status"
    assert mcp_tool.inputSchema["properties"]["verbose"]["type"] == "boolean"


def test_mcp_result_to_dict_text() -> None:
    """Translate MCP text result to dict."""
    from mcp.types import CallToolResult, TextContent

    result = CallToolResult(
        content=[TextContent(type="text", text='{"status": "ok"}')],
        isError=False,
    )
    d = mcp_result_to_dict(result)
    assert d == {"status": "ok"}


def test_mcp_result_to_dict_error() -> None:
    """Translate MCP error result to error dict."""
    from mcp.types import CallToolResult, TextContent

    result = CallToolResult(
        content=[TextContent(type="text", text="connection refused")],
        isError=True,
    )
    d = mcp_result_to_dict(result)
    assert "error" in d


def test_mcp_result_to_dict_non_json_text() -> None:
    """Non-JSON text result is wrapped in a text key."""
    from mcp.types import CallToolResult, TextContent

    result = CallToolResult(
        content=[TextContent(type="text", text="plain text response")],
        isError=False,
    )
    d = mcp_result_to_dict(result)
    assert d == {"text": "plain text response"}


def test_dict_to_mcp_result() -> None:
    """Translate dict result to MCP CallToolResult."""
    result = dict_to_mcp_result({"status": "ok", "count": 42})
    assert len(result) == 1
    assert result[0].type == "text"
    assert '"status"' in result[0].text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mcp/test_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quartermaster.mcp.bridge'`

- [ ] **Step 3: Implement bridge module**

Create `src/quartermaster/mcp/bridge.py`:

```python
"""Bidirectional MCP ↔ QM ToolDefinition translation.

This is the single translation point between MCP tool schemas
and Quartermaster's internal ToolDefinition format. Both client
and server use this module.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from mcp.types import CallToolResult, TextContent, Tool as MCPTool

from quartermaster.core.tools import ApprovalTier, ToolDefinition, ToolHandler

logger = structlog.get_logger()


def mcp_tool_to_definition(
    tool: MCPTool,
    handler: ToolHandler,
    server_name: str,
    approval_tier: ApprovalTier,
    namespace: str | None = None,
) -> ToolDefinition:
    """Translate an MCP Tool schema to a QM ToolDefinition.

    Args:
        tool: MCP tool from a remote server
        handler: Async closure that calls the remote tool
        server_name: Name of the MCP server (used for source tracking)
        approval_tier: Approval tier from config
        namespace: Optional namespace override (defaults to server_name)
    """
    prefix = namespace or server_name
    name = f"{prefix}.{tool.name}"
    description = tool.description or f"Remote tool: {tool.name} (from {server_name})"
    parameters = tool.inputSchema if tool.inputSchema else {"type": "object", "properties": {}}

    return ToolDefinition(
        name=name,
        description=description,
        parameters=parameters,
        handler=handler,
        approval_tier=approval_tier,
        source=server_name,
        metadata={"mcp_server": server_name, "mcp_original_name": tool.name},
    )


def definition_to_mcp_tool(defn: ToolDefinition) -> MCPTool:
    """Translate a QM ToolDefinition to an MCP Tool schema.

    Used by the MCP server to expose tools to external clients.
    """
    return MCPTool(
        name=defn.name,
        description=defn.description,
        inputSchema=defn.parameters if defn.parameters else {"type": "object", "properties": {}},
    )


def mcp_result_to_dict(result: CallToolResult) -> dict[str, Any]:
    """Translate an MCP CallToolResult to a plain dict.

    Used by the MCP client to convert remote tool results
    into the format the Tool Registry expects.
    """
    if result.isError:
        texts = [c.text for c in result.content if isinstance(c, TextContent)]
        return {"error": " ".join(texts) if texts else "Unknown MCP tool error"}

    texts = [c.text for c in result.content if isinstance(c, TextContent)]
    if not texts:
        return {"result": "ok"}

    combined = "\n".join(texts)

    # Try to parse as JSON
    try:
        parsed = json.loads(combined)
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}
    except (json.JSONDecodeError, ValueError):
        return {"text": combined}


def dict_to_mcp_result(result: dict[str, Any]) -> list[TextContent]:
    """Translate a dict result to MCP TextContent list.

    Used by the MCP server to convert local tool results
    into the format MCP clients expect.
    """
    return [TextContent(type="text", text=json.dumps(result, default=str))]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/mcp/test_bridge.py -v`
Expected: All tests PASS

- [ ] **Step 5: Type check**

Run: `mypy src/quartermaster/mcp/bridge.py`
Expected: Success

- [ ] **Step 6: Commit**

```bash
git add src/quartermaster/mcp/bridge.py tests/mcp/test_bridge.py
git commit -m "feat: MCP bridge — bidirectional tool schema translation"
```

---

## Task 5: Auth middleware

**Files:**
- Create: `src/quartermaster/mcp/auth.py`
- Create: `tests/mcp/test_auth.py`

- [ ] **Step 1: Write failing tests**

Create `tests/mcp/test_auth.py`:

```python
"""Tests for MCP server authentication middleware."""

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

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
        allowed_hosts=["127.0.0.1", "192.168.1.0/24"],
    )
    app = _make_app(auth)
    client = TestClient(app)

    # TestClient uses 127.0.0.1 by default
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mcp/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quartermaster.mcp.auth'`

- [ ] **Step 3: Implement auth middleware**

Create `src/quartermaster/mcp/auth.py`:

```python
"""MCP server authentication — bearer token + IP allowlist.

Designed as pluggable middleware. The current implementation uses
bearer tokens. Future implementations (mTLS, OAuth) can implement
the same interface.
"""

from __future__ import annotations

import ipaddress
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()


class BearerTokenAuth:
    """Bearer token + IP allowlist authentication."""

    def __init__(self, token: str, allowed_hosts: list[str]) -> None:
        self._token = token
        self._networks = self._parse_networks(allowed_hosts)

    def as_middleware_class(self) -> type[BaseHTTPMiddleware]:
        """Return a Starlette middleware class bound to this auth instance."""
        auth = self

        class AuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next: Any) -> Response:
                return await auth.check_request(request, call_next)

        return AuthMiddleware

    async def check_request(self, request: Request, call_next: Any) -> Response:
        """Validate auth token and IP allowlist."""
        client_ip = request.client.host if request.client else "unknown"

        # Check IP allowlist (if configured)
        if self._networks and not self._check_ip(client_ip):
            logger.warning("mcp_auth_ip_rejected", client_ip=client_ip)
            return Response(status_code=403)

        # Check bearer token
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning("mcp_auth_missing_token", client_ip=client_ip)
            return Response(status_code=401)

        token = auth_header[7:]  # Strip "Bearer "
        if token != self._token:
            logger.warning("mcp_auth_invalid_token", client_ip=client_ip)
            return Response(status_code=401)

        return await call_next(request)

    def _check_ip(self, client_ip: str) -> bool:
        """Check if client IP is in the allowlist."""
        try:
            addr = ipaddress.ip_address(client_ip)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/mcp/test_auth.py -v`
Expected: All tests PASS

- [ ] **Step 5: Type check**

Run: `mypy src/quartermaster/mcp/auth.py`
Expected: Success

- [ ] **Step 6: Commit**

```bash
git add src/quartermaster/mcp/auth.py tests/mcp/test_auth.py
git commit -m "feat: MCP auth middleware — bearer token + IP allowlist"
```

---

## Task 6: Transport factory

**Files:**
- Create: `src/quartermaster/mcp/transports.py`
- Create: `tests/mcp/test_transports.py`

- [ ] **Step 1: Write failing tests**

Create `tests/mcp/test_transports.py`:

```python
"""Tests for MCP transport factory."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mcp/test_transports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quartermaster.mcp.transports'`

- [ ] **Step 3: Implement transport factory**

Create `src/quartermaster/mcp/transports.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/mcp/test_transports.py -v`
Expected: All tests PASS

- [ ] **Step 5: Type check**

Run: `mypy src/quartermaster/mcp/transports.py`
Expected: Success

- [ ] **Step 6: Commit**

```bash
git add src/quartermaster/mcp/transports.py tests/mcp/test_transports.py
git commit -m "feat: MCP transport factory — config-driven transport selection"
```

---

## Task 7: Prometheus metrics for MCP

**Files:**
- Modify: `src/quartermaster/core/metrics.py`

- [ ] **Step 1: Add MCP metrics**

Add the following metric definitions after the existing `budget_limit_usd` gauge in `src/quartermaster/core/metrics.py`:

```python
# MCP Client metrics
mcp_client_status = Gauge(
    "qm_mcp_client_status",
    "MCP client connection status (1=up, 0=down, 0.5=degraded)",
    ["server"],
)
mcp_client_reconnect_total = Counter(
    "qm_mcp_client_reconnect_total",
    "Total MCP client reconnection attempts",
    ["server"],
)
mcp_tool_calls_total = Counter(
    "qm_mcp_tool_calls_total",
    "Total MCP remote tool calls",
    ["server", "tool", "status"],
)
mcp_tool_call_duration = Histogram(
    "qm_mcp_tool_call_duration_seconds",
    "MCP remote tool call duration",
    ["server", "tool"],
)

# MCP Server metrics
mcp_server_requests_total = Counter(
    "qm_mcp_server_requests_total",
    "Total MCP server requests",
    ["method", "status"],
)
mcp_server_connected_clients = Gauge(
    "qm_mcp_server_connected_clients",
    "Number of connected MCP clients",
)
mcp_server_auth_failures_total = Counter(
    "qm_mcp_server_auth_failures_total",
    "Total MCP server authentication failures",
)
```

- [ ] **Step 2: Run existing tests**

Run: `pytest tests/ -v`
Expected: All tests still pass (metrics are module-level singletons, no behavioral change)

- [ ] **Step 3: Commit**

```bash
git add src/quartermaster/core/metrics.py
git commit -m "feat: add Prometheus metrics for MCP client and server"
```

---

## Task 8: MCP Client Manager

**Files:**
- Create: `src/quartermaster/mcp/client.py`
- Create: `tests/mcp/test_client.py`
- Create: `tests/mcp/conftest.py`

- [ ] **Step 1: Create shared test fixtures**

Create `tests/mcp/conftest.py`:

```python
"""Shared fixtures for MCP tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from quartermaster.core.tools import ToolRegistry


@pytest.fixture
def mock_events() -> MagicMock:
    events = MagicMock()
    events.emit = AsyncMock()
    events.subscribe = MagicMock()
    return events


@pytest.fixture
def tool_registry(mock_events: MagicMock) -> ToolRegistry:
    return ToolRegistry(events=mock_events)
```

- [ ] **Step 2: Write failing tests**

Create `tests/mcp/test_client.py`:

```python
"""Tests for MCP Client Manager."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.types import Tool as MCPTool, ListToolsResult, CallToolResult, TextContent

from quartermaster.core.tools import ApprovalTier, ToolRegistry
from quartermaster.mcp.client import MCPClientManager
from quartermaster.mcp.config import MCPClientEntry, MCPConfig, TransportType, ToolOverride


@pytest.fixture
def mcp_config() -> MCPConfig:
    return MCPConfig(
        clients={
            "test-server": MCPClientEntry(
                transport=TransportType.STREAMABLE_HTTP,
                url="http://localhost:9999/mcp",
                default_approval_tier="confirm",
                enabled=True,
            ),
        },
    )


@pytest.fixture
def disabled_config() -> MCPConfig:
    return MCPConfig(
        clients={
            "disabled-server": MCPClientEntry(
                transport=TransportType.STREAMABLE_HTTP,
                url="http://localhost:9999/mcp",
                default_approval_tier="confirm",
                enabled=False,
            ),
        },
    )


@pytest.fixture
def override_config() -> MCPConfig:
    return MCPConfig(
        clients={
            "override-server": MCPClientEntry(
                transport=TransportType.STREAMABLE_HTTP,
                url="http://localhost:9999/mcp",
                default_approval_tier="autonomous",
                tool_overrides={
                    "dangerous_tool": ToolOverride(approval_tier="confirm"),
                    "hidden_tool": ToolOverride(enabled=False),
                },
                enabled=True,
            ),
        },
    )


def test_client_manager_init(
    tool_registry: ToolRegistry, mock_events: MagicMock, mcp_config: MCPConfig
) -> None:
    """MCPClientManager initializes without errors."""
    mgr = MCPClientManager(
        config=mcp_config,
        tools=tool_registry,
        events=mock_events,
    )
    assert mgr is not None


@pytest.mark.asyncio
async def test_register_tools_from_server(
    tool_registry: ToolRegistry, mock_events: MagicMock, mcp_config: MCPConfig
) -> None:
    """Remote tools are registered into the Tool Registry with namespacing."""
    mgr = MCPClientManager(
        config=mcp_config,
        tools=tool_registry,
        events=mock_events,
    )

    # Simulate tool discovery from a connected server
    mock_tools = [
        MCPTool(
            name="search",
            description="Search things",
            inputSchema={"type": "object", "properties": {"q": {"type": "string"}}},
        ),
        MCPTool(
            name="list_items",
            description="List items",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]

    mock_session = AsyncMock()
    mock_session.list_tools = AsyncMock(
        return_value=ListToolsResult(tools=mock_tools)
    )

    await mgr._register_server_tools("test-server", mock_session, mcp_config.clients["test-server"])

    # Tools should be namespaced
    assert tool_registry.get("test-server.search") is not None
    assert tool_registry.get("test-server.list_items") is not None
    assert tool_registry.get("test-server.search").source == "test-server"
    assert tool_registry.get("test-server.search").approval_tier == ApprovalTier.CONFIRM


@pytest.mark.asyncio
async def test_approval_tier_override(
    tool_registry: ToolRegistry, mock_events: MagicMock, override_config: MCPConfig
) -> None:
    """Tool overrides change approval tier per tool."""
    mgr = MCPClientManager(
        config=override_config,
        tools=tool_registry,
        events=mock_events,
    )

    mock_tools = [
        MCPTool(
            name="safe_tool",
            description="Safe",
            inputSchema={"type": "object", "properties": {}},
        ),
        MCPTool(
            name="dangerous_tool",
            description="Dangerous",
            inputSchema={"type": "object", "properties": {}},
        ),
        MCPTool(
            name="hidden_tool",
            description="Hidden",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]

    mock_session = AsyncMock()
    mock_session.list_tools = AsyncMock(
        return_value=ListToolsResult(tools=mock_tools)
    )

    await mgr._register_server_tools(
        "override-server", mock_session, override_config.clients["override-server"]
    )

    # Default tier
    assert tool_registry.get("override-server.safe_tool").approval_tier == ApprovalTier.AUTONOMOUS
    # Overridden tier
    assert tool_registry.get("override-server.dangerous_tool").approval_tier == ApprovalTier.CONFIRM
    # Hidden tool not registered
    assert tool_registry.get("override-server.hidden_tool") is None


@pytest.mark.asyncio
async def test_unregister_server_tools(
    tool_registry: ToolRegistry, mock_events: MagicMock, mcp_config: MCPConfig
) -> None:
    """Disconnecting a server removes its tools from the registry."""
    mgr = MCPClientManager(
        config=mcp_config,
        tools=tool_registry,
        events=mock_events,
    )

    mock_tools = [
        MCPTool(
            name="tool_a",
            description="A",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]

    mock_session = AsyncMock()
    mock_session.list_tools = AsyncMock(
        return_value=ListToolsResult(tools=mock_tools)
    )

    await mgr._register_server_tools("test-server", mock_session, mcp_config.clients["test-server"])
    assert tool_registry.get("test-server.tool_a") is not None

    mgr._unregister_server_tools("test-server")
    assert tool_registry.get("test-server.tool_a") is None


@pytest.mark.asyncio
async def test_disabled_server_skipped(
    tool_registry: ToolRegistry, mock_events: MagicMock, disabled_config: MCPConfig
) -> None:
    """Disabled server entries are not connected."""
    mgr = MCPClientManager(
        config=disabled_config,
        tools=tool_registry,
        events=mock_events,
    )
    enabled = mgr._get_enabled_entries()
    assert len(enabled) == 0


@pytest.mark.asyncio
async def test_name_collision_skips_remote(
    tool_registry: ToolRegistry, mock_events: MagicMock, mcp_config: MCPConfig
) -> None:
    """If a remote tool name collides with existing, it's skipped."""
    # Register a local tool with the same namespaced name
    async def handler(params: dict) -> dict:
        return {}

    tool_registry.register(
        name="test-server.search",
        description="Local version",
        parameters={},
        handler=handler,
    )

    mgr = MCPClientManager(
        config=mcp_config,
        tools=tool_registry,
        events=mock_events,
    )

    mock_tools = [
        MCPTool(
            name="search",
            description="Remote version",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]

    mock_session = AsyncMock()
    mock_session.list_tools = AsyncMock(
        return_value=ListToolsResult(tools=mock_tools)
    )

    await mgr._register_server_tools("test-server", mock_session, mcp_config.clients["test-server"])

    # Local tool should still be there, unchanged
    tool = tool_registry.get("test-server.search")
    assert tool is not None
    assert tool.description == "Local version"
    assert tool.source == "local"


def test_get_server_statuses(
    tool_registry: ToolRegistry, mock_events: MagicMock, mcp_config: MCPConfig
) -> None:
    """get_server_statuses() returns status dict."""
    mgr = MCPClientManager(
        config=mcp_config,
        tools=tool_registry,
        events=mock_events,
    )
    statuses = mgr.get_server_statuses()
    assert "test-server" in statuses
    assert statuses["test-server"]["status"] == "disconnected"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mcp/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quartermaster.mcp.client'`

- [ ] **Step 3: Implement MCPClientManager**

Create `src/quartermaster/mcp/client.py`:

```python
"""MCP Client Manager — connects to external MCP servers and bridges tools.

Orchestrates all outbound MCP connections. On startup, connects to each
enabled server in config, fetches its tools, and registers them into
the Tool Registry with server-prefix namespacing. Handles reconnection
on disconnect and dynamic tool list updates.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import structlog
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.types import ListToolsResult

# Note: At implementation time, check if streamablehttp_client has been
# replaced by streamable_http_client in the installed SDK version.
# The SDK is evolving — use whichever is current and not deprecated.

from quartermaster.core.metrics import (
    mcp_client_reconnect_total,
    mcp_client_status,
    mcp_tool_call_duration,
    mcp_tool_calls_total,
)
from quartermaster.core.tools import ApprovalTier, ToolHandler, ToolRegistry
from quartermaster.mcp.bridge import mcp_result_to_dict, mcp_tool_to_definition
from quartermaster.mcp.config import MCPClientEntry, MCPConfig, TransportType
from quartermaster.mcp.transports import MCPTransportFactory

if TYPE_CHECKING:
    from quartermaster.core.events import EventBus

logger = structlog.get_logger()


class MCPClientManager:
    """Manages connections to external MCP servers."""

    def __init__(
        self,
        config: MCPConfig,
        tools: ToolRegistry,
        events: EventBus | Any,
    ) -> None:
        self._config = config
        self._tools = tools
        self._events = events
        self._factory = MCPTransportFactory()
        self._sessions: dict[str, ClientSession] = {}
        self._transport_contexts: dict[str, Any] = {}  # Store context managers for cleanup
        self._server_statuses: dict[str, dict[str, Any]] = {}
        self._reconnect_tasks: dict[str, asyncio.Task[None]] = {}

        # Initialize status for all configured servers
        for name, entry in config.clients.items():
            self._server_statuses[name] = {
                "status": "disabled" if not entry.enabled else "disconnected",
                "transport": entry.transport.value,
                "tools": 0,
            }

    async def start(self) -> None:
        """Connect to all enabled MCP servers."""
        for name, entry in self._get_enabled_entries():
            await self._connect_server(name, entry)

    async def stop(self) -> None:
        """Disconnect from all servers and clean up."""
        # Cancel reconnection tasks
        for task in self._reconnect_tasks.values():
            task.cancel()
        self._reconnect_tasks.clear()

        # Disconnect all sessions and close transport contexts
        for name in list(self._sessions.keys()):
            self._unregister_server_tools(name)
            self._sessions.pop(name, None)
            # Clean up transport context manager
            ctx = self._transport_contexts.pop(name, None)
            if ctx is not None:
                try:
                    await ctx.__aexit__(None, None, None)
                except Exception:
                    logger.debug("mcp_transport_cleanup_error", server=name)
            self._update_status(name, "disconnected", 0)

        logger.info("mcp_client_manager_stopped")

    def get_server_statuses(self) -> dict[str, dict[str, Any]]:
        """Get status of all configured MCP servers."""
        return dict(self._server_statuses)

    def _get_enabled_entries(self) -> list[tuple[str, MCPClientEntry]]:
        """Get list of enabled server entries."""
        return [
            (name, entry)
            for name, entry in self._config.clients.items()
            if entry.enabled
        ]

    async def _connect_server(self, name: str, entry: MCPClientEntry) -> None:
        """Establish connection to a single MCP server."""
        try:
            ctx = self._factory.get_transport_context(entry, server_name=name)
        except FileNotFoundError as e:
            logger.error("mcp_client_command_not_found", server=name, error=str(e))
            self._update_status(name, "down", 0)
            return

        try:
            session = await self._create_session(name, ctx)
            self._sessions[name] = session
            await self._register_server_tools(name, session, entry)
            tool_count = len(self._tools.list_by_source(name))
            self._update_status(name, "up", tool_count)

            await self._events.emit("mcp.client_connected", {
                "server": name,
                "transport": entry.transport.value,
                "tool_count": tool_count,
            })

            logger.info(
                "mcp_client_connected",
                server=name,
                transport=entry.transport.value,
                tools=tool_count,
            )
        except Exception:
            logger.exception("mcp_client_connection_failed", server=name)
            self._update_status(name, "down", 0)
            self._schedule_reconnect(name, entry)

    async def _create_session(
        self, name: str, ctx: dict[str, Any]
    ) -> ClientSession:
        """Create an MCP ClientSession using the appropriate transport.

        Stores the transport context manager for proper cleanup on stop().
        """
        transport_type = ctx["type"]

        if transport_type == "streamable_http":
            transport_ctx = streamablehttp_client(
                url=ctx["url"],
                headers=ctx.get("headers"),
            )
        elif transport_type == "sse":
            transport_ctx = sse_client(
                url=ctx["url"],
                headers=ctx.get("headers"),
            )
        elif transport_type == "stdio":
            transport_ctx = stdio_client(server=ctx["server_params"])
        else:
            raise ValueError(f"Unknown transport type: {transport_type}")

        # Enter the transport context manager and store for cleanup
        self._transport_contexts[name] = transport_ctx
        streams = await transport_ctx.__aenter__()
        read_stream, write_stream = streams[0], streams[1]

        session = ClientSession(read_stream, write_stream)
        await session.initialize()
        return session

    async def _register_server_tools(
        self,
        server_name: str,
        session: ClientSession,
        entry: MCPClientEntry,
    ) -> None:
        """Fetch tools from server and register them in the Tool Registry."""
        result: ListToolsResult = await session.list_tools()

        namespace = entry.namespace or server_name
        default_tier = ApprovalTier(entry.default_approval_tier)

        for mcp_tool in result.tools:
            # Check tool-level overrides
            override = entry.tool_overrides.get(mcp_tool.name)
            if override and not override.enabled:
                logger.debug("mcp_tool_skipped_disabled", server=server_name, tool=mcp_tool.name)
                continue

            tier = default_tier
            if override and override.approval_tier:
                tier = ApprovalTier(override.approval_tier)

            # Create handler closure that calls the remote tool
            def make_handler(
                _session: ClientSession, _tool_name: str, _server: str
            ) -> ToolHandler:
                async def handler(params: dict[str, Any]) -> dict[str, Any]:
                    start = time.monotonic()
                    try:
                        result = await _session.call_tool(_tool_name, params)
                        duration = time.monotonic() - start
                        mcp_tool_calls_total.labels(
                            server=_server, tool=_tool_name, status="success"
                        ).inc()
                        mcp_tool_call_duration.labels(
                            server=_server, tool=_tool_name
                        ).observe(duration)
                        return mcp_result_to_dict(result)
                    except Exception as e:
                        duration = time.monotonic() - start
                        mcp_tool_calls_total.labels(
                            server=_server, tool=_tool_name, status="error"
                        ).inc()
                        mcp_tool_call_duration.labels(
                            server=_server, tool=_tool_name
                        ).observe(duration)
                        return {"error": f"MCP call failed: {e}"}

                return handler

            handler = make_handler(session, mcp_tool.name, server_name)

            defn = mcp_tool_to_definition(
                tool=mcp_tool,
                handler=handler,
                server_name=server_name,
                approval_tier=tier,
                namespace=namespace,
            )

            # Skip if name already exists (local tools take priority)
            if self._tools.get(defn.name) is not None:
                logger.warning(
                    "mcp_tool_name_collision",
                    server=server_name,
                    tool=defn.name,
                )
                continue

            self._tools.register(
                name=defn.name,
                description=defn.description,
                parameters=defn.parameters,
                handler=defn.handler,
                approval_tier=defn.approval_tier,
                metadata=defn.metadata,
                source=defn.source,
            )

    def _unregister_server_tools(self, server_name: str) -> None:
        """Remove all tools from a specific server."""
        tools = self._tools.list_by_source(server_name)
        for tool in tools:
            try:
                self._tools.unregister(tool.name)
            except KeyError:
                pass
        logger.info("mcp_tools_unregistered", server=server_name, count=len(tools))

    def _update_status(self, name: str, status: str, tool_count: int) -> None:
        """Update server status and Prometheus metrics."""
        self._server_statuses[name]["status"] = status
        self._server_statuses[name]["tools"] = tool_count

        metric_value = {"up": 1.0, "degraded": 0.5, "down": 0.0}.get(status, 0.0)
        mcp_client_status.labels(server=name).set(metric_value)

    def _schedule_reconnect(self, name: str, entry: MCPClientEntry) -> None:
        """Schedule a reconnection attempt for a failed server."""
        if name in self._reconnect_tasks:
            return  # Already scheduled

        async def reconnect_loop() -> None:
            delay = 5.0
            max_delay = 60.0
            max_retries = 5

            for attempt in range(max_retries):
                await asyncio.sleep(delay)
                logger.info(
                    "mcp_client_reconnecting",
                    server=name,
                    attempt=attempt + 1,
                )
                mcp_client_reconnect_total.labels(server=name).inc()

                try:
                    await self._connect_server(name, entry)
                    if self._server_statuses[name]["status"] == "up":
                        self._reconnect_tasks.pop(name, None)
                        return
                except Exception:
                    logger.exception("mcp_reconnect_failed", server=name)

                delay = min(delay * 2, max_delay)

            logger.error("mcp_client_reconnect_exhausted", server=name)
            self._update_status(name, "down", 0)
            await self._events.emit("mcp.client.health_changed", {
                "server": name,
                "status": "down",
            })
            self._reconnect_tasks.pop(name, None)

        self._reconnect_tasks[name] = asyncio.create_task(reconnect_loop())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/mcp/test_client.py -v`
Expected: All tests PASS

- [ ] **Step 5: Type check**

Run: `mypy src/quartermaster/mcp/client.py`
Expected: Success

- [ ] **Step 6: Commit**

```bash
git add src/quartermaster/mcp/client.py tests/mcp/test_client.py tests/mcp/conftest.py
git commit -m "feat: MCP Client Manager — connects to servers, bridges tools into registry"
```

---

## Task 9: MCP Server

**Files:**
- Create: `src/quartermaster/mcp/server.py`
- Create: `tests/mcp/test_server.py`

- [ ] **Step 1: Write failing tests**

Create `tests/mcp/test_server.py`:

```python
"""Tests for MCP Server."""

import json
import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from quartermaster.core.tools import ApprovalTier, ToolRegistry
from quartermaster.mcp.config import MCPServerConfig
from quartermaster.mcp.server import MCPServer


@pytest.fixture
def server_config(tmp_path: Any) -> MCPServerConfig:
    token_file = tmp_path / "token"
    token_file.write_text("test-token-123")
    return MCPServerConfig(
        enabled=True,
        port=0,  # random port for testing
        bind="127.0.0.1",
        auth_token_file=str(token_file),
        allowed_hosts=[],
        approval_chat_id="12345",
    )


@pytest.fixture
def server(
    server_config: MCPServerConfig,
    tool_registry: ToolRegistry,
    mock_events: MagicMock,
) -> MCPServer:
    return MCPServer(
        config=server_config,
        tools=tool_registry,
        events=mock_events,
        approval=MagicMock(),
        transport=MagicMock(),
    )


def test_server_init(server: MCPServer) -> None:
    """MCPServer initializes without errors."""
    assert server is not None


def test_server_list_tools(
    server: MCPServer, tool_registry: ToolRegistry
) -> None:
    """Server lists all tools from the registry."""
    async def handler(params: dict) -> dict:
        return {}

    tool_registry.register(
        name="test.hello", description="Say hello", parameters={}, handler=handler
    )
    tool_registry.register(
        name="test.goodbye", description="Say goodbye", parameters={}, handler=handler
    )

    tools = server._get_mcp_tools()
    assert len(tools) == 2
    names = {t.name for t in tools}
    assert names == {"test.hello", "test.goodbye"}


@pytest.mark.asyncio
async def test_server_call_autonomous_tool(
    server: MCPServer, tool_registry: ToolRegistry
) -> None:
    """Server executes autonomous tools directly."""
    async def greet(params: dict) -> dict:
        return {"greeting": f"Hello, {params.get('name', 'world')}!"}

    tool_registry.register(
        name="test.greet",
        description="Greet someone",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}},
        handler=greet,
        approval_tier=ApprovalTier.AUTONOMOUS,
    )

    result = await server._handle_tool_call("test.greet", {"name": "Brian"})
    assert result["greeting"] == "Hello, Brian!"


@pytest.mark.asyncio
async def test_server_call_unknown_tool(server: MCPServer) -> None:
    """Server returns error for unknown tools."""
    result = await server._handle_tool_call("nonexistent.tool", {})
    assert "error" in result


@pytest.mark.asyncio
async def test_server_call_confirm_tool_sends_approval(
    server: MCPServer, tool_registry: ToolRegistry
) -> None:
    """Confirm-tier tool triggers approval via Telegram."""
    async def dangerous_action(params: dict) -> dict:
        return {"status": "executed"}

    tool_registry.register(
        name="test.danger",
        description="Dangerous action",
        parameters={},
        handler=dangerous_action,
        approval_tier=ApprovalTier.CONFIRM,
    )

    server._approval = AsyncMock()
    server._approval.request_approval = AsyncMock(return_value="abc123")

    # The actual approval flow is tested in integration — here we verify
    # that confirm-tier tools trigger the approval path
    result = await server._handle_tool_call("test.danger", {})
    assert "approval" in str(result).lower() or server._approval.request_approval.called
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mcp/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quartermaster.mcp.server'`

- [ ] **Step 3: Implement MCP Server**

Create `src/quartermaster/mcp/server.py`:

```python
"""MCP Server — exposes Quartermaster tools via Streamable HTTP.

External MCP clients (e.g., Claude Code) connect to this server
to list and call Quartermaster's registered tools. Auth is handled
by the BearerTokenAuth middleware.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import uvicorn
from mcp.server.lowlevel.server import Server as MCPServerImpl
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool as MCPTool
from starlette.applications import Starlette
from starlette.routing import Mount

from quartermaster.core.metrics import (
    mcp_server_auth_failures_total,
    mcp_server_connected_clients,
    mcp_server_requests_total,
)
from quartermaster.core.tools import ApprovalTier, ToolRegistry
from quartermaster.mcp.auth import BearerTokenAuth
from quartermaster.mcp.bridge import definition_to_mcp_tool, dict_to_mcp_result
from quartermaster.mcp.config import MCPServerConfig

if TYPE_CHECKING:
    from quartermaster.core.events import EventBus

logger = structlog.get_logger()


class MCPServer:
    """Quartermaster MCP server exposing tools via Streamable HTTP."""

    def __init__(
        self,
        config: MCPServerConfig,
        tools: ToolRegistry,
        events: EventBus | Any,
        approval: Any,
        transport: Any,
    ) -> None:
        self._config = config
        self._tools = tools
        self._events = events
        self._approval = approval
        self._transport = transport
        self._uvicorn_server: uvicorn.Server | None = None
        self._serve_task: asyncio.Task[None] | None = None

        # Build the MCP server
        self._mcp = MCPServerImpl("quartermaster")

        # Register handlers
        @self._mcp.list_tools()
        async def list_tools() -> list[MCPTool]:
            mcp_server_requests_total.labels(method="tools/list", status="ok").inc()
            return self._get_mcp_tools()

        @self._mcp.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> list[TextContent]:
            params = arguments or {}
            try:
                result = await self._handle_tool_call(name, params)
                is_error = "error" in result
                status = "error" if is_error else "ok"
                mcp_server_requests_total.labels(method="tools/call", status=status).inc()
                return dict_to_mcp_result(result)
            except Exception as e:
                mcp_server_requests_total.labels(method="tools/call", status="error").inc()
                logger.exception("mcp_server_tool_call_error", tool=name)
                return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    async def start(self) -> None:
        """Start the MCP server."""
        if not self._config.enabled:
            logger.info("mcp_server_disabled")
            return

        # Load auth token
        token_path = Path(self._config.auth_token_file)
        if not token_path.exists():
            logger.error("mcp_server_token_missing", path=self._config.auth_token_file)
            return
        token = token_path.read_text().strip()

        # Build Starlette app with auth middleware
        auth = BearerTokenAuth(token=token, allowed_hosts=self._config.allowed_hosts)

        session_manager = StreamableHTTPSessionManager(
            app=self._mcp,
            json_response=True,
            stateless=True,
        )

        async def handle_mcp(scope: Any, receive: Any, send: Any) -> None:
            await session_manager.handle_request(scope, receive, send)

        app = Starlette(
            routes=[Mount("/mcp", app=handle_mcp)],
        )
        app.add_middleware(auth.as_middleware_class())

        # Subscribe to tool registry changes
        self._events.subscribe("tools.registry_changed", self._on_tools_changed)

        # Start uvicorn
        config = uvicorn.Config(
            app=app,
            host=self._config.bind,
            port=self._config.port,
            log_level="warning",
        )
        self._uvicorn_server = uvicorn.Server(config)
        self._serve_task = asyncio.create_task(self._uvicorn_server.serve())

        logger.info(
            "mcp_server_started",
            port=self._config.port,
            bind=self._config.bind,
        )

    async def stop(self) -> None:
        """Stop the MCP server."""
        if self._uvicorn_server:
            self._uvicorn_server.should_exit = True
        if self._serve_task:
            await self._serve_task
            self._serve_task = None

        logger.info("mcp_server_stopped")

    def _get_mcp_tools(self) -> list[MCPTool]:
        """Get all tools from the registry as MCP Tool objects."""
        return [definition_to_mcp_tool(defn) for defn in self._tools.list_tools()]

    async def _handle_tool_call(
        self, name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle a tool call, respecting approval tiers."""
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Tool '{name}' not found"}

        if tool.approval_tier == ApprovalTier.CONFIRM:
            return await self._handle_confirm_tier(name, params)
        elif tool.approval_tier == ApprovalTier.NOTIFY:
            result = await self._tools.execute(name, params)
            # Fire-and-forget notification
            asyncio.create_task(self._send_notification(name, params, result))
            return result
        else:
            # Autonomous — execute directly
            return await self._tools.execute(name, params)

    async def _handle_confirm_tier(
        self, name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle a confirm-tier tool call by routing through Telegram approval."""
        from quartermaster.core.approval import ApprovalRequest, ApprovalStatus
        from quartermaster.transport.types import TransportType

        if not self._config.approval_chat_id:
            return {"error": "Approval required but no approval_chat_id configured"}

        # Create approval request
        req = ApprovalRequest(
            plugin_name="mcp-server",
            tool_name=name,
            draft_content=f"MCP client requests: {name}\nParameters: {json.dumps(params, indent=2)}",
            action_payload={"tool": name, "params": params},
            chat_id=self._config.approval_chat_id,
            transport=TransportType.TELEGRAM,
        )

        approval_id = await self._approval.request_approval(req)

        # Wait for approval resolution via EventBus
        resolved_event = asyncio.Event()
        resolved_status: dict[str, str] = {}

        async def on_resolved(data: dict[str, Any]) -> None:
            if data.get("approval_id") == approval_id:
                resolved_status["status"] = data.get("status", "")
                resolved_event.set()

        self._events.subscribe("approval.resolved", on_resolved)

        # Use the approval timeout from MCP server config, or default 60 min
        timeout_seconds = 60 * 60  # 1 hour default
        try:
            await asyncio.wait_for(
                resolved_event.wait(),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            return {"error": f"Approval timed out for tool '{name}'"}
        finally:
            self._events.unsubscribe("approval.resolved", on_resolved)

        if resolved_status.get("status") == ApprovalStatus.APPROVED.value:
            return await self._tools.execute(name, params)
        else:
            return {
                "error": f"Tool '{name}' was {resolved_status.get('status', 'rejected')}"
            }

    async def _send_notification(
        self, name: str, params: dict[str, Any], result: dict[str, Any]
    ) -> None:
        """Send a notification about a notify-tier tool execution."""
        if not self._config.approval_chat_id:
            return
        from quartermaster.transport.types import OutboundMessage, TransportType

        await self._transport.send(OutboundMessage(
            transport=TransportType.TELEGRAM,
            chat_id=self._config.approval_chat_id,
            text=f"**Tool executed (notify):** {name}\nResult: {json.dumps(result, default=str)[:500]}",
        ))

    async def _on_tools_changed(self, data: dict[str, Any]) -> None:
        """Handle tool registry changes — notify connected clients.

        TODO: The SDK's StreamableHTTPSessionManager does not automatically
        propagate tool changes. To send notifications/tools/list_changed to
        connected clients, we need to track active sessions and call
        session.send_tool_list_changed() on each. For now, clients must
        reconnect to see tool changes. This is acceptable for Phase 2
        since tool changes only happen at startup (plugin load, MCP client
        connect). Real-time notifications can be added when needed.
        """
        logger.debug("mcp_server_tools_changed", **data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/mcp/test_server.py -v`
Expected: All tests PASS

- [ ] **Step 5: Type check**

Run: `mypy src/quartermaster/mcp/server.py`
Expected: Success

- [ ] **Step 6: Commit**

```bash
git add src/quartermaster/mcp/server.py tests/mcp/test_server.py
git commit -m "feat: MCP Server — Streamable HTTP with auth and approval routing"
```

---

## Task 10: Application bootstrap wiring

**Files:**
- Modify: `src/quartermaster/core/app.py`
- Modify: `src/quartermaster/plugin/context.py`

- [ ] **Step 1: Update PluginContext**

In `src/quartermaster/plugin/context.py`, add the `mcp_client` field:

```python
    mcp_client: Any = None  # MCPClientManager
```

Add it after the `conversation` field.

- [ ] **Step 2: Update app.py to wire MCP**

In `src/quartermaster/core/app.py`:

Add imports at the top:

```python
from quartermaster.mcp.client import MCPClientManager
from quartermaster.mcp.server import MCPServer
```

Add instance variables in `__init__`:

```python
        self._mcp_client: MCPClientManager | None = None
        self._mcp_server: MCPServer | None = None
```

In `start()`, update the ToolRegistry construction to pass events:

```python
        # Change from:
        self._tools = ToolRegistry()
        # To:
        self._tools = ToolRegistry(events=self._events)
```

After plugin loading, add MCP startup (before `await self._transport.start_all()`):

```python
        # Start MCP client (connects to external servers, registers tools)
        if self._config.mcp.clients:
            self._mcp_client = MCPClientManager(
                config=self._config.mcp,
                tools=self._tools,
                events=self._events,
            )
            await self._mcp_client.start()

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
```

Update the PluginContext to include mcp_client:

```python
        ctx = PluginContext(
            # ... existing fields ...
            mcp_client=self._mcp_client,
        )
```

Note: Since MCP client starts AFTER plugins load, the `mcp_client` in the context will be `None` at plugin setup time. Plugins that need it should access it lazily (it's set on the context object after plugin loading). Move the context field update after MCP client creation:

```python
        # After MCP client starts:
        if self._mcp_client:
            ctx.mcp_client = self._mcp_client
```

In `stop()`, add MCP shutdown (before plugin teardown):

```python
        if self._mcp_server:
            await self._mcp_server.stop()
        if self._mcp_client:
            await self._mcp_client.stop()
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Type check**

Run: `mypy src/quartermaster/core/app.py`
Expected: Success

- [ ] **Step 5: Commit**

```bash
git add src/quartermaster/core/app.py src/quartermaster/plugin/context.py
git commit -m "feat: wire MCP client + server into application bootstrap"
```

---

## Task 11: Update /status command and settings.example.yaml

**Files:**
- Modify: `plugins/commands/plugin.py`
- Modify: `config/settings.example.yaml`

- [ ] **Step 1: Add MCP status to /status command**

In `plugins/commands/plugin.py`, update the status handler to include MCP information. Add after the existing plugin health section:

```python
        # MCP status
        assert self._ctx is not None
        if self._ctx.mcp_client:
            lines.append("\n**MCP Clients:**")
            for name, status in self._ctx.mcp_client.get_server_statuses().items():
                lines.append(
                    f"  {name} ({status['transport']}): "
                    f"{status['status']} — {status['tools']} tools"
                )
```

- [ ] **Step 2: Update settings.example.yaml**

Add the MCP section to `config/settings.example.yaml` after the plugins_dir entry:

```yaml
  # MCP (Model Context Protocol) infrastructure
  mcp:
    # MCP Server — exposes Quartermaster tools to Claude Code and other MCP clients
    server:
      enabled: true
      port: 9200
      bind: "127.0.0.1"
      auth_token_file: "/app/credentials/mcp_server_token"
      allowed_hosts:
        - "127.0.0.1"
      # approval_chat_id: "YOUR_TELEGRAM_CHAT_ID"  # Required for confirm-tier tools via MCP

    # MCP Clients — connect to external MCP servers
    clients: {}
    # Example:
    # my-server:
    #   transport: streamable_http  # or: sse, stdio
    #   url: "http://localhost:8080/mcp"
    #   auth_token_file: "/app/credentials/my_server_token"
    #   default_approval_tier: confirm  # or: autonomous, notify
    #   enabled: true
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add plugins/commands/plugin.py config/settings.example.yaml
git commit -m "feat: add MCP status to /status command, update example config"
```

---

## Task 12: Integration test — loopback

**Files:**
- Create: `tests/mcp/test_integration.py`
- Create: `tests/fixtures/echo_server.py`

- [ ] **Step 1: Register integration marker in pyproject.toml**

Add to `[tool.pytest.ini_options]` in `pyproject.toml`:

```toml
markers = ["integration: MCP integration tests"]
```

- [ ] **Step 2: Create minimal stdio echo server for testing**

Create `tests/fixtures/echo_server.py`:

```python
#!/usr/bin/env python3
"""Minimal MCP stdio server for integration testing.

Exposes a single 'echo' tool that returns its input.
"""

import asyncio
import json
import sys

from mcp.server.lowlevel.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


server = Server("echo-test")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="echo",
            description="Echo back the input",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message to echo"},
                },
                "required": ["message"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None = None) -> list[TextContent]:
    if name == "echo":
        msg = (arguments or {}).get("message", "")
        return [TextContent(type="text", text=json.dumps({"echo": msg}))]
    return [TextContent(type="text", text=json.dumps({"error": "unknown tool"}))]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Write integration test**

Create `tests/mcp/test_integration.py`:

```python
"""Integration tests for MCP infrastructure.

Tests the full round-trip: Tool Registry → bridge → transport → protocol.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from quartermaster.core.tools import ApprovalTier, ToolRegistry
from quartermaster.mcp.client import MCPClientManager
from quartermaster.mcp.config import MCPClientEntry, MCPConfig, TransportType


ECHO_SERVER = str(Path(__file__).parent.parent / "fixtures" / "echo_server.py")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_stdio_echo_server_round_trip() -> None:
    """Connect to the echo test server via stdio and call a tool."""
    events = MagicMock()
    events.emit = AsyncMock()
    events.subscribe = MagicMock()

    tools = ToolRegistry(events=events)

    config = MCPConfig(
        clients={
            "echo": MCPClientEntry(
                transport=TransportType.STDIO,
                command=sys.executable,
                args=[ECHO_SERVER],
                default_approval_tier="autonomous",
                enabled=True,
            ),
        },
    )

    mgr = MCPClientManager(config=config, tools=tools, events=events)
    await mgr.start()

    try:
        # Tool should be registered
        tool = tools.get("echo.echo")
        assert tool is not None
        assert tool.source == "echo"
        assert tool.is_remote is True

        # Call the tool
        result = await tools.execute("echo.echo", {"message": "hello"})
        assert result == {"echo": "hello"}
    finally:
        await mgr.stop()

    # Tool should be unregistered after stop
    assert tools.get("echo.echo") is None
```

- [ ] **Step 4: Run integration test**

Run: `pytest tests/mcp/test_integration.py -v -m integration`
Expected: PASS — full round-trip through stdio works

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (integration test may be skipped without `-m integration` marker if pytest.ini is configured that way — verify)

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/echo_server.py tests/mcp/test_integration.py
git commit -m "test: MCP integration test — stdio echo server round-trip"
```

---

## Task 13: Lint, type check, and final verification

**Files:** None (verification only)

- [ ] **Step 1: Run ruff linter**

Run: `ruff check src/quartermaster/mcp/ tests/mcp/`
Expected: No errors

- [ ] **Step 2: Run mypy**

Run: `mypy src/quartermaster/mcp/`
Expected: Success

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Run integration tests**

Run: `pytest tests/mcp/test_integration.py -v`
Expected: All integration tests pass

- [ ] **Step 5: Verify Docker build**

Run: `docker build -t quartermaster:phase2 .`
Expected: Build succeeds

- [ ] **Step 6: Commit any fixes**

If linting or type checking required fixes, commit them:

```bash
git commit -m "chore: lint and type check fixes for MCP module"
```

---

## Summary

| Task | Component | Tests | Commits |
|------|-----------|-------|---------|
| 1 | mcp dependency | — | 1 |
| 2 | Config models | 12 tests | 1 |
| 3 | Tool Registry enhancements | 10 tests | 1 |
| 4 | Bridge module | 9 tests | 1 |
| 5 | Auth middleware | 7 tests | 1 |
| 6 | Transport factory | 6 tests | 1 |
| 7 | Prometheus metrics | — | 1 |
| 8 | MCP Client Manager | 7 tests | 1 |
| 9 | MCP Server | 4 tests | 1 |
| 10 | App bootstrap wiring | — | 1 |
| 11 | /status + example config | — | 1 |
| 12 | Integration test | 1 test | 1 |
| 13 | Final verification | — | 0-1 |

**Total: ~56 tests, 12-13 commits**

Build order ensures each task is independently testable: config → registry → bridge → auth → transports → metrics → client → server → wiring → integration.
