"""Email data models — provider-agnostic."""

from datetime import datetime

from pydantic import BaseModel


class AttachmentInfo(BaseModel):
    """Metadata about an email attachment."""

    filename: str
    mime_type: str
    size: int  # bytes


class EmailSummary(BaseModel):
    """Lightweight email summary for listings."""

    id: str
    subject: str
    sender: str
    date: datetime | None
    snippet: str
    is_read: bool
    labels: list[str] = []


class EmailMessage(BaseModel):
    """Full email message with body and attachments."""

    id: str
    thread_id: str
    subject: str
    sender: str
    to: list[str]
    cc: list[str] = []
    date: datetime | None
    body: str  # plain text
    snippet: str
    is_read: bool
    labels: list[str] = []
    attachments: list[AttachmentInfo] = []
