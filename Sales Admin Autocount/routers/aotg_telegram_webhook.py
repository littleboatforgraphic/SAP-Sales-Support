"""
Telegram webhook router for AOTG catalog query agent.

This is a simplified webhook for testing the AOTG catalog query functionality.
It uses the new AOTG knowledge models and query agent.
"""

import logging
import hmac
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, HTTPException, Depends, Header
from sqlalchemy.orm import Session

from database import get_db_session_factory
from aotg_query_agent import AOTGQueryAgent
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
    """
    from database import StaffAllowlistEntry

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
    """
    normalized = []

    message = update.get("message")
    if not message:
        return normalized

    msg_text = message.get("text")
    if not msg_text:
        logger.info(f"Skipping non-text Telegram message")
        return normalized

    from_field = message.get("from", {})
    chat = message.get("chat", {})

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


@router.post("/webhook/aotg-telegram")
async def aotg_telegram_webhook_receive(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
    db: Session = Depends(get_db)
):
    """
    Receive webhook updates from Telegram for AOTG catalog queries.
    """
    try:
        # Verify secret token
        verify_telegram_secret_token(x_telegram_bot_api_secret_token)

        update = await request.json()
        logger.info(f"Received Telegram update")

        agent = AOTGQueryAgent(db)

        for message in extract_messages_from_telegram_update(update):
            # Verify user is in allowlist
            verify_user_allowlist(message["sender_id"], db)

            # In groups, only respond when the message explicitly invokes the agent
            if message["is_group"] and not message["message"].strip().lower().startswith(("ai", "agent", "/")):
                continue

            # Handle the message with the AOTG query agent
            response = agent.handle_message(message["message"], message["sender_id"])
            logger.info(f"Agent response: {response[:100]}...")

            # Send response back via Telegram (if token is configured)
            from telegram_client import get_telegram_client

            telegram_client = get_telegram_client()
            if telegram_client.is_configured:
                try:
                    await telegram_client.send_message(message["chat_id"], response)
                    logger.info("Response sent to Telegram")
                except Exception as e:
                    logger.error(f"Failed to send Telegram response: {e}")
            else:
                logger.warning("Telegram client not configured - response not sent")

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
