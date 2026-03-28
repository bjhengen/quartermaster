"""Gmail provider — Gmail API client with async wrapping."""

from __future__ import annotations

import asyncio
import base64
import tempfile
from datetime import UTC, datetime
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, cast

import structlog
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from quartermaster.email.models import AttachmentInfo, EmailMessage, EmailSummary

logger = structlog.get_logger()

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.modify"


class GmailProvider:
    """Gmail API provider with async wrapping.

    All Google API calls are synchronous. This provider wraps them in
    asyncio.to_thread() to avoid blocking the event loop.
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
        self._service: Any = None
        self._creds: Credentials | None = None

    @property
    def account_name(self) -> str:
        return self._account_name

    @property
    def label(self) -> str:
        return self._label

    @property
    def provider_type(self) -> str:
        return "gmail"

    async def close(self) -> None:
        """No persistent connections to close for Gmail API."""

    async def connect(self) -> None:
        """Load credentials, refresh if needed, build Gmail service."""
        needs_persist = False

        def _connect() -> None:
            nonlocal needs_persist
            self._creds = Credentials.from_authorized_user_file(
                self._credential_file,
            )
            if not self._creds.valid:
                if self._creds.expired and self._creds.refresh_token:
                    self._creds.refresh(GoogleRequest())
                    needs_persist = True
                else:
                    raise RuntimeError(
                        f"Gmail credentials invalid for {self._account_name} "
                        f"and cannot be refreshed"
                    )
            self._service = build("gmail", "v1", credentials=self._creds)

        await asyncio.to_thread(_connect)
        if needs_persist:
            self._persist_credentials()
        logger.info(
            "gmail_provider_connected",
            account=self._account_name,
        )

    async def health_check(self) -> bool:
        """Check if the Gmail service is functional."""
        if self._service is None:
            return False
        try:

            def _check() -> dict[str, Any]:
                return (
                    self._service.users()
                    .getProfile(userId="me")
                    .execute()
                )

            await asyncio.to_thread(_check)
            return True
        except Exception as exc:
            logger.warning(
                "gmail_health_check_failed",
                account=self._account_name,
                error=str(exc),
            )
            return False

    # -----------------------------------------------------------------------
    # Read operations
    # -----------------------------------------------------------------------

    async def get_unread_summary(self, max_results: int = 20) -> list[EmailSummary]:
        """Return summaries for unread messages."""
        return await self.search("is:unread", max_results=max_results)

    async def search(self, query: str, max_results: int = 10) -> list[EmailSummary]:
        """Search Gmail messages and return summaries."""
        service = self._service

        def _list() -> list[dict[str, Any]]:
            resp = cast(
                "dict[str, Any]",
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute(),
            )
            return cast("list[dict[str, Any]]", resp.get("messages", []))

        stubs = await asyncio.to_thread(_list)
        if not stubs:
            return []

        def _fetch_all() -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            for stub in stubs:
                raw = cast(
                    "dict[str, Any]",
                    service.users()
                    .messages()
                    .get(userId="me", id=stub["id"], format="full")
                    .execute(),
                )
                results.append(raw)
            return results

        raws = await asyncio.to_thread(_fetch_all)
        return [self._parse_summary(raw) for raw in raws]

    async def read(self, message_id: str) -> EmailMessage:
        """Fetch a full message by ID."""
        service = self._service

        def _get() -> dict[str, Any]:
            return cast(
                "dict[str, Any]",
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute(),
            )

        raw = await asyncio.to_thread(_get)
        return self._parse_message(raw)

    # -----------------------------------------------------------------------
    # Parsing helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _extract_headers(raw: dict[str, Any]) -> dict[str, str]:
        """Return a lowercase-keyed dict of header name → value."""
        headers: dict[str, str] = {}
        for h in raw.get("payload", {}).get("headers", []):
            headers[h["name"].lower()] = h["value"]
        return headers

    @staticmethod
    def _parse_date(date_str: str) -> datetime | None:
        """Parse an RFC 2822 date string to an aware datetime, or None."""
        if not date_str:
            return None
        try:
            dt = parsedate_to_datetime(date_str)
            # Ensure UTC-aware
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except Exception:
            return None

    @staticmethod
    def _parse_address_list(addr_str: str) -> list[str]:
        """Split a comma-separated address string into a list of stripped addresses."""
        if not addr_str:
            return []
        return [a.strip() for a in addr_str.split(",") if a.strip()]

    @staticmethod
    def _extract_text_body(payload: dict[str, Any]) -> str:
        """Recursively extract the first text/plain body part."""
        mime_type = payload.get("mimeType", "")
        if mime_type == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode(
                    "utf-8", errors="replace"
                )
        for part in payload.get("parts", []):
            result = GmailProvider._extract_text_body(part)
            if result:
                return result
        return ""

    @staticmethod
    def _extract_attachments(payload: dict[str, Any]) -> list[AttachmentInfo]:
        """Recursively collect attachment metadata from payload parts."""
        attachments: list[AttachmentInfo] = []
        for part in payload.get("parts", []):
            filename = part.get("filename", "")
            if filename:
                attachments.append(
                    AttachmentInfo(
                        filename=filename,
                        mime_type=part.get("mimeType", "application/octet-stream"),
                        size=part.get("body", {}).get("size", 0),
                    )
                )
            else:
                attachments.extend(GmailProvider._extract_attachments(part))
        return attachments

    def _parse_summary(self, raw: dict[str, Any]) -> EmailSummary:
        """Convert a raw Gmail message dict to an EmailSummary."""
        headers = self._extract_headers(raw)
        label_ids: list[str] = raw.get("labelIds", [])
        return EmailSummary(
            id=raw["id"],
            subject=headers.get("subject", "(no subject)"),
            sender=headers.get("from", ""),
            date=self._parse_date(headers.get("date", "")),
            snippet=raw.get("snippet", ""),
            is_read="UNREAD" not in label_ids,
            labels=label_ids,
        )

    def _parse_message(self, raw: dict[str, Any]) -> EmailMessage:
        """Convert a raw Gmail full message dict to an EmailMessage."""
        headers = self._extract_headers(raw)
        label_ids: list[str] = raw.get("labelIds", [])
        payload = raw.get("payload", {})
        return EmailMessage(
            id=raw["id"],
            thread_id=raw.get("threadId", ""),
            subject=headers.get("subject", "(no subject)"),
            sender=headers.get("from", ""),
            to=self._parse_address_list(headers.get("to", "")),
            cc=self._parse_address_list(headers.get("cc", "")),
            date=self._parse_date(headers.get("date", "")),
            body=self._extract_text_body(payload),
            snippet=raw.get("snippet", ""),
            is_read="UNREAD" not in label_ids,
            labels=label_ids,
            attachments=self._extract_attachments(payload),
        )

    # -----------------------------------------------------------------------
    # Write operations
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_mime_message(
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> str:
        """Build a base64url-encoded MIME message."""
        msg = MIMEText(body, "plain")
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        raw_bytes = msg.as_bytes()
        return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
    ) -> dict[str, str]:
        """Send an email. Returns {"message_id": ..., "status": "sent"}."""
        raw = self._build_mime_message(to=to, subject=subject, body=body, cc=cc)
        service = self._service

        def _send() -> dict[str, Any]:
            return cast(
                "dict[str, Any]",
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute(),
            )

        result = await asyncio.to_thread(_send)
        return {"message_id": result["id"], "status": "sent"}

    async def draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
    ) -> dict[str, str]:
        """Save a draft. Returns {"draft_id": ..., "status": "drafted"}."""
        raw = self._build_mime_message(to=to, subject=subject, body=body, cc=cc)
        service = self._service

        def _create() -> dict[str, Any]:
            return cast(
                "dict[str, Any]",
                service.users()
                .drafts()
                .create(userId="me", body={"message": {"raw": raw}})
                .execute(),
            )

        result = await asyncio.to_thread(_create)
        return {"draft_id": result["id"], "status": "drafted"}

    async def reply(self, message_id: str, body: str) -> dict[str, str]:
        """Reply to a message in the same thread."""
        service = self._service

        # Single fetch — get both structured EmailMessage and raw headers
        def _get_raw() -> dict[str, Any]:
            return cast(
                "dict[str, Any]",
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute(),
            )

        raw_original = await asyncio.to_thread(_get_raw)
        original = self._parse_message(raw_original)
        headers = self._extract_headers(raw_original)

        original_message_id = headers.get("message-id", "")
        references = headers.get("references", "")
        if original_message_id:
            references = (references + " " + original_message_id).strip()

        mime_raw = self._build_mime_message(
            to=original.sender,
            subject="Re: " + original.subject,
            body=body,
            in_reply_to=original_message_id or None,
            references=references or None,
        )
        thread_id = original.thread_id

        def _send_reply() -> dict[str, Any]:
            return cast(
                "dict[str, Any]",
                service.users()
                .messages()
                .send(
                    userId="me",
                    body={"raw": mime_raw, "threadId": thread_id},
                )
                .execute(),
            )

        result = await asyncio.to_thread(_send_reply)
        return {"message_id": result["id"], "status": "sent"}

    def _persist_credentials(self) -> None:
        """Atomically write refreshed credentials back to file.

        google.oauth2.credentials.Credentials.to_json() already returns a
        well-formed JSON string; write it directly to avoid double-parsing.
        """
        assert self._creds is not None
        cred_path = Path(self._credential_file)
        serialized = self._creds.to_json()
        if not isinstance(serialized, str):
            logger.warning(
                "gmail_credential_persist_skipped",
                account=self._account_name,
                reason="to_json() did not return a string",
            )
            return
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=cred_path.parent,
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp.write(serialized)
            tmp_path = Path(tmp.name)
        tmp_path.rename(cred_path)
