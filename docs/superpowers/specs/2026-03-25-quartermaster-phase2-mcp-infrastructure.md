# Quartermaster Phase 2 — MCP Infrastructure Design

**Date:** March 25, 2026
**Status:** Approved
**Authors:** Brian Hengen + Claude (design session)
**Phase scope:** Bidirectional MCP infrastructure — client and server

---

## 1. Overview

Phase 2 adds the Model Context Protocol (MCP) infrastructure that all subsequent phases depend on. Quartermaster becomes both an **MCP client** (consuming tools from external servers) and an **MCP server** (exposing its tools to Claude Code and other MCP clients).

### Goals

- Remote MCP server tools coexist in the Tool Registry alongside local plugin tools
- Plugins call tools without knowing if they're local or remote
- Quartermaster exposes its own registered tools as an MCP server
- Transport abstraction layer minimizes rework when transports evolve
- Production-quality: robust reconnection, monitoring, auth, and testing

### Non-Goals

- Building actual integration plugins (Gmail, Calendar, etc.) — that's Phase 3+
- Multi-user authentication or RBAC
- MCP resource or prompt capabilities (tools only for now)

---

## 2. Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| MCP SDK | Official `mcp` Python SDK | Protocol compliance, maintained by Anthropic, supports all transports |
| Primary transport | Streamable HTTP | Future of the MCP spec; stateless, proxy-friendly, production-grade |
| Transport abstraction | Config-driven factory above SDK | Minimizes rework when transports evolve; SDK handles protocol internals |
| SSE support | Client-side fallback | Existing servers (claude-memory) use SSE; support until they upgrade |
| stdio support | Client-side for bundled servers | Many community MCP servers are stdio-only |
| Server auth | Bearer token + IP allowlist | Right level for single-user self-hosted; auth layer abstracted for future upgrade to mTLS/OAuth |
| Tool namespacing | Server-prefix auto-naming | `claude-memory.search`, `filesystem.read_file`; configurable override per server |
| Remote tool approval | Default `confirm`, promoted via config | Security by default; trust granted per-server or per-tool |
| Tool notifications | Dynamic via MCP spec | `notifications/tools/list_changed` sent when Tool Registry changes |
| Server port | 9200 | Dedicated port, verified available, keeps QM endpoints in 9xxx range |

---

## 3. Module Structure

New module at `src/quartermaster/mcp/`:

```
src/quartermaster/mcp/
├── __init__.py
├── config.py          # MCPConfig, MCPServerConfig, MCPClientEntry Pydantic models
├── transports.py      # Transport factory — selects SDK transport per server config
├── auth.py            # Bearer token + IP allowlist middleware
├── client.py          # MCPClientManager — connects to external servers, bridges tools
├── server.py          # MCPServer — exposes Tool Registry via Streamable HTTP
└── bridge.py          # Bidirectional MCP ↔ QM ToolDefinition translation
```

### Integration Points

- `client.py` registers remote tools into the existing `ToolRegistry` (with server-prefix namespacing)
- `server.py` reads tools from the existing `ToolRegistry` and exposes them via MCP
- Both hook into the `EventBus` for lifecycle events (`mcp.client_connected`, `mcp.client_disconnected`, `mcp.server_started`, etc.)
- Config models extend `QuartermasterConfig` in `core/config.py`

---

## 4. Configuration

### settings.yaml Structure

```yaml
quartermaster:
  mcp:
    server:
      enabled: true
      port: 9200
      bind: "0.0.0.0"
      auth_token_file: "/app/credentials/mcp_server_token"
      allowed_hosts:
        - "127.0.0.1"
        - "192.168.1.0/24"
      approval_chat_id: "123456789"  # Brian's Telegram chat ID for confirm-tier approvals

    clients:
      claude-memory:
        transport: sse
        url: "http://memory.friendly-robots.com"
        auth_token_file: "/app/credentials/claude_memory_token"
        default_approval_tier: autonomous
        tool_overrides:
          log_lesson:
            approval_tier: confirm
        enabled: true

      filesystem:
        transport: stdio
        command: "npx"
        args: ["-y", "@modelcontextprotocol/server-filesystem", "/app/data"]
        default_approval_tier: confirm
        enabled: true

      quartermaster-loopback:
        transport: streamable_http
        url: "http://127.0.0.1:9200/mcp"
        auth_token_file: "/app/credentials/mcp_server_token"
        default_approval_tier: autonomous
        namespace: "qm-loop"
        enabled: false  # integration testing only
```

### Pydantic Config Models

`mcp/config.py` defines:

- `MCPServerConfig` — port, bind, auth_token_file, allowed_hosts, approval_chat_id (required when enabled — Brian's Telegram chat ID for routing confirm-tier approvals from MCP clients)
- `MCPClientEntry` — transport type (enum: `streamable_http`, `sse`, `stdio`), connection params (url or command+args), default_approval_tier, tool_overrides dict, namespace override, enabled flag
- `MCPConfig` — server config + dict of named client entries

Config key name is the default namespace prefix for that server's tools. The `namespace` field overrides this.

### Credential Separation

Credential file paths are stored in settings.yaml (safe to commit to public repo). Actual credential files live in `credentials/` (gitignored). This follows the pattern established in Phase 1 for the Anthropic API key.

New credential files:
- `credentials/mcp_server_token` — Bearer token for QM's MCP server endpoint

---

## 5. Transport Abstraction Layer

`mcp/transports.py` contains `MCPTransportFactory` — given an `MCPClientEntry`, it returns a connected MCP client session using the appropriate SDK transport.

### Transport Selection

```
match entry.transport:
    case TransportType.STREAMABLE_HTTP → SDK streamablehttp_client()
    case TransportType.SSE             → SDK sse_client()
    case TransportType.STDIO           → SDK stdio_client()
```

### Factory Responsibilities

- Transport selection based on config
- Auth header injection for HTTP-based transports (bearer token loaded from file)
- Connection timeout and retry config
- Returns a uniform `ClientSession` regardless of transport

### Reconnection Strategy

**HTTP transports (Streamable HTTP, SSE):**
- Exponential backoff with jitter, max 5 retries
- After max retries: mark server as `down`, emit `mcp.client_disconnected` on Event Bus
- Periodic reconnection attempts continue in background (configurable, default 60s)

**stdio:**
- If child process dies, restart with backoff
- After 3 consecutive failures: mark as `down`

All reconnection state is logged via structlog and visible in `/status` command and Prometheus metrics.

### Design Rationale

The SDK already normalizes all transports into a uniform `ClientSession`. Our factory picks the right SDK transport constructor — no need for our own transport interface hierarchy on top. The abstraction we own is at the config → connected session level.

---

## 6. Authentication Middleware

`mcp/auth.py` provides a pluggable auth layer for the MCP server.

### Current Implementation: Bearer Token + IP Allowlist

Two layers of defense, either usable alone or together:

- **Bearer token** — Client sends `Authorization: Bearer <token>` header. Token loaded from file at startup.
- **IP allowlist** — Optional list of allowed source IPs/CIDR ranges. Checked before token validation.

### Abstraction

Auth is implemented as ASGI middleware with a simple interface:

```python
class AuthMiddleware(Protocol):
    async def authenticate(self, request: Request) -> bool: ...
```

Future auth methods (mTLS, OAuth) implement the same interface and are swapped via config. No server code changes required.

### Failure Handling

- Auth failures return HTTP 401/403 with no body (don't leak information)
- All auth failures logged with source IP
- `qm_mcp_server_auth_failures_total` Prometheus counter

---

## 7. MCP Client Manager

`mcp/client.py` orchestrates all outbound MCP connections.

### Lifecycle

**Startup:**
1. Iterate enabled entries in `mcp.clients` config
2. For each: use `MCPTransportFactory` to connect
3. Fetch tool list from server
4. Register each tool into Tool Registry via bridge (with namespacing and approval tier from config)

**Running:**
- Listen for `notifications/tools/list_changed` from connected servers
- On notification: re-fetch tool list, update Tool Registry (add new, remove stale)
- Monitor connection health

**Shutdown:**
- Gracefully disconnect all client sessions
- Unregister all remote tools from Tool Registry

### Tool Registration Flow

```
MCP Server "claude-memory" exposes tool "search"
  → Bridge translates MCP tool schema → QM ToolDefinition
  → Name becomes "claude-memory.search"
  → Approval tier set from config (default_approval_tier or tool_override)
  → Handler is async closure wrapping session.call_tool()
  → source field set to "claude-memory"
  → Registered in Tool Registry like any local tool
```

The handler closure wraps the MCP SDK's `session.call_tool(name, arguments)` in a function matching the `ToolHandler` signature (`async (dict) -> dict`). From the Tool Registry's perspective, calling a remote MCP tool is identical to calling a local plugin tool.

### Error Handling

- Server fails to connect at startup → marked `down`, logged, skipped. Other servers proceed.
- Tool call to remote server fails → error returned as tool result dict (`{"error": "..."}`). LLM handles gracefully.
- Connection loss mid-session → triggers reconnection strategy from transport layer.

---

## 8. MCP Server

`mcp/server.py` exposes Quartermaster's Tool Registry to external MCP clients via Streamable HTTP.

### Exposed Capabilities

- `tools/list` — All tools in the Tool Registry (local + remote)
- `tools/call` — Execute a tool through the Tool Registry
- `notifications/tools/list_changed` — Sent when Tool Registry changes

### Not Exposed

- Conversation history or internal state
- Direct Event Bus access
- Admin/lifecycle operations

### Architecture

The server is a Starlette ASGI app served by uvicorn programmatically (via `uvicorn.Server` with `config.setup()`, not CLI). The MCP SDK provides ASGI request handlers; we wrap them in Starlette middleware for auth. This runs alongside the existing aiohttp metrics server on a separate dedicated port (9200). Dependencies `starlette` and `uvicorn` are added to requirements (unless the `mcp` SDK bundles them — check at implementation time).

### Request Flow

```
MCP Client sends: tools/list
  → Auth middleware checks bearer token + IP allowlist
  → Server reads Tool Registry via bridge.py
  → Returns MCP-formatted tool schemas

MCP Client sends: tools/call("commands.system_status", {})
  → Auth middleware validates
  → Server looks up tool in Tool Registry
  → Approval tier check:
      - autonomous → execute via ToolRegistry.execute()
      - confirm → route approval to Telegram, hold MCP request until resolved
      - notify → execute, send notification via Telegram
  → Returns result in MCP format
```

### Approval Routing for MCP Clients

When an MCP client (e.g., Claude Code) calls a `confirm`-tier tool, the approval flows through Telegram:

1. MCP server receives tool call
2. Sends approval request to Brian's Telegram chat via inline keyboard (using `mcp.server.approval_chat_id` from config — this is Brian's Telegram chat ID, required when the MCP server is enabled)
3. MCP server creates an `asyncio.Event` keyed by approval ID and subscribes to `approval.resolved` on the EventBus
4. MCP request handler `await`s the event with a timeout (matching `approval.default_timeout_minutes` from config)
5. When Brian approves/rejects on Telegram, the `approval.resolved` event fires, signaling the waiting `asyncio.Event`
6. MCP response returns the result (if approved) or an approval-rejected/expired error
7. On timeout, the approval is auto-expired and an error is returned to the MCP client

This preserves the approval flow regardless of which client triggered the tool.

### Dynamic Tool Notifications

The server subscribes to `tools.registry_changed` on the Event Bus. When fired (by Tool Registry on register/unregister), the server sends the MCP protocol's `notifications/tools/list_changed` to all connected MCP clients. Note: `tools.registry_changed` is the internal EventBus event; the MCP server translates it into the outbound MCP protocol notification. These are distinct.

### Metrics

- `qm_mcp_server_requests_total` counter (labels: method, status)
- `qm_mcp_server_connected_clients` gauge
- `qm_mcp_server_auth_failures_total` counter

---

## 9. Bridge Module

`mcp/bridge.py` is the single translation point between MCP tool schemas and QM `ToolDefinition` objects.

### MCP → QM (Client Side)

| MCP Field | QM ToolDefinition Field | Notes |
|-----------|------------------------|-------|
| `name` | `name` | Prefixed with server name |
| `description` | `description` | Passed through |
| `inputSchema` | `parameters` | Both JSON Schema; direct passthrough with validation |
| — | `handler` | Closure wrapping `session.call_tool()` |
| — | `approval_tier` | From config, not from MCP schema |
| — | `source` | Set to server name |

### QM → MCP (Server Side)

| QM ToolDefinition Field | MCP Field | Notes |
|------------------------|-----------|-------|
| `name` | `name` | Full namespaced name |
| `description` | `description` | Passed through |
| `parameters` | `inputSchema` | Direct mapping |

### Validation

- JSON Schema compatibility checks on parameter schemas
- Name uniqueness verification before Tool Registry insertion
- Incomplete MCP tools logged and skipped (don't crash the client)

### Design Rationale

Intentionally thin. Both MCP and QM use JSON Schema for parameters, so translation is structural (field name mapping) not semantic. One file to update if either side's format evolves.

---

## 10. Tool Registry Changes

Minimal, backward-compatible additions to `core/tools.py`.

### New Methods

- `unregister(name: str)` — Remove a tool. Emits `tools.registry_changed` event. Needed for MCP server disconnects and tool list updates.
- `list_by_source(source: str)` — List tools filtered by source. Used for bulk unregister on disconnect.

### Modified Methods

- `register()` — Gains a `source: str = "local"` parameter. Emits `tools.registry_changed` event after successful registration. Existing callers are unaffected because of the default value.

### New Field on ToolDefinition

- `source: str = "local"` — Tracks tool origin. Local plugin tools: `"local"`. Remote MCP tools: server name (e.g., `"claude-memory"`). Used by `list_by_source()`, `/status` display, and metrics labels.
- `is_remote` property — Computed: `return self.source != "local"`. Convenience for filtering.

### Constructor Change

`ToolRegistry` now accepts an optional `EventBus` in its constructor. When `None`, `register()` and `unregister()` skip event emission. This preserves true backward compatibility — existing tests that construct `ToolRegistry()` with no arguments continue to work.

```python
# Before
self._tools = ToolRegistry()

# After (app.py)
self._tools = ToolRegistry(events=self._events)

# Tests still work
self._tools = ToolRegistry()  # events=None, no event emission
```

### Name Collision Handling

If a remote tool name collides with an existing tool (after namespacing), the bridge logs a warning and skips the remote tool. No crash. Local tools always take priority.

### Backward Compatibility

All existing methods (`get()`, `list_tools()`, `get_tool_schemas()`, `execute()`) unchanged. Existing plugins and tests continue to work — `source` defaults to `"local"`, `events` defaults to `None`, and no existing call sites need updating.

---

## 11. Application Bootstrap Changes

### Startup Order (new steps in bold)

1. Load config
2. Create EventBus
3. Create ToolRegistry **(now receives EventBus)**
4. Connect to Oracle
5. Create UsageTracker, LLMRouter, ConversationManager, Scheduler, TransportManager, ApprovalManager
6. **Create MCPServer (not started yet — no tools registered)**
7. Build PluginContext **(now includes optional mcp_client field)**
8. Load plugins (register local tools)
9. **Start MCPClientManager — connect to configured servers, bridge remote tools into registry**
10. **Start MCPServer — full tool set now available**
11. Start transports, start scheduler

### Shutdown Order

1. Stop scheduler
2. Stop transports
3. **Stop MCPServer — disconnect MCP clients gracefully**
4. **Stop MCPClientManager — disconnect from remote servers, unregister tools**
5. Teardown plugins
6. Stop metrics
7. Close database

### Ordering Rationale

- MCP client starts after plugins so local tools are in the registry first
- MCP server starts after MCP client so the full tool set (local + remote) is exposed from first connection
- MCP server stops before MCP client on shutdown — clients get clean disconnect before remote tools are torn down

### PluginContext Addition

```python
@dataclass
class PluginContext:
    # ... existing fields ...
    mcp_client: Any = None  # MCPClientManager
```

---

## 12. Monitoring Integration

### Prometheus Metrics

**MCP Client:**
- `qm_mcp_client_status` gauge (labels: server) — 1=up, 0=down, 0.5=degraded
- `qm_mcp_client_reconnect_total` counter (labels: server)
- `qm_mcp_tool_calls_total` counter (labels: server, tool, status=success/error)
- `qm_mcp_tool_call_duration_seconds` histogram (labels: server, tool)

**MCP Server:**
- `qm_mcp_server_requests_total` counter (labels: method, status)
- `qm_mcp_server_connected_clients` gauge
- `qm_mcp_server_auth_failures_total` counter

### /status Command

```
MCP Clients:
  claude-memory (sse): up — 12 tools
  filesystem (stdio): up — 4 tools

MCP Server:
  Streamable HTTP on :9200 — 28 tools exposed, 1 client connected
```

### Health Events

MCP client manager emits `mcp.client.health_changed` events on state transitions (not `plugin.health_changed`, since the MCP client manager is a core service, not a plugin). The `/status` command and health monitoring treat it as a virtual component with the well-known name `"mcp-client"`.

---

## 13. Testing Strategy

### Unit Tests (mocked dependencies)

| File | Coverage |
|------|----------|
| `tests/mcp/test_bridge.py` | Schema translation both directions, edge cases, invalid schemas |
| `tests/mcp/test_config.py` | Config model validation, valid/invalid configs |
| `tests/mcp/test_auth.py` | Bearer token validation, IP allowlist (exact + CIDR), rejection |
| `tests/mcp/test_transports.py` | Factory selects correct SDK transport per config |
| `tests/mcp/test_client.py` | Register/unregister, disconnect handling, approval tier, namespacing |
| `tests/mcp/test_server.py` | Tool list, call routing, auth rejection, approval tier enforcement |

### Updated Existing Tests

- `tests/core/test_tools.py` — `unregister()`, `list_by_source()`, event emission. Existing tests updated for EventBus constructor.

### Integration Tests

- `tests/mcp/test_integration.py` — **Loopback test:** Uses `pytest-asyncio`, starts the MCP server on a random available port, generates a temporary auth token, configures a client entry pointing at `localhost:<port>`, and validates a tool call round-trip. Server and client are torn down in the fixture.
- SSE client test against a mock SSE server fixture.
- stdio client test against a minimal test server script in `tests/fixtures/`.

### Post-Deployment Validation (Phase 2 completion)

- Smoke tests against real endpoints (claude-memory)
- Health check integration with `claude-healthcheck.sh` cron
- Manual validation with Claude Code as MCP client

---

## 14. Dependencies

### New Python Dependencies

```
mcp>=1.0.0,<2.0.0    # Official MCP SDK (Anthropic/ModelContextProtocol)
```

Pin to exact tested version during implementation. The SDK pulls in dependencies for Streamable HTTP, SSE, and stdio transports. `httpx` and `pydantic` are already in the project. `starlette` and `uvicorn` may be needed if not bundled by the SDK — verify at implementation time.

The MCP SDK handles protocol version negotiation. Quartermaster uses whatever protocol version the SDK supports. No custom version handling is needed.

### Dockerfile Changes

- Add `mcp` (and `starlette`/`uvicorn` if needed) to `requirements.txt`
- No new system packages required
- Note: `docker-compose.yml` needs no changes for port 9200 — host networking mode exposes it automatically. Ensure IP allowlist is configured to restrict access to trusted hosts.
- **stdio transport note:** The base image (`python:3.13-slim`) has no Node.js. stdio MCP servers requiring Node.js need it added to the Dockerfile. The `MCPClientManager` validates that configured stdio commands exist at startup and logs a clear error if missing, rather than failing at first tool call.

---

## 15. Files Changed Summary

| Component | Files | Type |
|-----------|-------|------|
| MCP module | 6 new in `src/quartermaster/mcp/` | New |
| Tool Registry | `src/quartermaster/core/tools.py` | Modified |
| App bootstrap | `src/quartermaster/core/app.py` | Modified |
| Plugin context | `src/quartermaster/plugin/context.py` | Modified |
| Config models | `src/quartermaster/core/config.py` | Modified |
| Settings example | `config/settings.example.yaml` | Modified |
| Requirements | `requirements.txt` | Modified |
| Tests | ~8 new in `tests/mcp/` | New |

No existing behavior changes. Phase 1 plugins and tests continue to work unmodified.

---

## 16. Connection to Future Phases

This MCP infrastructure is the foundation for Phases 3-6:

| Phase | How It Uses MCP |
|-------|-----------------|
| 3 (Email + Calendar + News) | Gmail, O365, Calendar as MCP servers or plugins calling MCP tools |
| 4 (App Store + Revenue) | App Store Connect, Google Play as MCP tool providers |
| 5 (Social Media) | Facebook, Instagram, X, TikTok — complex MCP servers built on Streamable HTTP |
| 6 (Infrastructure Control) | Claude Code headless as MCP client to QM's server |
| 7 (WhatsApp) | Transport only — no MCP changes needed |

The transport abstraction ensures that when the MCP ecosystem evolves (new transports, protocol versions), the rework is limited to adding a new transport adapter behind the existing factory interface.

---

*Designed in a collaborative session, March 25, 2026.*
