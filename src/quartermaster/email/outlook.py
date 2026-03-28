"""Outlook provider — Microsoft Graph API client via MSAL + httpx."""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
import structlog
from msal import PublicClientApplication, SerializableTokenCache

from quartermaster.email.models import AttachmentInfo, EmailMessage, EmailSummary

logger = structlog.get_logger()

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPES = [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Calendars.ReadWrite",
]


class OutlookProvider:
    """Microsoft Graph email provider using MSAL for auth.

    MSAL handles token lifecycle via SerializableTokenCache.
    httpx.AsyncClient handles Graph API calls (natively async).
    """

    def __init__(
        self,
        account_name: str,
        label: str,
        credential_file: str,
    ) -> None:
        self._account_name = account_name
        self._label = label
        self._credential_file = credential_file
        self._access_token: str | None = None
        self._http: httpx.AsyncClient | None = None
        self._msal_app: PublicClientApplication | None = None
        self._cache: SerializableTokenCache | None = None
        self._client_id: str = ""
        self._tenant_id: str = ""
        self._email: str = ""

    @property
    def account_name(self) -> str:
        return self._account_name

    @property
    def label(self) -> str:
        return self._label

    @property
    def provider_type(self) -> str:
        return "outlook"

    async def connect(self) -> None:
        """Load credentials, acquire token via MSAL, create httpx client."""

        def _connect() -> str:
            cred_path = Path(self._credential_file)
            cred_data = json.loads(cred_path.read_text())
            self._client_id = cred_data["client_id"]
            self._tenant_id = cred_data["tenant_id"]
            self._email = cred_data.get("email_address", "")

            # Load MSAL token cache
            self._cache = SerializableTokenCache()
            token_cache_str = cred_data.get("token_cache", "")
            if token_cache_str:
                self._cache.deserialize(token_cache_str)

            authority = f"https://login.microsoftonline.com/{self._tenant_id}"
            self._msal_app = PublicClientApplication(
                client_id=self._client_id,
                authority=authority,
                token_cache=self._cache,
            )

            accounts = self._msal_app.get_accounts()
            if not accounts:
                raise RuntimeError(
                    f"No accounts found in MSAL cache for {self._account_name}. "
                    f"Run scripts/outlook_oauth_setup.py to authenticate."
                )

            result = self._msal_app.acquire_token_silent(
                scopes=GRAPH_SCOPES,
                account=accounts[0],
            )
            if result is None or "access_token" not in result:
                error = (result or {}).get("error_description", "unknown error")
                raise RuntimeError(
                    f"Failed to acquire token for {self._account_name}: {error}"
                )

            # Persist cache if tokens were refreshed
            if self._cache.has_state_changed:
                self._persist_cache()

            return result["access_token"]

        self._access_token = await asyncio.to_thread(_connect)
        self._http = httpx.AsyncClient(
            base_url=GRAPH_BASE,
            headers={
                "Prefer": 'outlook.body-content-type="text"',
            },
            timeout=30.0,
        )
        logger.info(
            "outlook_provider_connected",
            account=self._account_name,
            email=self._email,
        )

    async def health_check(self) -> bool:
        """Check if Graph API is accessible."""
        if self._http is None or self._access_token is None:
            return False
        try:
            await self._refresh_token_if_needed()
            resp = await self._http.get(
                "/me/mailFolders/inbox", headers=self._auth_headers()
            )
            return resp.status_code == 200
        except Exception as exc:
            logger.warning(
                "outlook_health_check_failed",
                account=self._account_name,
                error=str(exc),
            )
            return False

    async def close(self) -> None:
        """Close the httpx client."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_unread_summary(self, max_results: int = 20) -> list[EmailSummary]:
        """Get unread email summaries via Graph API."""
        await self._refresh_token_if_needed()
        resp = await self._http.get(
            "/me/messages",
            params={
                "$filter": "isRead eq false",
                "$top": max_results,
                "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
                "$orderby": "receivedDateTime desc",
            },
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        return [self._parse_summary(msg) for msg in data.get("value", [])]

    async def search(self, query: str, max_results: int = 10) -> list[EmailSummary]:
        """Search emails using Graph KQL search syntax."""
        await self._refresh_token_if_needed()
        resp = await self._http.get(
            "/me/messages",
            params={
                "$search": f'"{query}"',
                "$top": max_results,
            },
            headers=self._auth_headers(ConsistencyLevel="eventual"),
        )
        resp.raise_for_status()
        data = resp.json()
        return [self._parse_summary(msg) for msg in data.get("value", [])]

    async def read(self, message_id: str) -> EmailMessage:
        """Read a full email message."""
        await self._refresh_token_if_needed()
        resp = await self._http.get(
            f"/me/messages/{message_id}",
            params={"$expand": "attachments"},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return self._parse_message(resp.json())

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def send(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> dict[str, str]:
        """Send an email via Graph API."""
        await self._refresh_token_if_needed()
        message = self._build_message(to=to, subject=subject, body=body, cc=cc)
        resp = await self._http.post(
            "/me/sendMail",
            json={"message": message, "saveToSentItems": True},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        logger.info(
            "outlook_message_sent",
            account=self._account_name,
            to=to,
            subject=subject,
        )
        # Graph sendMail returns 202 with no body — no message_id available
        return {"message_id": "", "status": "sent"}

    async def draft(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> dict[str, str]:
        """Create a draft email via Graph API."""
        await self._refresh_token_if_needed()
        message = self._build_message(to=to, subject=subject, body=body, cc=cc)
        resp = await self._http.post(
            "/me/messages", json=message, headers=self._auth_headers()
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(
            "outlook_draft_created",
            account=self._account_name,
            to=to,
            subject=subject,
        )
        return {"draft_id": data.get("id", ""), "status": "drafted"}

    async def reply(self, message_id: str, body: str) -> dict[str, str]:
        """Reply to an email via Graph API."""
        await self._refresh_token_if_needed()
        resp = await self._http.post(
            f"/me/messages/{message_id}/reply",
            json={"comment": body},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        logger.info(
            "outlook_reply_sent",
            account=self._account_name,
            message_id=message_id,
        )
        return {"status": "sent"}

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _refresh_token_if_needed(self) -> None:
        """Re-acquire token via MSAL if expired. Update httpx headers."""

        def _refresh() -> str | None:
            if self._msal_app is None:
                return None
            accounts = self._msal_app.get_accounts()
            if not accounts:
                return None
            result = self._msal_app.acquire_token_silent(
                scopes=GRAPH_SCOPES,
                account=accounts[0],
            )
            if result and "access_token" in result:
                if self._cache and self._cache.has_state_changed:
                    self._persist_cache()
                return result["access_token"]
            return None

        new_token = await asyncio.to_thread(_refresh)
        if new_token:
            self._access_token = new_token

    def _auth_headers(self, **extra: str) -> dict[str, str]:
        """Build per-request auth headers. httpx client headers are immutable."""
        headers = {"Authorization": f"Bearer {self._access_token}"}
        headers.update(extra)
        return headers

    def _persist_cache(self) -> None:
        """Atomically write MSAL cache back to credential file.

        Rebuilds from instance vars — does not re-read the file,
        avoiding race conditions under concurrent requests.
        """
        cred_path = Path(self._credential_file)
        cred_data = {
            "client_id": self._client_id,
            "tenant_id": self._tenant_id,
            "email_address": self._email,
            "token_cache": self._cache.serialize(),
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=cred_path.parent,
            suffix=".tmp",
            delete=False,
        ) as tmp:
            json.dump(cred_data, tmp, indent=2)
            tmp_path = Path(tmp.name)
        tmp_path.rename(cred_path)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_summary(msg: dict[str, Any]) -> EmailSummary:
        return EmailSummary(
            id=msg["id"],
            subject=msg.get("subject", ""),
            sender=msg.get("from", {}).get("emailAddress", {}).get("address", ""),
            date=_parse_graph_datetime(msg.get("receivedDateTime")),
            snippet=msg.get("bodyPreview", ""),
            is_read=msg.get("isRead", True),
        )

    @staticmethod
    def _parse_message(msg: dict[str, Any]) -> EmailMessage:
        body_obj = msg.get("body", {})
        body_text = body_obj.get("content", "")
        if body_obj.get("contentType", "").lower() == "html":
            body_text = _strip_html(body_text)

        return EmailMessage(
            id=msg["id"],
            thread_id=msg.get("conversationId", ""),
            subject=msg.get("subject", ""),
            sender=msg.get("from", {}).get("emailAddress", {}).get("address", ""),
            to=[
                r.get("emailAddress", {}).get("address", "")
                for r in msg.get("toRecipients", [])
            ],
            cc=[
                r.get("emailAddress", {}).get("address", "")
                for r in msg.get("ccRecipients", [])
            ],
            date=_parse_graph_datetime(msg.get("receivedDateTime")),
            body=body_text,
            snippet=msg.get("bodyPreview", ""),
            is_read=msg.get("isRead", True),
            attachments=_parse_attachments(msg),
        )

    @staticmethod
    def _build_message(
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
    ) -> dict[str, Any]:
        """Build a Graph API message object."""
        message: dict[str, Any] = {
            "subject": subject,
            "body": {"contentType": "text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
        if cc:
            message["ccRecipients"] = [
                {"emailAddress": {"address": addr.strip()}}
                for addr in cc.split(",")
            ]
        return message


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _parse_graph_datetime(dt_str: str | None) -> datetime | None:
    """Parse Graph API ISO datetime string."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class _HTMLStripper(HTMLParser):
    """Minimal HTML tag stripper."""

    def __init__(self) -> None:
        super().__init__()
        self._result = StringIO()

    def handle_data(self, data: str) -> None:
        self._result.write(data)

    def get_text(self) -> str:
        return self._result.getvalue()


def _strip_html(html: str) -> str:
    """Strip HTML tags, returning plain text."""
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


def _parse_attachments(msg: dict[str, Any]) -> list[AttachmentInfo]:
    """Parse attachment metadata from Graph API message."""
    if not msg.get("hasAttachments"):
        return []
    attachments: list[AttachmentInfo] = []
    for att in msg.get("attachments", []):
        if att.get("name"):
            attachments.append(
                AttachmentInfo(
                    filename=att["name"],
                    mime_type=att.get("contentType", "application/octet-stream"),
                    size=att.get("size", 0),
                )
            )
    return attachments
