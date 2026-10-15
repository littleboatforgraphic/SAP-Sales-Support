"""
Gmail Email Poller for Email Order Agent.

This module polls Gmail for incoming emails and processes them through
the email order agent. Supports both Gmail API (OAuth 2.0) and IMAP approaches.

Configuration options:
- Gmail API: Requires OAuth 2.0 credentials (client_id, client_secret, refresh_token)
- IMAP: Simpler setup with app password

Gmail API (Recommended for production):
- GMAIL_CLIENT_ID: Google Cloud OAuth 2.0 client ID
- GMAIL_CLIENT_SECRET: Google Cloud OAuth 2.0 client secret
- GMAIL_REFRESH_TOKEN: OAuth 2.0 refresh token (long-lived)

IMAP (Alternative):
- GMAIL_IMAP_USERNAME: Gmail address
- GMAIL_IMAP_PASSWORD: App password (not regular password!)
- GMAIL_IMAP_PORT: IMAP port (default: 993)
"""

import base64
import imaplib
import logging
import ssl
import time
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from email import message_from_bytes
from email.header import decode_header

import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from config import settings
from email_order_agent import EmailOrderAgent
from database import get_db_session_factory
from routers.email_webhook import parse_auth_verdict

logger = logging.getLogger(__name__)


def _new_db_session():
    """Open a DB session, initializing the database first if needed."""
    try:
        SessionLocal = get_db_session_factory()
    except RuntimeError:
        from database import init_database
        init_database(settings.database_url)
        SessionLocal = get_db_session_factory()
    return SessionLocal()


class GmailEmailPoller:
    """Poller for Gmail emails using Gmail API or IMAP."""

    def __init__(self):
        # Gmail API credentials (OAuth 2.0)
        self.gmail_client_id = getattr(settings, "gmail_client_id", "")
        self.gmail_client_secret = getattr(settings, "gmail_client_secret", None)
        self.gmail_refresh_token = getattr(settings, "gmail_refresh_token", "")

        # IMAP credentials (alternative approach)
        self.imap_username = getattr(settings, "gmail_imap_username", "")
        self.imap_password = getattr(settings, "gmail_imap_password", None)
        self.imap_port = getattr(settings, "gmail_imap_port", 993)

        self.poll_interval = getattr(settings, "gmail_poll_interval", 300)

        # Determine which method to use
        self.use_gmail_api = bool(self.gmail_client_id and self.gmail_refresh_token)
        self.use_imap = bool(self.imap_username and self.imap_password)

        if not (self.use_gmail_api or self.use_imap):
            logger.warning("Neither Gmail API nor IMAP credentials configured")

        # Gmail API service (if using API)
        self.gmail_service = None
        if self.use_gmail_api:
            self._init_gmail_service()

    def _init_gmail_service(self):
        """Initialize Gmail API service."""
        try:
            # Create credentials from stored refresh token
            creds = Credentials(
                None,
                refresh_token=self.gmail_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.gmail_client_id,
                client_secret=self.gmail_client_secret.get_secret_value() if self.gmail_client_secret else None,
                scopes=["https://www.googleapis.com/auth/gmail.readonly"]
            )

            # Refresh token if expired
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())

            self.gmail_service = build("gmail", "v1", credentials=creds)
            logger.info("Gmail API service initialized")

        except Exception as e:
            logger.error(f"Failed to initialize Gmail API service: {e}")
            raise

    def _get_gmail_token(self) -> str:
        """Get access token for Gmail API."""
        if not self.gmail_service:
            self._init_gmail_service()

        # Refresh token if needed
        creds = self.gmail_service.credentials
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        return creds.token

    def fetch_emails_gmail_api(
        self,
        limit: int = 10,
        query: str = "is:unread"
    ) -> List[Dict[str, Any]]:
        """
        Fetch emails using Gmail API.

        Args:
            limit: Maximum number of emails to fetch
            query: Gmail search query (e.g., "is:unread", "has:attachment")

        Returns:
            List of email dictionaries
        """
        try:
            token = self._get_gmail_token()

            # List messages
            results = self.gmail_service.users().messages().list(
                userId="me",
                q=query,
                maxResults=limit
            ).execute()

            messages = results.get("messages", [])
            emails = []

            for msg in messages:
                # Get full message
                message = self.gmail_service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="full"
                ).execute()

                # Parse message headers and body
                headers = message.get("payload", {}).get("headers", [])
                header_dict = {h["name"]: h["value"] for h in headers}

                # Extract body
                body = ""
                parts = [message.get("payload")]
                while parts:
                    part = parts.pop(0)
                    if part.get("mimeType") == "text/plain":
                        body = part.get("body", {}).get("data", "")
                        if body:
                            body = base64.urlsafe_b64decode(body).decode("utf-8")
                    else:
                        parts.extend(part.get("parts", []))

                # Extract attachments
                attachments = []
                parts = [message.get("payload")]
                while parts:
                    part = parts.pop(0)
                    if part.get("filename") and part.get("body", {}).get("attachmentId"):
                        att_data = self._download_attachment_gmail_api(
                            message["id"],
                            part["body"]["attachmentId"]
                        )
                        if att_data:
                            attachments.append((part["filename"], att_data))
                    else:
                        parts.extend(part.get("parts", []))

                emails.append({
                    "id": message["id"],
                    "subject": header_dict.get("Subject", ""),
                    "from": header_dict.get("From", ""),
                    "reply_to": header_dict.get("Reply-To"),
                    "body": body,
                    "received_at": datetime.fromtimestamp(
                        int(message["internalDate"]) / 1000,
                        tz=timezone.utc
                    ).isoformat(),
                    "attachments": attachments,
                    "dmarc": parse_auth_verdict(header_dict.get("Authentication-Results"))
                })

            logger.info(f"Fetched {len(emails)} emails from Gmail API")
            return emails

        except Exception as e:
            logger.error(f"Error fetching emails from Gmail API: {e}")
            return []

    def _download_attachment_gmail_api(self, message_id: str, attachment_id: str) -> Optional[bytes]:
        """Download attachment via Gmail API."""
        try:
            att = self.gmail_service.users().messages().attachments().get(
                userId="me",
                messageId=message_id,
                id=attachment_id
            ).execute()

            data = att["data"]
            return base64.urlsafe_b64decode(data)

        except Exception as e:
            logger.error(f"Error downloading attachment {attachment_id}: {e}")
            return None

    def fetch_emails_imap(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch emails using IMAP.

        Args:
            limit: Maximum number of emails to fetch

        Returns:
            List of email dictionaries
        """
        try:
            # Connect to Gmail IMAP
            mail = imaplib.IMAP4_SSL("imap.gmail.com", self.imap_port)
            mail.login(self.imap_username, self.imap_password.get_secret_value())
            mail.select("INBOX")

            # Search for unread emails
            status, data = mail.search(None, "UNSEEN")
            if status != "OK":
                logger.warning("No unread emails found")
                return []

            email_ids = data[0].split()
            emails = []

            for email_id in email_ids[-limit:]:
                # BODY.PEEK[] fetches without marking the message as \Seen,
                # so emails stay unread for admins handling mail manually
                status, msg_data = mail.fetch(email_id, "(BODY.PEEK[])")
                if status != "OK":
                    continue

                # Parse email
                msg = message_from_bytes(msg_data[0][1])
                subject = decode_header(msg["Subject"])[0][0]
                if isinstance(subject, bytes):
                    subject = subject.decode()

                # Extract body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8")
                            break
                else:
                    body = msg.get_payload(decode=True).decode("utf-8")

                # Extract attachments
                attachments = []
                for part in msg.walk():
                    if part.get_filename():
                        filename = decode_header(part.get_filename())[0][0]
                        if isinstance(filename, bytes):
                            filename = filename.decode()
                        attachments.append((filename, part.get_payload(decode=True)))

                emails.append({
                    # Prefer the RFC822 Message-ID header: stable across sessions,
                    # unlike IMAP sequence numbers
                    "id": msg.get("Message-ID") or f"imap-uid-{email_id.decode()}",
                    "subject": subject,
                    "from": msg.get("From", ""),
                    "reply_to": msg.get("Reply-To"),
                    "body": body,
                    "received_at": msg.get("Date", ""),
                    "attachments": attachments,
                    "dmarc": parse_auth_verdict(msg.get("Authentication-Results"))
                })

            mail.logout()
            logger.info(f"Fetched {len(emails)} emails via IMAP")
            return emails

        except Exception as e:
            logger.error(f"Error fetching emails via IMAP: {e}")
            return []

    def fetch_emails(
        self,
        limit: int = 10,
        query: str = "is:unread"
    ) -> List[Dict[str, Any]]:
        """
        Fetch emails using configured method (Gmail API or IMAP).

        Args:
            limit: Maximum number of emails to fetch
            query: Gmail API search query (ignored for IMAP)

        Returns:
            List of email dictionaries
        """
        if self.use_gmail_api:
            return self.fetch_emails_gmail_api(limit, query)
        elif self.use_imap:
            return self.fetch_emails_imap(limit)
        else:
            logger.error("No Gmail credentials configured")
            return []

    def process_email_with_agent(
        self,
        email: Dict[str, Any],
        db
    ) -> Dict[str, Any]:
        """
        Process an email with the email order agent.

        Args:
            email: Email data from Gmail API or IMAP
            db: Database session

        Returns:
            Processing result
        """
        from routers.email_webhook import (
            Attachment, InboundEmail, process_inbound_email, claim_email
        )

        # Convert Gmail email to InboundEmail format.
        # InboundEmail supports a single attachment, so pick the best candidate:
        # prefer an allowed type (pdf/png/jpg/jpeg) under the size limit.
        attachment = self._pick_attachment(email.get("attachments", []))

        received_at = email.get("received_at")
        if isinstance(received_at, str):
            try:
                from email.utils import parsedate_to_datetime
                received_at = parsedate_to_datetime(received_at)
            except Exception:
                received_at = None

        inbound_email = InboundEmail(
            message_id=email.get("id"),
            sender=email.get("from", ""),
            reply_to=email.get("reply_to"),
            subject=email.get("subject", ""),
            body=email.get("body", "") or "",
            attachment=attachment,
            dmarc=email.get("dmarc"),
            received_at=received_at
        )

        # Check if already processed
        if not claim_email(db, inbound_email):
            logger.info(f"Email {email.get('id')} already processed, skipping")
            return {"status": "duplicate", "message_id": email.get("id")}

        # Process with email order agent
        return process_inbound_email(inbound_email, db)

    @staticmethod
    def _pick_attachment(attachments: List[Tuple[str, bytes]]) -> Optional["Attachment"]:
        """Pick the first usable attachment (allowed type, within size limit)."""
        from routers.email_webhook import Attachment, ALLOWED_ATTACHMENTS, MAX_ATTACHMENT_BYTES

        fallback = None
        for filename, content in attachments:
            if not content:
                continue
            name = filename.lower()
            ext = name[name.rfind("."):] if "." in name else ""
            if len(content) > MAX_ATTACHMENT_BYTES:
                logger.warning(f"Skipping oversized attachment {filename} ({len(content)} bytes)")
                continue
            if ext in ALLOWED_ATTACHMENTS:
                return Attachment(
                    filename=filename[:255],
                    content=base64.b64encode(content).decode("utf-8")
                )
            if fallback is None:
                fallback = Attachment(
                    filename=filename[:255],
                    content=base64.b64encode(content).decode("utf-8")
                )
        return fallback

    def poll_once(self, limit: int = 10, query: str = "is:unread") -> Dict[str, Any]:
        """
        Poll once and process emails.

        Args:
            limit: Maximum emails to fetch
            query: Gmail API search query

        Returns:
            Polling results
        """
        db = _new_db_session()

        try:
            emails = self.fetch_emails(limit=limit, query=query)
            processed = 0
            errors = 0

            for email in emails:
                try:
                    result = self.process_email_with_agent(email, db)
                    if result.get("status") != "duplicate":
                        processed += 1
                except Exception as e:
                    logger.error(f"Error processing email {email.get('id')}: {e}")
                    errors += 1

            return {
                "fetched": len(emails),
                "processed": processed,
                "errors": errors,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        finally:
            db.close()

    def poll_continuous(self, limit: int = 10):
        """
        Continuously poll for emails.

        Args:
            limit: Maximum emails to fetch per poll
        """
        method = "Gmail API" if self.use_gmail_api else "IMAP"
        logger.info(f"Starting continuous Gmail polling via {method} (interval: {self.poll_interval}s)")

        while True:
            try:
                result = self.poll_once(limit=limit)

                logger.info(
                    f"Poll result: fetched={result['fetched']}, "
                    f"processed={result['processed']}, errors={result['errors']}"
                )

            except Exception as e:
                logger.error(f"Error in polling loop: {e}")

            # Wait before next poll
            time.sleep(self.poll_interval)


def test_gmail_connection():
    """Test Gmail connection and list recent emails."""
    print("Testing Gmail connection...")
    print()

    poller = GmailEmailPoller()

    # Check which method is configured
    if poller.use_gmail_api:
        print("Method: Gmail API (OAuth 2.0)")
        print(f"Client ID: {poller.gmail_client_id}")
    elif poller.use_imap:
        print("Method: IMAP")
        print(f"Username: {poller.imap_username}")
    else:
        print("❌ No Gmail credentials configured")
        print("Please configure either Gmail API or IMAP credentials in .env")
        return

    print()

    # Fetch emails
    emails = poller.fetch_emails(limit=5)

    if not emails:
        print("No emails found or authentication failed")
        return

    print(f"✅ Successfully fetched {len(emails)} emails:")
    print()
    for email in emails:
        print(f"  {email.get('received_at')} | {email.get('from')} | {email.get('subject')}")
        print(f"    ID: {email.get('id')}")
        print(f"    Attachments: {len(email.get('attachments', []))}")
        print()


if __name__ == "__main__":
    test_gmail_connection()
