"""
SMTP reply sender for the email order pipeline.

Used as reply_fn by process_inbound_email: sends the fixed-template
acknowledgement to the customer. Never carries LLM output - callers must only
pass template messages.

Returns a ready reply_fn via make_smtp_reply_fn(), or None when SMTP is not
configured so callers can report "no_sender_configured" instead of failing.
"""

import logging
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Callable, Optional, TYPE_CHECKING

from config import settings

if TYPE_CHECKING:
    from routers.email_webhook import InboundEmail

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    """SMTP credentials present and usable."""
    return bool(
        settings.smtp_host
        and settings.smtp_from
        and settings.smtp_password
        and settings.smtp_password.get_secret_value()
    )


def make_smtp_reply_fn() -> Optional[Callable[["InboundEmail", str], None]]:
    """
    Build a reply_fn for process_inbound_email.

    Returns None when SMTP is not configured - the caller then reports
    "no_sender_configured" rather than raising.
    """
    if not smtp_configured():
        return None

    def _send(email: "InboundEmail", message: str) -> None:
        send_reply(email, message)

    return _send


def send_reply(email: "InboundEmail", message: str) -> None:
    """
    Send a reply to an inbound email via SMTP.

    Replies go to Reply-To when present, else the sender. In-Reply-To /
    References keep the message threaded under the customer's original mail.
    """
    recipient = parseaddr(email.reply_to or "")[1] or parseaddr(email.sender)[1]
    if not recipient:
        raise ValueError(f"No usable recipient on inbound email {email.message_id}")

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = recipient
    msg["Subject"] = f"Re: {email.subject}" if email.subject else "Re: your enquiry"
    if email.message_id:
        msg["In-Reply-To"] = email.message_id
        msg["References"] = email.message_id
    msg.set_content(message)

    password = settings.smtp_password.get_secret_value()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, password)
        server.send_message(msg)

    logger.info(f"Sent email reply to {recipient} re: {email.message_id[:60]}")
