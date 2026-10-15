"""
Channel-agnostic core message handler.
Both the WhatsApp and Telegram webhook routers delegate here after extracting
a normalized message from their platform-specific payloads:
staff allowlist check, admin takeover detection, and trigger detection.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from database import StaffAllowlistEntry, Role, ConversationState
from trigger import TriggerDetector
from glossary import GlossaryManager

logger = logging.getLogger(__name__)


class CoreMessageHandler:
    """
    Processes normalized inbound messages regardless of origin channel.
    A normalized message has:
        - sender_id:   channel-native sender identifier (phone number, Telegram user ID)
        - channel:     "whatsapp" | "telegram"
        - conversation_id: channel-native conversation identifier
        - message:     text content
    """

    def __init__(self, db: Session):
        self.db = db
        self.glossary_manager = GlossaryManager(db)
        self.trigger_detector = TriggerDetector(self.glossary_manager, db)

    def is_staff_member(self, sender_id: str, channel: str) -> bool:
        """
        Check if sender is on the staff allowlist for the given channel.
        Returns True if the sender is allowed and active, False otherwise.
        """
        entry = self._get_staff_entry(sender_id, channel)
        return entry is not None

    def _get_staff_entry(self, sender_id: str, channel: str) -> Optional[StaffAllowlistEntry]:
        """Look up the active staff allowlist entry for a sender on a channel."""
        column = StaffAllowlistEntry.phone_number if channel == "whatsapp" else StaffAllowlistEntry.telegram_user_id
        return self.db.query(StaffAllowlistEntry).filter(
            column == sender_id,
            StaffAllowlistEntry.active == True
        ).first()

    def get_staff_role(self, sender_id: str, channel: str) -> Optional[str]:
        """Get the role of a staff member by sender ID and channel."""
        entry = self._get_staff_entry(sender_id, channel)
        if entry:
            return entry.role.value
        return None

    def is_admin(self, sender_id: str, channel: str) -> bool:
        """Check if sender is an admin."""
        return self.get_staff_role(sender_id, channel) == Role.ADMIN.value

    def check_admin_takeover(self, conversation_id: str) -> bool:
        """
        Check if admin has taken over this conversation.
        Returns True if admin takeover is active, False otherwise.
        """
        state = self.db.query(ConversationState).filter(
            ConversationState.conversation_id == conversation_id
        ).first()

        if state and state.admin_takeover_active:
            # Check if takeover window has expired.
            # SQLite may return the stored timestamp as naive (no tzinfo), so
            # normalize before comparing with the aware UTC now.
            if state.admin_takeover_ends_at:
                ends_at = state.admin_takeover_ends_at
                if ends_at.tzinfo is None:
                    ends_at = ends_at.replace(tzinfo=timezone.utc)
                if ends_at < datetime.now(timezone.utc):
                    # Window expired, clear takeover
                    state.admin_takeover_active = False
                    state.admin_takeover_ends_at = None
                    self.db.commit()
                    return False
            return True

        return False

    def handle_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a normalized inbound message.
        Returns a response indicating whether the message was processed.
        """
        sender_id = message_data.get("sender_id", "")
        channel = message_data.get("channel", "")
        conversation_id = message_data.get("conversation_id", "")
        message_content = message_data.get("message", "")

        # Staff allowlist check
        if not self.is_staff_member(sender_id, channel):
            logger.warning(f"Unauthorized message from {sender_id} on {channel}")
            return {
                "processed": False,
                "reason": "unauthorized_sender",
                "message": "Sender not on staff allowlist"
            }

        # Check admin takeover
        if self.check_admin_takeover(conversation_id):
            logger.info(f"Admin takeover active for conversation {conversation_id}")
            # Detect if admin is explicitly handing back control
            # TODO: Implement handoff detection
            return {
                "processed": False,
                "reason": "admin_takeover",
                "message": "Admin has taken over this conversation"
            }

        # Trigger detection
        trigger_type = self.trigger_detector.detect(message_content)

        if trigger_type is None:
            # No trigger, this is normal conversation
            return {
                "processed": False,
                "reason": "no_trigger",
                "message": "No trigger detected"
            }

        # Trigger detected - this would be passed to agent orchestration layer
        # For now, just acknowledge
        logger.info(f"Trigger detected: {trigger_type} from {sender_id} on {channel}")

        return {
            "processed": True,
            "trigger_type": trigger_type,
            "message": "Trigger detected, ready for agent processing"
        }
