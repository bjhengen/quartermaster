# Quartermaster Phase 3b — O365 Outlook Integration Design

**Date:** March 27, 2026
**Status:** Approved
**Authors:** Brian Hengen + Claude (design session)
**Phase scope:** O365 email integration — 2 accounts via Microsoft Graph API, implementing existing EmailProvider protocol

---

## 1. Overview

Phase 3b adds Outlook/O365 email integration as the second email provider. Two accounts under the same GoDaddy M365 tenant (`brian@friendly-robots.com` and `support@friendly-robots.com`) are wired into the existing unified email plugin. Minimal plugin changes — register the new provider class, add `provider_type` and `close()` to the protocol, fix health reporting. All tools, routing, metrics, and aggregation work automatically.

### Goals

- `OutlookProvider` implementing the existing `EmailProvider` protocol
- Two O365 accounts operational (same tenant, one Azure AD app registration)
- Same capabilities as Gmail: search, read, send, draft, reply
- MSAL device code flow for headless-friendly OAuth setup
- Minimal plugin changes: register new provider, fix health reporting, add provider cleanup

### Non-Goals

- Calendar integration (Phase 3c/3d)
- Exchange-specific features (rules, categories, shared mailboxes)
- Application-level permissions (daemon/service access without user context)

---

## 2. Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Auth library | `msal` (Microsoft Authentication Library) | Official, handles token refresh, device code flow for headless setup |
| HTTP client | `httpx.AsyncClient` | Already in project, natively async, no wrapping needed for Graph API calls |
| Graph API version | v1.0 | Stable; beta not needed for Mail operations |
| OAuth flow | Device code (setup) + refresh token (runtime) | Headless-friendly — no browser needed on slmbeast |
| App registration | Single app, Public client type | One registration serves both accounts; delegated permissions |
| Token persistence | MSAL `SerializableTokenCache` saved as credential JSON | MSAL manages refresh tokens internally; we persist the cache to disk |
| Provider cleanup | `close()` method on `EmailProvider` protocol | Closes `httpx.AsyncClient`; plugin calls on teardown |

---

## 3. Configuration

### settings.yaml Additions

```yaml
quartermaster:
  email:
    accounts:
      # ... existing Gmail accounts ...
      fr-brian:
        provider: outlook
        credential_file: "credentials/outlook_brian.json"
        label: "FR Brian"
      fr-support:
        provider: outlook
        credential_file: "credentials/outlook_support.json"
        label: "FR Support"
```

Same `EmailAccountConfig` model — `provider: outlook` triggers `OutlookProvider` instantiation.

### Credential File Format

```json
{
  "client_id": "...",
  "tenant_id": "...",
  "email_address": "brian@friendly-robots.com",
  "token_cache": "...serialized MSAL cache JSON..."
}
```

- `client_id` and `tenant_id` — from the Entra app registration
- `email_address` — identifies the mailbox; used in logging and `/status`
- `token_cache` — serialized MSAL `SerializableTokenCache` containing access and refresh tokens. MSAL manages token lifecycle internally; the provider persists the cache when `cache.has_state_changed` is true.

Written by the OAuth setup script. Updated at runtime via atomic write when MSAL refreshes tokens.

---

## 4. Azure AD App Registration (Pre-requisite)

One-time setup in [Entra ID](https://entra.microsoft.com):

1. **App registrations > New registration**
   - Name: "Quartermaster"
   - Supported account types: "Accounts in this organizational directory only"
   - Redirect URI: Public client/native, `http://localhost`

2. **API permissions > Add a permission > Microsoft Graph > Delegated:**
   - `Mail.ReadWrite` — read, send, draft, reply, delete
   - `User.Read` — profile/health check
   - `offline_access` — refresh token persistence

3. **Authentication > Advanced settings:**
   - Enable "Allow public client flows" = Yes

4. Note the **Application (client) ID** and **Directory (tenant) ID** from the Overview page.

No admin consent required for these delegated permissions — each user consents during the device code flow.

---

## 5. OutlookProvider Implementation

New file at `src/quartermaster/email/outlook.py`.

### Auth & Token Management

Uses MSAL's `SerializableTokenCache` for token lifecycle — not raw refresh token manipulation. MSAL manages access token expiry, refresh token rotation, and cache state internally.

- `connect()` — loads credential file (which contains a serialized MSAL token cache). Creates `PublicClientApplication` with the cache attached. Calls `acquire_token_silent()` to get a valid access token (MSAL handles refresh if needed). Wraps in `asyncio.to_thread()` since MSAL is synchronous. If `cache.has_state_changed`, persists the updated cache back to the credential file atomically.
- `_get_token()` — called before each Graph API request. Calls `acquire_token_silent()` via `asyncio.to_thread()`. If the access token is still valid, MSAL returns it from cache instantly. If expired, MSAL refreshes silently. Persists cache if state changed. Returns the access token string for the `Authorization: Bearer` header.
- The credential file stores the full MSAL serialized cache (JSON) plus `client_id`, `tenant_id`, and `email_address` metadata. The OAuth setup script creates this file initially; the provider updates it at runtime when tokens refresh.

**Credential file format (updated):**

```json
{
  "client_id": "...",
  "tenant_id": "...",
  "email_address": "brian@friendly-robots.com",
  "token_cache": "...serialized MSAL cache JSON..."
}
```

### Graph API Endpoints

| Method | Endpoint | Notes |
|--------|----------|-------|
| `get_unread_summary` | `GET /me/messages?$filter=isRead eq false&$top={N}&$select=id,subject,from,receivedDateTime,bodyPreview,isRead` | Uses `$select` to minimize payload |
| `search` | `GET /me/messages?$search="{query}"&$top={N}` | Requires `ConsistencyLevel: eventual` header. Graph KQL search syntax. |
| `read` | `GET /me/messages/{id}` | Full message with body |
| `send` | `POST /me/sendMail` | JSON body with message object |
| `draft` | `POST /me/messages` | Creates message as draft (isDraft=true by default) |
| `reply` | `POST /me/messages/{id}/reply` | Graph handles threading automatically |
| `health_check` | `GET /me/mailFolders/inbox` | Lightweight check that auth + mailbox work |

### Async Approach

- MSAL calls: `asyncio.to_thread()` (synchronous library)
- Graph API calls: `httpx.AsyncClient` directly (natively async)
- One `httpx.AsyncClient` instance per provider, created in `connect()`, closed in cleanup

### Response Parsing

Graph API returns JSON. Map to existing models:

| Graph Field | EmailSummary/EmailMessage Field |
|-------------|-------------------------------|
| `id` | `id` |
| `subject` | `subject` |
| `from.emailAddress.address` | `sender` |
| `receivedDateTime` | `date` |
| `bodyPreview` | `snippet` |
| `isRead` | `is_read` |
| `body.content` | `body` (strip HTML if contentType is "html") |
| `conversationId` | `thread_id` |
| `toRecipients[].emailAddress.address` | `to` |
| `ccRecipients[].emailAddress.address` | `cc` |
| `hasAttachments` + `attachments` | `attachments` |

### HTML Body Handling

Graph API returns email bodies as HTML by default. The provider requests `Prefer: outlook.body-content-type="text"` header to get plain text where available. For emails that are HTML-only, strip tags with a simple regex or `html.parser` — no external dependency needed.

---

## 6. OAuth Setup Script

`scripts/outlook_oauth_setup.py` — MSAL device code flow:

```
python scripts/outlook_oauth_setup.py \
  --client-id <app-client-id> \
  --tenant-id <tenant-id> \
  --account-name fr-brian
```

Flow:
1. Creates MSAL `PublicClientApplication` with client_id and authority (`https://login.microsoftonline.com/{tenant_id}`)
2. Initiates device code flow with fully-qualified scopes: `https://graph.microsoft.com/Mail.ReadWrite`, `https://graph.microsoft.com/User.Read`, `offline_access` (Graph-specific scopes require the full URI prefix; `offline_access` is an identity platform scope and does not)
3. Prints URL and code for user to enter in any browser
4. Waits for authentication
5. Extracts `email_address` from the ID token (or calls `/me` endpoint)
6. Writes credential file to `credentials/outlook_{account_name}.json`

Run once per account. Second run reuses `--client-id` and `--tenant-id`.

---

## 7. Plugin and Protocol Changes

### Provider registration (1 line)

```python
from quartermaster.email.outlook import OutlookProvider

mapping = {
    "gmail": GmailProvider,
    "outlook": OutlookProvider,
}
```

### EmailProvider protocol additions

Two additions to `src/quartermaster/email/provider.py`:

1. **`provider_type` property** — returns `"gmail"` or `"outlook"`. Used by `health()` to report the correct provider in `/status` output. Replaces the hard-coded `"provider": "gmail"` in the plugin's health details.

2. **`close()` async method** — called by the plugin's `teardown()` for resource cleanup. The `OutlookProvider` closes its `httpx.AsyncClient`; `GmailProvider` is a no-op (Google SDK uses short-lived HTTP connections).

### Plugin fixes

- `health()` — use `provider.provider_type` instead of hard-coded `"gmail"`
- `teardown()` — call `await provider.close()` for each provider before clearing

---

## 8. Error Handling

Same per-account isolation as Gmail:
- Credential file missing → account skipped, logged as unhealthy
- Refresh token expired/revoked → MSAL raises, caught, account marked unhealthy
- Graph API errors (403, 429, 5xx) → caught per-call, returned as error dict
- Network errors → caught, returned as error dict
- One account failing doesn't affect others

### Token Expiry

Microsoft refresh tokens for M365 are long-lived (90 days rolling) but can be revoked by admin policy. If token refresh fails, the account is marked unhealthy and the setup script needs to be re-run.

---

## 9. Testing Strategy

### Unit Tests

`tests/email/test_outlook.py`:
- `test_connect_acquires_token` — mock MSAL, verify token acquisition
- `test_connect_refreshes_expired_token` — mock MSAL silent refresh
- `test_health_check_true/false` — mock Graph API inbox endpoint
- `test_get_unread_summary` — mock Graph API list messages response
- `test_search` — mock Graph API search, verify KQL query formatting
- `test_read` — mock Graph API get message, verify full model parsing including HTML stripping
- `test_send` — mock Graph API sendMail, verify request body format
- `test_draft` — mock Graph API create message
- `test_reply` — mock Graph API reply endpoint
- `test_properties` — account_name, label

### Updated Plugin Tests

`tests/plugins/test_email_plugin.py`:
- Add test with mixed gmail + outlook providers to verify multi-provider routing

### No Integration Test

Real Graph API testing requires live M365 credentials — same as Gmail, deferred to manual validation after deployment.

---

## 10. Dependencies

### New Python Dependency

```
msal>=1.0.0
```

### Files Summary

| Component | Files | Type |
|-----------|-------|------|
| Outlook provider | `src/quartermaster/email/outlook.py` | New |
| OAuth setup | `scripts/outlook_oauth_setup.py` | New |
| Provider protocol | `src/quartermaster/email/provider.py` | Modified (add `provider_type`, `close()`) |
| Gmail provider | `src/quartermaster/email/gmail.py` | Modified (add `provider_type`, no-op `close()`) |
| Plugin | `plugins/email/plugin.py` | Modified (register provider, fix health, add teardown cleanup) |
| Config example | `config/settings.example.yaml` | Modified |
| Requirements | `requirements.txt` | Modified |
| Tests | `tests/email/test_outlook.py` | New |
| Tests | `tests/plugins/test_email_plugin.py` | Modified |

---

## 11. Connection to Future Sub-Phases

| Sub-Phase | How It Builds on 3b |
|-----------|-------------------|
| 3d (O365 Calendar) | Reuses same Entra app registration and MSAL credential pattern. Add `Calendars.ReadWrite` scope. Separate calendar plugin + provider. |
| 3f (Enhanced Briefings) | `email.unread_summary` now aggregates 4 accounts (2 Gmail + 2 Outlook) automatically. |

---

*Designed in a collaborative session, March 27, 2026.*
