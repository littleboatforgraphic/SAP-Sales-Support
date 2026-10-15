"""
Admin API for viewing email order drafts and history.

This router provides endpoints for internal staff to:
1. View email order drafts created in AutoCount
2. View draft history and processing results
3. Monitor email order processing status

Admins work directly in AutoCount to review and submit drafts.
This API is for viewing and monitoring only.

This is for INTERNAL STAFF ONLY (authenticated via allowlist).
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db_session_factory, AuditLogEntry, StaffAllowlistEntry, ActorType, new_uuid
from config import settings
from role_helpers import has_role, Role
from email_autonomy import measure_shadow_accuracy

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------
# Dependency to verify staff access
# --------------------------------------------------------------------------

def get_db():
    """Dependency to get a database session."""
    factory = get_db_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def verify_staff_access(user_id: str, db: Session) -> bool:
    """
    Verify that the user is in the staff allowlist and has Admin role.

    Args:
        user_id: Telegram user ID
        db: Database session

    Returns:
        True if user has Admin role
    """
    staff = db.query(StaffAllowlistEntry).filter(
        StaffAllowlistEntry.telegram_user_id == user_id,
        StaffAllowlistEntry.active == True
    ).first()

    if not staff:
        return False

    # Check if user has Admin role
    return has_role(db, staff.id, Role.ADMIN)


# --------------------------------------------------------------------------
# Response Models
# --------------------------------------------------------------------------

class AccuracyReport(BaseModel):
    """Shadow mode accuracy report."""
    draft_ref: str
    agent_doc_number: Optional[str]
    admin_action: str
    admin_doc_number: Optional[str]
    doc_numbers_match: Optional[bool]
    accuracy_score: Optional[float]


class DraftSummary(BaseModel):
    """Summary of an email order draft."""
    draft_ref: str
    sender: str
    subject: str
    scenario: str
    po_number: Optional[str]
    buyer_name: Optional[str]
    customer_status: str
    autocount_doc_number: Optional[str]
    autocount_doc_type: Optional[str]
    autocount_message: str
    block_flags: List[str]
    warn_flags: List[str]
    created_at: str
    autonomy_mode: str
    autonomy_decision: str
    autonomy_reason: str


class AdminActionRequest(BaseModel):
    """Request to report admin action for shadow mode accuracy measurement."""
    user_id: str = Field(..., description="Staff user ID")
    draft_ref: str = Field(..., description="Email message ID (draft reference)")
    action: str = Field(..., description="Action: 'submit', 'modify', or 'reject'")
    admin_doc_number: Optional[str] = Field(None, description="Document number admin created/modified")


class ReplyDraftSummary(BaseModel):
    """Summary of a drafted enquiry reply awaiting review/release."""
    draft_ref: str
    category: str
    recipient: str
    subject: str
    confidence: str
    risk: str
    flags: List[str]
    reply_body: str
    created_at: str
    sent: bool


class SendReplyRequest(BaseModel):
    """Request to release a drafted enquiry reply (assisted mode)."""
    user_id: str = Field(..., description="Staff user ID")
    draft_ref: str = Field(..., description="Email message ID (draft reference)")


# --------------------------------------------------------------------------
# View Endpoints
# --------------------------------------------------------------------------

@router.get("/drafts")
def list_drafts(
    user_id: str = Query(..., description="Staff user ID"),
    limit: int = Query(50, description="Maximum number of drafts to return"),
    db: Session = Depends(get_db)
) -> List[DraftSummary]:
    """
    List all email order drafts created in AutoCount.

    Only staff in the allowlist can view drafts.
    """
    # Verify staff access
    if not verify_staff_access(user_id, db):
        raise HTTPException(status_code=403, detail="User not authorized to view drafts")

    # Get all draft_created entries
    draft_audits = db.query(AuditLogEntry).filter(
        AuditLogEntry.entity_type == "email_po",
        AuditLogEntry.action == "draft_created"
    ).order_by(AuditLogEntry.timestamp.desc()).limit(limit).all()

    drafts = []
    for draft in draft_audits:
        # Extract draft data
        details = draft.details
        processing_result = details.get("processing_result", {})
        draft_data = processing_result.get("draft", {})
        autocount_draft = draft_data.get("autocount_draft", {})

        drafts.append(DraftSummary(
            draft_ref=draft.entity_reference,
            sender=details.get("sender", "unknown"),
            subject=details.get("subject", "No subject"),
            scenario=draft_data.get("scenario", "unknown"),
            po_number=draft_data.get("order", {}).get("po_number"),
            buyer_name=draft_data.get("order", {}).get("buyer_name"),
            customer_status=draft_data.get("customer", {}).get("status", "unknown"),
            autocount_doc_number=autocount_draft.get("document_number"),
            autocount_doc_type=autocount_draft.get("document_type"),
            autocount_message=autocount_draft.get("message", "No message"),
            block_flags=draft_data.get("flags", {}).get("block", []),
            warn_flags=draft_data.get("flags", {}).get("warn", []),
            created_at=draft.timestamp.isoformat(),
            autonomy_mode=processing_result.get("autonomy_mode", "unknown"),
            autonomy_decision=processing_result.get("autonomy_decision", "unknown"),
            autonomy_reason=processing_result.get("autonomy_reason", "unknown")
        ))

    return drafts


@router.get("/draft-details")
def get_draft_details(
    draft_ref: str = Query(..., description="Email message ID (draft reference)"),
    user_id: str = Query(..., description="Staff user ID"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get full details of a specific draft.

    Only staff in the allowlist can view draft details.
    """
    # Verify staff access
    if not verify_staff_access(user_id, db):
        raise HTTPException(status_code=403, detail="User not authorized to view draft details")

    # Get the draft from audit log
    draft_audit = db.query(AuditLogEntry).filter(
        AuditLogEntry.entity_type == "email_po",
        AuditLogEntry.entity_reference == draft_ref,
        AuditLogEntry.action == "draft_created"
    ).first()

    if not draft_audit:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Return full draft data
    return {
        "draft_ref": draft_audit.entity_reference,
        "timestamp": draft_audit.timestamp.isoformat(),
        "details": draft_audit.details
    }


@router.get("/stats")
def get_processing_stats(
    user_id: str = Query(..., description="Staff user ID"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get processing statistics for email orders.

    Only staff in the allowlist can view stats.
    """
    # Verify staff access
    if not verify_staff_access(user_id, db):
        raise HTTPException(status_code=403, detail="User not authorized to view stats")

    # Get all email PO entries
    all_entries = db.query(AuditLogEntry).filter(
        AuditLogEntry.entity_type == "email_po"
    ).all()

    # Count by action
    stats = {}
    for entry in all_entries:
        action = entry.action
        stats[action] = stats.get(action, 0) + 1

    # Get recent drafts
    recent_drafts = db.query(AuditLogEntry).filter(
        AuditLogEntry.entity_type == "email_po",
        AuditLogEntry.action == "draft_created"
    ).order_by(AuditLogEntry.timestamp.desc()).limit(10).all()

    return {
        "total_entries": len(all_entries),
        "by_action": stats,
        "recent_drafts": [
            {
                "ref": e.entity_reference,
                "timestamp": e.timestamp.isoformat(),
                "details": e.details
            }
            for e in recent_drafts
        ]
    }


@router.post("/report-admin-action")
def report_admin_action(
    request: AdminActionRequest,
    db: Session = Depends(get_db)
) -> AccuracyReport:
    """
    Report admin action for shadow mode accuracy measurement.

    Used in shadow mode to compare agent draft with admin's actual action.
    """
    # Verify staff access
    if not verify_staff_access(request.user_id, db):
        raise HTTPException(status_code=403, detail="User not authorized")

    # Measure accuracy
    metrics = measure_shadow_accuracy(
        db,
        request.draft_ref,
        request.action,
        request.admin_doc_number
    )

    return AccuracyReport(
        draft_ref=request.draft_ref,
        agent_doc_number=metrics.get("agent_doc_number"),
        admin_action=request.action,
        admin_doc_number=request.admin_doc_number,
        doc_numbers_match=metrics.get("doc_numbers_match"),
        accuracy_score=metrics.get("accuracy_score")
    )


# --------------------------------------------------------------------------
# Enquiry reply drafts (shadow / assisted mode)
# --------------------------------------------------------------------------

def _enquiry_reply_audits(db: Session, limit: int = 50):
    """reply_drafted audit entries, annotated with whether they were sent."""
    drafted = db.query(AuditLogEntry).filter(
        AuditLogEntry.entity_type == "email_po",
        AuditLogEntry.action == "reply_drafted"
    ).order_by(AuditLogEntry.timestamp.desc()).limit(limit).all()

    sent_refs = {
        r.entity_reference for r in db.query(AuditLogEntry).filter(
            AuditLogEntry.entity_type == "email_po",
            AuditLogEntry.action == "reply_sent"
        ).all()
    }
    return drafted, sent_refs


@router.get("/reply-drafts")
def list_reply_drafts(
    user_id: str = Query(..., description="Staff user ID"),
    limit: int = Query(50),
    db: Session = Depends(get_db)
) -> List[ReplyDraftSummary]:
    """List enquiry replies the agent drafted, newest first."""
    if not verify_staff_access(user_id, db):
        raise HTTPException(status_code=403, detail="User not authorized")

    drafted, sent_refs = _enquiry_reply_audits(db, limit)
    return [
        ReplyDraftSummary(
            draft_ref=e.entity_reference,
            category=e.details.get("category", "enquiry"),
            recipient=e.details.get("recipient", "unknown"),
            subject=e.details.get("subject", ""),
            confidence=e.details.get("confidence", "low"),
            risk=e.details.get("risk", "low"),
            flags=e.details.get("flags", []),
            reply_body=e.details.get("reply_body", ""),
            created_at=e.timestamp.isoformat(),
            sent=e.entity_reference in sent_refs,
        )
        for e in drafted
    ]


@router.post("/send-drafted-reply")
def send_drafted_reply(
    request: SendReplyRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Release a drafted enquiry reply to the customer (assisted mode).

    Sends the stored fixed-template body over SMTP, threaded under the
    original email. Refuses if the reply was already sent.
    """
    if not verify_staff_access(request.user_id, db):
        raise HTTPException(status_code=403, detail="User not authorized")

    draft = db.query(AuditLogEntry).filter(
        AuditLogEntry.entity_type == "email_po",
        AuditLogEntry.entity_reference == request.draft_ref,
        AuditLogEntry.action == "reply_drafted"
    ).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Reply draft not found")

    already_sent = db.query(AuditLogEntry).filter(
        AuditLogEntry.entity_type == "email_po",
        AuditLogEntry.entity_reference == request.draft_ref,
        AuditLogEntry.action == "reply_sent"
    ).first()
    if already_sent:
        raise HTTPException(status_code=409, detail="Reply already sent")

    details = draft.details
    recipient = details.get("recipient")
    reply_body = details.get("reply_body")
    if not recipient or not reply_body:
        raise HTTPException(status_code=422, detail="Draft is missing recipient or body")

    from email_sender import send_reply
    from routers.email_webhook import InboundEmail

    original = InboundEmail(
        message_id=request.draft_ref,
        sender=recipient,
        subject=details.get("subject", ""),
        body="",
    )
    try:
        send_reply(original, reply_body)
    except Exception as e:
        logger.error(f"Failed to release drafted reply {request.draft_ref[:40]}: {e}")
        raise HTTPException(status_code=502, detail=f"SMTP send failed: {type(e).__name__}")

    db.add(AuditLogEntry(
        id=new_uuid(),
        entity_type="email_po",
        entity_reference=request.draft_ref,
        action="reply_sent",
        actor=request.user_id,
        actor_type=ActorType.STAFF,
        details={"recipient": recipient, "category": details.get("category")},
        timestamp=datetime.now(timezone.utc),
    ))
    db.commit()
    return {"status": "sent", "draft_ref": request.draft_ref, "recipient": recipient}
