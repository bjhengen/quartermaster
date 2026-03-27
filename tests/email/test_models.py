"""Tests for email data models."""

from datetime import UTC, datetime

from quartermaster.email.models import AttachmentInfo, EmailMessage, EmailSummary


def test_email_summary_minimal() -> None:
    summary = EmailSummary(
        id="msg123",
        subject="Test Subject",
        sender="alice@example.com",
        date=None,
        snippet="Hello world...",
        is_read=False,
    )
    assert summary.id == "msg123"
    assert summary.labels == []
    assert summary.is_read is False


def test_email_summary_with_date() -> None:
    dt = datetime(2026, 3, 26, 10, 0, tzinfo=UTC)
    summary = EmailSummary(
        id="msg456",
        subject="Meeting Tomorrow",
        sender="bob@example.com",
        date=dt,
        snippet="Don't forget...",
        is_read=True,
        labels=["INBOX", "IMPORTANT"],
    )
    assert summary.date == dt
    assert len(summary.labels) == 2


def test_attachment_info() -> None:
    attachment = AttachmentInfo(
        filename="report.pdf",
        mime_type="application/pdf",
        size=1024,
    )
    assert attachment.filename == "report.pdf"
    assert attachment.size == 1024


def test_email_message_full() -> None:
    msg = EmailMessage(
        id="msg789",
        thread_id="thread001",
        subject="Important Update",
        sender="ceo@company.com",
        to=["brian@example.com"],
        cc=["team@example.com"],
        date=datetime(2026, 3, 26, 12, 0, tzinfo=UTC),
        body="Full email body text here.",
        snippet="Full email body...",
        is_read=False,
        labels=["INBOX"],
        attachments=[
            AttachmentInfo(filename="doc.pdf", mime_type="application/pdf", size=2048),
        ],
    )
    assert msg.thread_id == "thread001"
    assert len(msg.to) == 1
    assert len(msg.attachments) == 1
    assert msg.attachments[0].filename == "doc.pdf"


def test_email_message_minimal() -> None:
    msg = EmailMessage(
        id="m1",
        thread_id="t1",
        subject="Hi",
        sender="a@b.com",
        to=["c@d.com"],
        date=None,
        body="",
        snippet="",
        is_read=True,
    )
    assert msg.cc == []
    assert msg.attachments == []


def test_email_summary_serialization() -> None:
    summary = EmailSummary(
        id="msg1",
        subject="Test",
        sender="a@b.com",
        date=None,
        snippet="...",
        is_read=False,
    )
    data = summary.model_dump()
    assert data["id"] == "msg1"
    assert data["is_read"] is False
    restored = EmailSummary.model_validate(data)
    assert restored == summary
