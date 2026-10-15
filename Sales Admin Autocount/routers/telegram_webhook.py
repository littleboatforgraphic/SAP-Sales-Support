import logging
import hmac
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from telegram_client import get_telegram_client
from database import get_db_session_factory
from message_handler import CoreMessageHandler
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Use shared database session factory from database.py
SessionLocal = get_db_session_factory()


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_telegram_secret_token(secret_token_header: Optional[str]):
    """
    Verify Telegram's X-Telegram-Bot-Api-Secret-Token header.
    Telegram includes this header on every webhook request when a secret token
    is configured via setWebhook. Skips verification when not configured (dev mode);
    refuses to run unsigned in production.
    """
    secret_token = settings.telegram_webhook_secret_token.get_secret_value() if settings.telegram_webhook_secret_token else ""

    if not secret_token:
        if settings.environment == "production":
            logger.error("TELEGRAM_WEBHOOK_SECRET_TOKEN not configured in production - rejecting update")
            raise HTTPException(status_code=500, detail="Telegram webhook secret not configured")
        logger.warning("Telegram webhook secret not configured - skipping verification (dev mode)")
        return

    if not secret_token_header:
        logger.warning("Missing X-Telegram-Bot-Api-Secret-Token header")
        raise HTTPException(status_code=403, detail="Missing secret token header")

    if not hmac.compare_digest(secret_token_header, secret_token):
        logger.warning("Telegram webhook secret token mismatch")
        raise HTTPException(status_code=403, detail="Invalid secret token")


def verify_user_allowlist(sender_id: str, db: Session):
    """
    Verify that the sender is in the staff allowlist.
    Rejects messages from unauthorized users.
    """
    from database import StaffAllowlistEntry

    # Check if user is in allowlist by Telegram user ID
    allowed = db.query(StaffAllowlistEntry).filter(
        StaffAllowlistEntry.telegram_user_id == sender_id,
        StaffAllowlistEntry.active == True
    ).first()

    if not allowed:
        logger.warning(f"Unauthorized Telegram user attempted access: {sender_id}")
        raise HTTPException(status_code=403, detail="User not authorized")


def extract_messages_from_telegram_update(update: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract normalized inbound messages from a Telegram webhook update.
    Handles both private chats and groups; ignores edits and non-text messages
    for now (the agent layer will handle documents when implemented).
    Returns normalized messages with sender_id / channel / conversation_id / message keys.
    """
    normalized = []

    # Only process new messages, not edits of previous ones
    message = update.get("message")
    if not message:
        # Updates without a new message (edits, callbacks, channel posts, etc.) - ignore
        return normalized

    msg_text = message.get("text")
    if not msg_text:
        logger.info(f"Skipping non-text Telegram message: {list(message.keys())}")
        return normalized

    from_field = message.get("from", {})
    chat = message.get("chat", {})

    # In group chats, require an explicit trigger prefix so casual group chatter
    # never wakes the agent; private chats use the normal trigger rules.
    normalized.append({
        "sender_id": str(from_field.get("id", "")),
        "channel": "telegram",
        "conversation_id": f"tg:{chat.get('id', '')}",
        "message": msg_text,
        "chat_type": chat.get("type", ""),
        "chat_id": str(chat.get("id", "")),
        "is_group": chat.get("type") in ("group", "supergroup")
    })

    return normalized


@router.post("/webhook/telegram")
async def telegram_webhook_receive(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
    db: Session = Depends(get_db)
):
    """
    Receive webhook updates from Telegram.
    Configure with telegram_client.set_webhook("<public-url>/api/v1/webhook/telegram", secret).
    """
    try:
        # Verify secret token first - before trusting any payload content
        verify_telegram_secret_token(x_telegram_bot_api_secret_token)

        update = await request.json()
        logger.info(f"Received Telegram update: {update}")

        handler = CoreMessageHandler(db)

        for message in extract_messages_from_telegram_update(update):
            # Verify user is in allowlist
            verify_user_allowlist(message["sender_id"], db)

            # In groups, only respond when the message explicitly invokes the agent
            if message["is_group"] and not message["message"].strip().lower().startswith(("ai", "agent")):
                continue

            result = handler.handle_message(message)
            logger.info(f"Telegram message handling result: {result}")
            
            # ---- TEMPORARY ECHO TEST (add this) ----
            if result.get("processed"):
                logger.info("ECHO: attempting to send reply")
                telegram_client = get_telegram_client()
                resp = await telegram_client.send_message(
                    chat_id=message["sender_id"],
                    text=f"Got it, agent received: {message['message']}",
                )
                logger.info(f"ECHO: send_message returned: {resp}")
            # ----------------------------------------

        # Always return 200 quickly to Telegram; processing results are logged
        return {"status": "ok"}

    except HTTPException:
        raise  # Re-raise HTTP exceptions (verification failures)
    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
