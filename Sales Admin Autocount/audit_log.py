from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database import AuditLogEntry, ActorType, get_sessionmaker
import uuid


class AuditLogger:
    """
    Logs all system actions for auditability.
    Every price used, document sent, and edit made is logged with version history.
    """

    def __init__(self, session: Session):
        self.session = session

    def log(
        self,
        entity_type: str,
        entity_reference: str,
        action: str,
        actor: str,
        actor_type: ActorType,
        details: Optional[Dict[str, Any]] = None,
        related_conversation_id: Optional[str] = None
    ) -> AuditLogEntry:
        """
        Log an audit entry.
        """
        import json

        entry = AuditLogEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            entity_type=entity_type,
            entity_reference=entity_reference,
            action=action,
            actor=actor,
            actor_type=actor_type,
            details=json.dumps(details) if details else None,
            related_conversation_id=related_conversation_id
        )

        self.session.add(entry)
        self.session.commit()
        return entry

    def log_price_used(
        self,
        order_reference: str,
        sku: str,
        price: float,
        actor: str,
        related_conversation_id: Optional[str] = None
    ) -> AuditLogEntry:
        """Log the price used for a specific order line item."""
        return self.log(
            entity_type="order",
            entity_reference=order_reference,
            action="price_used",
            actor=actor,
            actor_type=ActorType.AGENT,
            details={
                "sku": sku,
                "price": price
            },
            related_conversation_id=related_conversation_id
        )

    def log_document_sent(
        self,
        order_reference: str,
        document_type: str,
        recipient: str,
        channel: str,
        actor: str,
        related_conversation_id: Optional[str] = None
    ) -> AuditLogEntry:
        """Log when a document is sent to a customer or salesperson."""
        return self.log(
            entity_type="order",
            entity_reference=order_reference,
            action="document_sent",
            actor=actor,
            actor_type=ActorType.AGENT,
            details={
                "document_type": document_type,
                "recipient": recipient,
                "channel": channel
            },
            related_conversation_id=related_conversation_id
        )

    def log_glossary_change(
        self,
        glossary_id: int,
        action: str,
        term: str,
        canonical_value: str,
        actor: str,
        related_conversation_id: Optional[str] = None
    ) -> AuditLogEntry:
        """Log changes to the glossary (additions, approvals, rejections)."""
        return self.log(
            entity_type="glossary",
            entity_reference=str(glossary_id),
            action=action,
            actor=actor,
            actor_type=ActorType.ADMIN,
            details={
                "term": term,
                "canonical_value": canonical_value
            },
            related_conversation_id=related_conversation_id
        )

    def log_order_created(
        self,
        order_reference: str,
        customer_id: str,
        items: list,
        total_amount: float,
        actor: str,
        related_conversation_id: Optional[str] = None
    ) -> AuditLogEntry:
        """Log when a new order is created."""
        return self.log(
            entity_type="order",
            entity_reference=order_reference,
            action="created",
            actor=actor,
            actor_type=ActorType.AGENT,
            details={
                "customer_id": customer_id,
                "items": items,
                "total_amount": total_amount
            },
            related_conversation_id=related_conversation_id
        )

    def log_order_approved(
        self,
        order_reference: str,
        approved_by: str,
        related_conversation_id: Optional[str] = None
    ) -> AuditLogEntry:
        """Log when an order is approved by admin."""
        return self.log(
            entity_type="order",
            entity_reference=order_reference,
            action="approved",
            actor=approved_by,
            actor_type=ActorType.ADMIN,
            details={},
            related_conversation_id=related_conversation_id
        )

    def log_order_version(
        self,
        order_reference: str,
        version: int,
        edit_reason: Optional[str],
        actor: str,
        related_conversation_id: Optional[str] = None
    ) -> AuditLogEntry:
        """Log when an order is edited (new version created)."""
        return self.log(
            entity_type="order",
            entity_reference=order_reference,
            action="version_created",
            actor=actor,
            actor_type=ActorType.AGENT,
            details={
                "version": version,
                "edit_reason": edit_reason
            },
            related_conversation_id=related_conversation_id
        )

    def log_payment_draft(
        self,
        payment_reference: str,
        amount: float,
        payer_ref: str,
        actor: str,
        related_conversation_id: Optional[str] = None
    ) -> AuditLogEntry:
        """Log when a payment entry is drafted."""
        return self.log(
            entity_type="payment",
            entity_reference=payment_reference,
            action="drafted",
            actor=actor,
            actor_type=ActorType.AGENT,
            details={
                "amount": amount,
                "payer_ref": payer_ref
            },
            related_conversation_id=related_conversation_id
        )

    def log_payment_confirmed(
        self,
        payment_reference: str,
        confirmed_by: str,
        related_conversation_id: Optional[str] = None
    ) -> AuditLogEntry:
        """Log when a payment is confirmed by accountant."""
        return self.log(
            entity_type="payment",
            entity_reference=payment_reference,
            action="confirmed",
            actor=confirmed_by,
            actor_type=ActorType.ACCOUNTANT,
            details={},
            related_conversation_id=related_conversation_id
        )

    def log_escalation(
        self,
        entity_type: str,
        entity_reference: str,
        reason: str,
        actor: str,
        related_conversation_id: Optional[str] = None
    ) -> AuditLogEntry:
        """Log when an action is escalated to admin."""
        return self.log(
            entity_type=entity_type,
            entity_reference=entity_reference,
            action="escalated",
            actor=actor,
            actor_type=ActorType.AGENT,
            details={
                "reason": reason
            },
            related_conversation_id=related_conversation_id
        )

    def get_audit_trail(
        self,
        entity_type: Optional[str] = None,
        entity_reference: Optional[str] = None,
        limit: int = 100
    ) -> list[AuditLogEntry]:
        """
        Get audit trail for a specific entity or all entities.
        """
        query = self.session.query(AuditLogEntry)

        if entity_type:
            query = query.filter(AuditLogEntry.entity_type == entity_type)

        if entity_reference:
            query = query.filter(AuditLogEntry.entity_reference == entity_reference)

        return query.order_by(AuditLogEntry.timestamp.desc()).limit(limit).all()

    def get_conversation_audit_trail(
        self,
        conversation_id: str,
        limit: int = 100
    ) -> list[AuditLogEntry]:
        """Get all audit entries related to a specific conversation."""
        return self.session.query(AuditLogEntry).filter(
            AuditLogEntry.related_conversation_id == conversation_id
        ).order_by(AuditLogEntry.timestamp.desc()).limit(limit).all()
