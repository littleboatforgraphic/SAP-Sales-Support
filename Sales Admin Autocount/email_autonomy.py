"""
Email Agent Autonomy Framework

This module implements the three autonomy phases:
1. Shadow Mode - Agent drafts, admin handles manually (measure accuracy)
2. Assisted Mode - Admin approves with one click, agent executes
3. Selective Autonomy - Agent auto-submits safe orders

Autonomy Criteria for Selective Autonomy:
- Matched customer (not uncertain or no_match)
- Repeat customer (has previous orders)
- Order amount below threshold
- Not a trading house
- No block flags
- High confidence extraction
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from enum import Enum

from config import settings
from database import AuditLogEntry, ActorType, new_uuid
from email_order_extraction import Flag, Severity

logger = logging.getLogger(__name__)


class AutonomyMode(str, Enum):
    """Autonomy modes for email agent."""
    SHADOW = "shadow"
    ASSISTED = "assisted"
    SELECTIVE_AUTONOMY = "selective_autonomy"


class AutonomyCriteria:
    """Criteria for selective autonomy."""

    def __init__(self):
        self.max_amount = settings.email_auto_submit_max_amount
        self.repeat_customer_only = settings.email_auto_submit_repeat_customer
        self.trading_house_allowed = settings.email_auto_submit_trading_house_allowed

    def can_auto_submit(
        self,
        order_amount: Optional[float],
        is_repeat_customer: bool,
        is_trading_house: bool,
        block_flags: List[Flag],
        confidence: str
    ) -> tuple[bool, str]:
        """
        Determine if an order can be auto-submitted based on criteria.

        Args:
            order_amount: Total order amount
            is_repeat_customer: Whether customer has previous orders
            is_trading_house: Whether customer is a trading house
            block_flags: List of block flags
            confidence: Extraction confidence (high/medium/low)

        Returns:
            Tuple of (can_submit, reason)
        """
        reasons = []

        # Check amount threshold
        if order_amount and order_amount > self.max_amount:
            reasons.append(f"Order amount {order_amount} exceeds threshold {self.max_amount}")

        # Check repeat customer
        if self.repeat_customer_only and not is_repeat_customer:
            reasons.append("New customer (not repeat)")

        # Check trading house
        if not self.trading_house_allowed and is_trading_house:
            reasons.append("Customer is a trading house")

        # Check block flags
        if block_flags:
            reasons.append(f"Has {len(block_flags)} block flag(s)")

        # Check confidence
        if confidence != "high":
            reasons.append(f"Confidence is {confidence}, not high")

        can_submit = len(reasons) == 0
        reason = "; ".join(reasons) if reasons else "Meets all criteria"

        return can_submit, reason


def get_autonomy_mode() -> AutonomyMode:
    """Get the current autonomy mode from settings."""
    mode_str = settings.email_autonomy_mode.lower()
    try:
        return AutonomyMode(mode_str)
    except ValueError:
        logger.warning(f"Invalid autonomy mode '{mode_str}', defaulting to shadow")
        return AutonomyMode.SHADOW


def should_auto_submit(
    draft: Dict[str, Any],
    is_repeat_customer: bool
) -> tuple[bool, str]:
    """
    Determine if a draft should be auto-submitted based on autonomy mode and criteria.

    Args:
        draft: Draft summary from email_order_agent
        is_repeat_customer: Whether customer has previous orders

    Returns:
        Tuple of (should_submit, reason)
    """
    mode = get_autonomy_mode()

    # Shadow mode: never auto-submit
    if mode == AutonomyMode.SHADOW:
        return False, "Shadow mode: admin handles manually"

    # Assisted mode: never auto-submit (requires admin approval)
    if mode == AutonomyMode.ASSISTED:
        return False, "Assisted mode: requires admin approval"

    # Selective autonomy: check criteria
    if mode == AutonomyMode.SELECTIVE_AUTONOMY:
        criteria = AutonomyCriteria()

        order = draft.get("order", {})
        customer = draft.get("customer", {})
        flags = draft.get("flags", {})

        order_amount = order.get("total")
        is_trading_house = customer.get("is_trading_house", False)
        block_flags = [Flag(code=f"block_{i}", severity="block", message=msg)
                      for i, msg in enumerate(flags.get("block", []))]
        confidence = order.get("confidence", "low")

        return criteria.can_auto_submit(
            order_amount=order_amount,
            is_repeat_customer=is_repeat_customer,
            is_trading_house=is_trading_house,
            block_flags=block_flags,
            confidence=confidence
        )

    return False, "Unknown autonomy mode"


def log_autonomy_decision(
    db,
    draft_ref: str,
    decision: str,
    reason: str,
    mode: str
) -> None:
    """
    Log autonomy decision to audit trail.

    Args:
        db: Database session
        draft_ref: Email message ID
        decision: Decision made (auto_submit/require_approval/shadow)
        reason: Reason for decision
        mode: Autonomy mode in effect
    """
    db.add(AuditLogEntry(
        id=new_uuid(),
        entity_type="email_po",
        entity_reference=draft_ref[:255],
        action="autonomy_decision",
        actor="email_agent",
        actor_type=ActorType.AGENT,
        details={
            "decision": decision,
            "reason": reason,
            "mode": mode,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    ))
    db.commit()


def measure_shadow_accuracy(
    db,
    draft_ref: str,
    admin_action: str,
    admin_doc_number: Optional[str]
) -> Dict[str, Any]:
    """
    Measure accuracy in shadow mode by comparing agent draft with admin action.

    Args:
        db: Database session
        draft_ref: Email message ID
        admin_action: What admin did (submit, modify, reject)
        admin_doc_number: Document number admin created/modified

    Returns:
        Accuracy metrics
    """
    # Get the original draft
    draft_audit = db.query(AuditLogEntry).filter(
        AuditLogEntry.entity_type == "email_po",
        AuditLogEntry.entity_reference == draft_ref,
        AuditLogEntry.action == "draft_created"
    ).first()

    if not draft_audit:
        return {"error": "Draft not found"}

    draft_data = draft_audit.details
    agent_doc_no = draft_data.get("processing_result", {}).get("draft", {}).get("autocount_draft", {}).get("document_number")

    # Calculate accuracy metrics
    metrics = {
        "agent_draft_created": bool(agent_doc_no),
        "agent_doc_number": agent_doc_no,
        "admin_action": admin_action,
        "admin_doc_number": admin_doc_number,
        "doc_numbers_match": agent_doc_no == admin_doc_number if (agent_doc_no and admin_doc_number) else None,
        "accuracy_score": None
    }

    # Simple accuracy score (can be enhanced)
    if admin_action == "submit" and agent_doc_no:
        if agent_doc_no == admin_doc_number:
            metrics["accuracy_score"] = 1.0  # Perfect match
        else:
            metrics["accuracy_score"] = 0.5  # Both created but different docs
    elif admin_action == "submit" and not agent_doc_no:
        metrics["accuracy_score"] = 0.0  # Admin submitted but agent didn't draft
    elif admin_action == "reject":
        metrics["accuracy_score"] = 0.0  # Admin rejected, agent was wrong

    # Log accuracy measurement
    db.add(AuditLogEntry(
        id=new_uuid(),
        entity_type="email_po",
        entity_reference=draft_ref[:255],
        action="accuracy_measurement",
        actor="shadow_mode",
        actor_type=ActorType.AGENT,
        details=metrics
    ))
    db.commit()

    return metrics
