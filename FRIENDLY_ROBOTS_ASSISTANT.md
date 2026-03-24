# Friendly Robots Personal Assistant — Project Spec

**Date:** March 24, 2026
**Status:** Planning
**Author:** Brian Hengen + Claude (research & design session on hostmodel)

---

## Vision

A self-hosted personal AI assistant for Friendly Robots that communicates via Telegram (and optionally WhatsApp), manages daily workflows, monitors app store performance, assists with social media marketing, and serves as a unified command center for Brian's projects and infrastructure.

This is also intended as material for a blog post series documenting the build process.

---

## Why Build Our Own?

We evaluated **OpenClaw** (334K stars, full-featured AI assistant platform) and **NanoClaw** (25K stars, minimal Claude-native assistant) and concluded that building custom is the right call:

| Factor | OpenClaw | NanoClaw | Custom |
|--------|----------|----------|--------|
| LLM conflict with llama-swap | Model swaps disrupt GPU work | N/A (cloud only) | Smart queue — use local when idle, Claude API fallback |
| App store monitoring | Not built-in | Not built-in | First-class feature |
| Social media marketing | Not built-in | Not built-in | First-class feature |
| Gmail/Calendar | Via `gog` CLI (indirect) | Via MCP (Claude API costs) | Direct Google API (free, reuse ledgr patterns) |
| Cost | Free (local LLM) | $30-80/month API | Free local + minimal Claude fallback |
| Complexity | 334K-star codebase, frequent breaking changes | 20-file codebase but Claude-locked | Exactly what we need, nothing we don't |
| Infrastructure fit | Node.js, would coexist awkwardly | Docker containers per interaction | Python, systemd, native to slmbeast |

**Key insight:** Neither framework has app store or social media capabilities. We'd be writing the hard parts regardless — might as well own the whole stack.

---

## Architecture

### Core: Event-Driven Async Daemon

```
┌──────────────────────────────────────────────────────────┐
│  Python asyncio event loop (systemd service)             │
│  ~30-50 MB idle, zero CPU between events                 │
│                                                          │
│  Event Sources:                                          │
│  ├─ Telegram long-polling (instant message delivery)     │
│  ├─ Scheduled task timers (asyncio-native)               │
│  ├─ Webhook listener (localhost HTTP for cron scripts)   │
│  └─ (Future) WAHA webhook for WhatsApp                   │
│                                                          │
│  LLM Backend (smart routing):                            │
│  ├─ Check llama-swap /running endpoint                   │
│  ├─ If idle → qwen3.5-27b via localhost:8200             │
│  ├─ If busy → queue (short wait) or Claude API fallback  │
│  └─ Tool calling for structured actions                  │
│                                                          │
│  State: SQLite (conversation history, task state, cache)  │
└──────────────────────────────────────────────────────────┘
```

### LLM Strategy

The assistant shares the GPU with ComfyUI, training jobs, and other llama-swap consumers. It must be a good citizen:

1. **Check before calling:** `GET http://localhost:8200/running` — if empty or qwen3.5-27b is loaded, proceed
2. **If another model is loaded:** Queue the request briefly (5-10s for swap) or fall back to Claude API for time-sensitive messages
3. **Never interrupt GPU-intensive work:** If ComfyUI or a training job is running, use Claude API
4. **Scheduled tasks with LLM:** Run during known idle windows (overnight training pauses at 7 AM, resumes at 8 PM)

### Component Map

```
~/dev/fr_assistant/              (or whatever we name it)
├── bot/
│   ├── main.py                  # Entry point, event loop
│   ├── telegram_handler.py      # python-telegram-bot integration
│   ├── llm_router.py            # Smart LLM routing (local vs cloud)
│   ├── conversation.py          # History management, SQLite
│   └── scheduler.py             # Scheduled task engine
├── integrations/
│   ├── gmail.py                 # Google Gmail API (reuse ledgr patterns)
│   ├── calendar.py              # Google Calendar API
│   ├── appstore.py              # App Store Connect API
│   ├── playstore.py             # Google Play Developer API
│   ├── twitter.py               # X/Twitter API
│   └── facebook.py              # Facebook Graph API (Pages)
├── skills/
│   ├── briefing.py              # Daily morning briefing
│   ├── app_monitor.py           # App store health checks
│   ├── review_responder.py      # Review alert + draft responses
│   ├── social_publisher.py      # Draft → approve → publish flow
│   ├── infra_monitor.py         # Service health, Docker, disk
│   └── memory_bridge.py         # claude-memory MCP integration
├── config/
│   ├── settings.yaml            # All configuration
│   └── credentials/             # OAuth tokens, API keys (gitignored)
├── data/
│   ├── assistant.db             # SQLite database
│   └── media/                   # Cached images, generated content
├── fr_assistant.service         # systemd unit file
├── requirements.txt
├── CLAUDE.md
└── README.md
```

---

## Feature Breakdown

### Phase 1: Core Bot (MVP)

**Goal:** Working Telegram bot that can chat using local LLMs with Claude fallback.

- [ ] Telegram bot setup via @BotFather
- [ ] `python-telegram-bot` async handler with long-polling
- [ ] LLM router: check llama-swap status → route to local or Claude API
- [ ] Conversation history in SQLite (per-chat, configurable retention)
- [ ] User allowlist (just Brian)
- [ ] systemd service with auto-restart
- [ ] "Typing" indicator while waiting for LLM response
- [ ] Basic commands: `/status` (system info), `/models` (loaded model), `/help`

**Libraries:**
- `python-telegram-bot` (29K stars, async, mature)
- `httpx` or `aiohttp` (async HTTP for llama-swap + Claude API)
- `sqlite3` (stdlib) or `aiosqlite`

### Phase 2: Google Integration

**Goal:** Gmail and Calendar management from Telegram.

- [ ] Google OAuth setup (Desktop app credentials, token persistence)
- [ ] Gmail: search, read, send, draft — reuse patterns from ledgr's MCP server
- [ ] Calendar: list events, create events, daily agenda
- [ ] Morning briefing scheduled task: weather + calendar + unread email summary
- [ ] Natural language: "What's on my calendar today?" / "Send an email to X about Y"

**Libraries:**
- `google-api-python-client`
- `google-auth-httplib2`, `google-auth-oauthlib`

### Phase 3: App Store Monitoring

**Goal:** Daily visibility into how wine.dine Pro, recipe.sync, and future apps are performing.

- [ ] **App Store Connect API** integration (JWT auth, REST API)
  - Downloads & sales data
  - Ratings & reviews (new review alerts)
  - Crash reports (spike detection)
  - App status (review state, rejection alerts)
- [ ] **Google Play Developer API** integration (service account auth)
  - Install stats, ratings, reviews
  - ANR/crash rates
  - Store listing performance
- [ ] Daily digest: "Your apps yesterday — wine.dine Pro: 12 downloads, 4.8 stars, 1 new review"
- [ ] Instant alerts: new negative review, crash spike, app rejection
- [ ] LLM-assisted review response drafts
- [ ] Trend tracking over time (SQLite + simple charts via matplotlib)

**APIs:**
- App Store Connect API (free, JWT auth, official)
- Google Play Developer API (free, service account, official)

### Phase 4: Social Media & Marketing

**Goal:** LLM-assisted content creation with human-in-the-loop publishing.

- [ ] **X/Twitter** integration (free tier: 1,500 posts/month)
  - Draft posts about app updates, features, tips
  - "Draft a tweet about the new recipe import feature in recipe.sync"
  - Approval flow: LLM drafts → sends to Telegram for review → Brian approves → posts
  - Engagement monitoring (likes, retweets, replies)
- [ ] **Facebook Pages** integration (Graph API)
  - Similar draft → approve → publish flow
  - Cross-post from X with platform-appropriate formatting
- [ ] **Content calendar:** Schedule posts via Google Calendar integration
- [ ] **Competitor monitoring:** Periodic web search for competing apps, summarize changes
- [ ] **ASO suggestions:** Analyze keywords, ratings trends, suggest App Store description updates

**APIs:**
- X API v2 (free tier sufficient for indie apps)
- Facebook Graph API (Pages, free)

### Phase 5: Infrastructure Integration

**Goal:** Unified view of Brian's homelab from Telegram.

- [ ] Service monitoring: llama-swap, ComfyUI, Open WebUI, Docker containers
- [ ] Disk space alerts (/u01, /u02 thresholds)
- [ ] GPU status: VRAM usage, temperature, running processes
- [ ] Backup verification: check last restic snapshot age
- [ ] Docker container health: restart counts, log errors
- [ ] Webhook endpoint for existing cron scripts to push notifications
- [ ] claude-memory integration: search lessons, log from Telegram

### Phase 6: WhatsApp (Optional)

**Goal:** Same assistant, also available on WhatsApp.

- [ ] WAHA Docker container (REST API wrapper for WhatsApp Web)
- [ ] Webhook handler forwarding to same LLM pipeline
- [ ] Shared conversation context across channels (or separate, configurable)
- [ ] Use a **dedicated SIM** to avoid ban risk on personal number

---

## Messaging Platform Comparison

| Factor | Telegram | WhatsApp (WAHA) | WhatsApp (Business API) |
|--------|----------|-----------------|------------------------|
| Setup time | 5 minutes | 15 minutes | 1-2 hours |
| Cost | Free | Free (core) | Free (1K convos/month) |
| Ban risk | None (official API) | Moderate (unofficial) | None (official) |
| Proactive messages | Trivial | Works (ban risk) | Template-only (restrictive) |
| Protocol stability | Stable, versioned API | Can break on WhatsApp updates | Stable |
| Library | python-telegram-bot (29K stars) | REST API (language-agnostic) | Meta SDK |

**Decision:** Start with Telegram. Add WhatsApp via WAHA later if desired.

---

## Infrastructure

### Host: slmbeast

- Ubuntu Linux, RTX 5090 (32GB VRAM)
- llama-swap on port 8200 (22 local LLMs, qwen3.5-27b primary)
- Claude API access (Anthropic) for fallback
- Docker for WAHA (future WhatsApp)
- Existing services: ComfyUI, Open WebUI, Grafana, Prometheus, vitals-hub, ledgr

### Dependencies

```
python-telegram-bot>=22.0    # Telegram bot framework (async)
httpx                         # Async HTTP client (llama-swap, Claude API)
aiosqlite                     # Async SQLite
google-api-python-client      # Gmail, Calendar, Play Store
google-auth-oauthlib          # Google OAuth
pyjwt                         # App Store Connect JWT auth
cryptography                  # App Store Connect key handling
pyyaml                        # Configuration
```

### Resource Budget

- **Idle:** ~30-50 MB RAM, zero CPU (long-polling wait)
- **Active:** Brief spikes during LLM calls (~100 MB)
- **No GPU usage** — delegates to llama-swap or Claude API
- **Disk:** SQLite DB + logs, minimal

---

## Smart LLM Routing (Key Design Decision)

```python
async def route_llm_request(messages, tools=None):
    """Pick the best available LLM backend."""

    # 1. Check what's loaded in llama-swap
    running = await httpx.get("http://localhost:8200/running")
    loaded_models = running.json().get("running", [])

    # 2. If our preferred model is loaded or nothing is loaded, use local
    if not loaded_models or "qwen3.5-27b" in [m["model"] for m in loaded_models]:
        try:
            return await call_llama_swap(messages, tools, timeout=60)
        except TimeoutError:
            pass  # Fall through to Claude

    # 3. If a different model is loaded, check if it's a quick swap
    #    (small model → fast unload, or TTL about to expire)
    #    vs a heavy job (ComfyUI generation, training)
    if is_gpu_busy():  # nvidia-smi check
        return await call_claude_api(messages, tools)

    # 4. Default: try local with longer timeout (model swap)
    try:
        return await call_llama_swap(messages, tools, timeout=120)
    except TimeoutError:
        return await call_claude_api(messages, tools)
```

---

## Approval Flow for Publishing (Key UX Pattern)

For any action that has external consequences (sending emails, posting to social media, responding to reviews), the bot uses a **draft → approve → execute** pattern:

```
Bot: Here's a draft tweet for the recipe.sync update:

     "recipe.sync v1.0.1 is live! Now with faster recipe
     import from any website. Try it free 🍳
     https://apps.apple.com/..."

     [✅ Post] [✏️ Edit] [❌ Cancel]

Brian: [taps ✅ Post]

Bot: Posted to X. https://x.com/friendlyrobots/status/...
```

Telegram inline keyboards make this interaction clean and mobile-friendly.

---

## Blog Post Series Outline

1. **"Building a Self-Hosted AI Assistant with Local LLMs"** — Architecture, Telegram setup, llama-swap integration, smart routing
2. **"Your Apps, Your Data: App Store Monitoring Without Third-Party Services"** — App Store Connect API, Play Console API, daily digests
3. **"LLM-Powered Social Media for Indie Developers"** — Draft→approve→publish flow, X and Facebook integration
4. **"The $0/Month AI Assistant"** — Cost comparison vs cloud services, self-hosting philosophy
5. **"Connecting Everything: Gmail, Calendar, and Infrastructure Monitoring"** — Google API integration, proactive notifications

---

## Related Prior Work

- **ledgr project:** Gmail MCP server patterns (OAuth, token management) — reusable
- **claude-memory MCP:** Shared memory system — bridge to bot for cross-session context
- **hostmodel/llama-swap:** LLM infrastructure the bot will consume
- **daily-status-check.sh / claude-healthcheck.sh:** Existing monitoring scripts that could push to the bot's webhook

---

## Open Questions

1. **Project name?** `fr_assistant`? `friendly-bot`? `clawless`? (tongue-in-cheek nod to the claw projects we didn't use)
2. **Qwen3.5 tool calling:** How reliable is function calling via llama-swap for structured actions (email, calendar, app store queries)? Need to benchmark.
3. **Multi-model routing:** Should different tasks use different models? (e.g., 35B MoE for content generation, 27B for reasoning/tool use)
4. **MCP integration:** Should the bot expose its own MCP server so Claude Code sessions can interact with it? Or consume existing MCP servers?
5. **Conversation memory:** Local SQLite only, or bridge to claude-memory for cross-project context?
6. **Blog format:** Step-by-step tutorial style, or narrative "here's what we built and why"?

---

## Next Steps

1. Create project directory and initialize
2. Brainstorm + refine architecture in a dedicated CC session
3. Phase 1 MVP: Telegram bot + LLM routing + basic chat
4. Iterate from there based on what's most useful day-to-day

---

*Generated from a research session on the hostmodel project, March 24, 2026.
Brian and Claude evaluated OpenClaw, NanoClaw, and custom-build approaches
before deciding to build a tailored solution.*
