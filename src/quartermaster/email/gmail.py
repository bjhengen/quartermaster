"""Gmail provider — Gmail API client with async wrapping."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import structlog
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from quartermaster.email.models import EmailMessage, EmailSummary  # noqa: F401

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
