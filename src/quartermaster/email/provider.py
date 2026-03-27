"""Email provider protocol — defines the contract for all email backends."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from quartermaster.email.models import EmailMessage, EmailSummary


class EmailProvider(Protocol):
    """Protocol that all email providers must implement."""

    @property
    def account_name(self) -> str: ...

    @property
    def label(self) -> str: ...

    async def connect(self) -> None: ...

    async def get_unread_summary(self, max_results: int = 20) -> list[EmailSummary]: ...

    async def search(self, query: str, max_results: int = 10) -> list[EmailSummary]: ...

    async def read(self, message_id: str) -> EmailMessage: ...

    async def send(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> dict[str, str]: ...

    async def draft(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> dict[str, str]: ...

    async def reply(self, message_id: str, body: str) -> dict[str, str]: ...

    async def health_check(self) -> bool: ...
