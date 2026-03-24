"""Three-tier approval manager."""

import json
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

from quartermaster.transport.types import OutboundMessage, TransportType

logger = structlog.get_logger()


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ApprovalRequest:
    """A request for user approval."""

    plugin_name: str
    tool_name: str
    draft_content: str
    action_payload: dict[str, Any]
    chat_id: str
    transport: TransportType = TransportType.TELEGRAM


class ApprovalManager:
    """Manages the draft -> approve -> execute flow."""

    def __init__(
        self,
        db: Any,
        transport: Any,
        events: Any,
        timeout_minutes: int = 60,
    ) -> None:
        self._db = db
        self._transport = transport
        self._events = events
        self._timeout_minutes = timeout_minutes
        self._pending_callbacks: dict[str, ApprovalRequest] = {}
        events.subscribe("approval.callback", self._handle_callback)

    async def request_approval(self, req: ApprovalRequest) -> str:
        """Send a draft for approval and store in Oracle."""
        approval_id = str(uuid.uuid4())[:8]

        await self._db.execute(
            """INSERT INTO qm.approvals
               (plugin_name, tool_name, draft_content, action_payload,
                status, transport, external_msg_id)
               VALUES (:plugin, :tool, :draft, :payload,
                       'pending', :transport, :msg_id)""",
            {
                "plugin": req.plugin_name,
                "tool": req.tool_name,
                "draft": req.draft_content,
                "payload": json.dumps(req.action_payload),
                "transport": req.transport.value,
                "msg_id": approval_id,
            },
        )

        await self._transport.send(OutboundMessage(
            transport=req.transport,
            chat_id=req.chat_id,
            text=f"**Approval needed:**\n\n{req.draft_content}",
            inline_keyboard=[
                [
                    {"text": "Approve", "callback_data": f"approve:{approval_id}"},
                    {"text": "Reject", "callback_data": f"reject:{approval_id}"},
                ],
            ],
        ))

        self._pending_callbacks[approval_id] = req
        logger.info("approval_requested", approval_id=approval_id, tool=req.tool_name)
        return approval_id

    async def resolve(
        self, approval_id: str, status: ApprovalStatus, resolved_by: str
    ) -> bool:
        """Resolve a pending approval."""
        await self._db.execute(
            """UPDATE qm.approvals
               SET status = :status,
                   resolved_at = systimestamp,
                   resolved_by = :by
               WHERE external_msg_id = :id AND status = 'pending'""",
            {"status": status.value, "by": resolved_by, "id": approval_id},
        )

        await self._events.emit("approval.resolved", {
            "approval_id": approval_id,
            "status": status.value,
            "resolved_by": resolved_by,
        })

        logger.info("approval_resolved", approval_id=approval_id, status=status.value)
        return True

    async def _handle_callback(self, data: dict[str, Any]) -> None:
        """Handle an inline keyboard callback from Telegram."""
        callback_data = data.get("callback_data", "")
        if ":" not in callback_data:
            return

        action, approval_id = callback_data.split(":", 1)

        if approval_id not in self._pending_callbacks:
            chat_id = data.get("chat_id", "")
            if chat_id:
                await self._transport.send(OutboundMessage(
                    transport=TransportType.TELEGRAM,
                    chat_id=chat_id,
                    text="This action has expired.",
                ))
            return

        if action == "approve":
            await self.resolve(approval_id, ApprovalStatus.APPROVED, "brian")
        elif action == "reject":
            await self.resolve(approval_id, ApprovalStatus.REJECTED, "brian")

        self._pending_callbacks.pop(approval_id, None)
