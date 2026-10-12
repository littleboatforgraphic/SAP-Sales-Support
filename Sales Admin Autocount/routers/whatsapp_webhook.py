import logging
import hmac
import hashlib
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, HTTPException, Depends, Header
from fastapi.responses import Response
from sqlalchemy.orm import Session

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


def verify_webhook_signature(
    x_hub_signature_256: Optional[str],
    raw_body: bytes
):
    """
    Verify Meta's X-Hub-Signature-256 header against the raw request body.
    Skips verification when WHATSAPP_APP_SECRET is not configured (dev mode);
    refuses to run unsigned in production.
    """
    app_secret = settings.whatsapp_app_secret.get_secret_value() if settings.whatsapp_app_secret else ""
    if not app_secret:
        if settings.environment == "production":
            logger.error("WHATSAPP_APP_SECRET not configured in production - rejecting message")
            raise HTTPException(status_code=500, detail="Webhook app secret not configured")
        logger.warning("WhatsApp app secret not configured - skipping signature verification (dev mode)")
        return

    if not x_hub_signature_256:
        logger.warning("Missing X-Hub-Signature-256 header")
        raise HTTPException(status_code=403, detail="Missing signature header")

    # Parse signature: "sha256=<signature>"
    signature = x_hub_signature_256.split("=")[1] if "=" in x_hub_signature_256 else x_hub_signature_256

    expected_signature = hmac.new(
        app_secret.encode(),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        logger.warning("Webhook signature mismatch")
        raise HTTPException(status_code=403, detail="Invalid signature")

    logger.info("Webhook signature verified successfully")


def extract_messages_from_meta_payload(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract normalized inbound messages from a Meta Cloud API webhook payload.
    Structure: { "entry": [ { "changes": [ { "value": { "messages": [...] } } ] } ] }
    Returns normalized messages with sender_id / channel / conversation_id / message keys.
    """
    normalized = []

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            phone_number_id = metadata.get("phone_number_id", "")

            for message in value.get("messages", []):
                # Only handle text messages for now; other types (image, document)
                # are handled by the agent layer when implemented
                msg_type = message.get("type", "")
                if msg_type == "text":
                    content = message.get("text", {}).get("body", "")
                else:
                    logger.info(f"Skipping non-text WhatsApp message type: {msg_type}")
                    continue

                normalized.append({
                    "sender_id": message.get("from", ""),
                    "channel": "whatsapp",
                    # Conversation ID scoped to this WhatsApp number
                    "conversation_id": f"wa:{phone_number_id}:{message.get('from', '')}",
                    "message": content
                })

    return normalized


# Webhook endpoints for Meta Cloud API
@router.get("/webhook")
async def webhook_verify(request: Request):
    """
    Verify webhook with Meta.
    Meta sends a GET request with hub.verify_token to verify the webhook.
    Must return the challenge value as raw response body, not JSON.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.whatsapp_webhook_verify_token:
        logger.info("Webhook verified successfully")
        # Return challenge as raw string, not JSON
        return Response(content=challenge, media_type="text/plain")
    else:
        logger.warning("Webhook verification failed")
        raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def webhook_receive(
    request: Request,
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
    db: Session = Depends(get_db)
):
    """
    Receive webhook events from Meta.
    This endpoint receives message events from WhatsApp.
    """
    try:
        # Get raw body first - signature is calculated against the raw bytes
        raw_body = await request.body()

        # Verify signature (single source of truth for this logic)
        verify_webhook_signature(x_hub_signature_256, raw_body)

        data = await request.json()
        logger.info(f"Received webhook event: {data}")

        handler = CoreMessageHandler(db)

        for message in extract_messages_from_meta_payload(data):
            result = handler.handle_message(message)
            logger.info(f"Message handling result: {result}")

        # Always return 200 quickly to Meta; processing results are logged
        return {"status": "ok"}

    except HTTPException:
        raise  # Re-raise HTTP exceptions (signature verification failures)
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
