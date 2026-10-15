"""
Microsoft Graph (Outlook) Email Poller for Email Order Agent.

This module polls Microsoft Graph API for incoming emails and processes them
through the email order agent. It supports both one-time polling and continuous polling.

Configuration:
- MS_CLIENT_ID: Azure AD app registration client ID
- MS_TENANT_ID: Azure AD tenant ID (or use 'consumers' for personal accounts)
- MS_CLIENT_SECRET: Azure AD app client secret (for service principal)
- MS_POLL_INTERVAL: Polling interval in seconds (default: 300 = 5 minutes)
"""

import logging
import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta

import msal
import httpx

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


class OutlookEmailPoller:
    """Poller for Microsoft Graph API (Outlook emails)."""

    def __init__(self):
        self.client_id = getattr(settings, "ms_client_id", "")
        self.tenant_id = getattr(settings, "ms_tenant_id", "consumers")
        self.client_secret = getattr(settings, "ms_client_secret", None)
        self.poll_interval = getattr(settings, "ms_poll_interval", 300)
        self.scopes = ["Mail.Read"]
        self.cache_file = "token_cache.json"

        # MSAL app
        self.app = None
        self.token_cache = msal.SerializableTokenCache()

        # Load cache if exists
        try:
            with open(self.cache_file, "r") as f:
                self.token_cache.deserialize(f.read())
        except FileNotFoundError:
            pass

        self.app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=self.token_cache
        )

    def _get_access_token(self) -> str:
        """Get access token using MSAL."""
        # Try to get token from cache
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(self.scopes, account=accounts[0])
            if result:
                self._save_cache()
                return result["access_token"]

        # Get new token
        if self.client_secret:
            # Service principal flow
            result = self.app.acquire_token_for_client(scopes=self.scopes)
        else:
            # Device code flow (interactive)
            logger.error("Client secret not configured - cannot use service principal flow")
            raise ValueError("MS_CLIENT_SECRET required for automated polling")

        self._save_cache()
        return result["access_token"]

    def _save_cache(self):
        """Save token cache to file."""
        with open(self.cache_file, "w") as f:
            f.write(self.token_cache.serialize())

    def fetch_emails(
        self,
        limit: int = 10,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch emails from Outlook inbox via Microsoft Graph API.

        Args:
            limit: Maximum number of emails to fetch
            since: Only fetch emails received after this datetime

        Returns:
            List of email dictionaries
        """
        try:
            token = self._get_access_token()

            # Build filter
            filters = []
            if since:
                filter_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
                filters.append(f"receivedDateTime ge {filter_str}")

            # Build OData query
            odata_params = {
                "$top": limit,
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,from,replyTo,receivedDateTime,hasAttachments,body,internetMessageHeaders",
                "$filter": " and ".join(filters) if filters else None
            }

            response = httpx.get(
                "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Prefer": 'outlook.body-content-type="text"',
                },
                params=odata_params,
                timeout=30.0
            )
            response.raise_for_status()

            emails = response.json().get("value", [])
            logger.info(f"Fetched {len(emails)} emails from Outlook")
            return emails

        except Exception as e:
            logger.error(f"Error fetching emails from Outlook: {e}")
            return []

    def fetch_attachments(self, message_id: str) -> List[Dict[str, Any]]:
        """
        Fetch attachments for a specific email.

        Args:
            message_id: Outlook message ID

        Returns:
            List of attachment dictionaries
        """
        try:
            token = self._get_access_token()

            response = httpx.get(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments",
                headers={
                    "Authorization": f"Bearer {token}",
                },
                timeout=30.0
            )
            response.raise_for_status()

            attachments = response.json().get("value", [])
            logger.info(f"Fetched {len(attachments)} attachments for message {message_id}")
            return attachments

        except Exception as e:
            logger.error(f"Error fetching attachments for {message_id}: {e}")
            return []

    def download_attachment(self, message_id: str, attachment_id: str) -> Optional[bytes]:
        """
        Download attachment content.

        Args:
            message_id: Outlook message ID
            attachment_id: Attachment ID

        Returns:
            Attachment content as bytes
        """
        try:
            token = self._get_access_token()

            response = httpx.get(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments/{attachment_id}/$value",
                headers={
                    "Authorization": f"Bearer {token}",
                },
                timeout=60.0
            )
            response.raise_for_status()

            return response.content

        except Exception as e:
            logger.error(f"Error downloading attachment {attachment_id}: {e}")
            return None

    def process_email_with_agent(
        self,
        email: Dict[str, Any],
        db
    ) -> Dict[str, Any]:
        """
        Process an email with the email order agent.

        Args:
            email: Email data from Graph API
            db: Database session

        Returns:
            Processing result
        """
        from routers.email_webhook import (
            Attachment, InboundEmail, process_inbound_email, claim_email,
            ALLOWED_ATTACHMENTS, MAX_ATTACHMENT_BYTES
        )

        # Fetch attachments if any. InboundEmail supports a single attachment,
        # so pick the first allowed type within the size limit.
        attachment = None
        fallback = None
        if email.get("hasAttachments"):
            import base64
            graph_attachments = self.fetch_attachments(email.get("id"))
            for att in graph_attachments:
                name = (att.get("name") or "").lower()
                ext = name[name.rfind("."):] if "." in name else ""
                content = self.download_attachment(email.get("id"), att.get("id"))
                if not content or len(content) > MAX_ATTACHMENT_BYTES:
                    continue
                candidate = Attachment(
                    filename=(att.get("name") or "")[:255],
                    content=base64.b64encode(content).decode("utf-8")
                )
                if ext in ALLOWED_ATTACHMENTS:
                    attachment = candidate
                    break
                if fallback is None:
                    fallback = candidate
        attachment = attachment or fallback

        # Convert Graph API email to InboundEmail format
        received_at = email.get("receivedDateTime")
        if isinstance(received_at, str):
            try:
                received_at = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
            except Exception:
                received_at = None

        body_obj = email.get("body") or {}
        body = body_obj.get("content", "") if isinstance(body_obj, dict) else str(body_obj)

        inbound_email = InboundEmail(
            message_id=email.get("id"),
            sender=email.get("from", {}).get("emailAddress", {}).get("address", ""),
            reply_to=email.get("replyTo", {}).get("emailAddress", {}).get("address", "") or None,
            subject=email.get("subject", "") or "",
            body=body,
            attachment=attachment,
            dmarc=parse_auth_verdict(
                self._get_header(email.get("internetMessageHeaders"), "Authentication-Results")
            ),
            received_at=received_at
        )

        # Check if already processed
        if not claim_email(db, inbound_email):
            logger.info(f"Email {email.get('id')} already processed, skipping")
            return {"status": "duplicate", "message_id": email.get("id")}

        # Process with email order agent
        return process_inbound_email(inbound_email, db)

    @staticmethod
    def _get_header(headers: Any, name: str) -> Optional[str]:
        """Extract a header value from Graph's internetMessageHeaders list."""
        if isinstance(headers, list):
            return next(
                (h.get("value") for h in headers if h.get("name") == name),
                None
            )
        if isinstance(headers, dict):
            return headers.get(name)
        return None

    def poll_once(self, limit: int = 10, since: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Poll once and process emails.

        Args:
            limit: Maximum emails to fetch
            since: Only fetch emails after this datetime

        Returns:
            Polling results
        """
        db = _new_db_session()

        try:
            emails = self.fetch_emails(limit=limit, since=since)
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
        logger.info(f"Starting continuous Outlook polling (interval: {self.poll_interval}s)")
        last_check = datetime.now(timezone.utc) - timedelta(minutes=10)

        while True:
            try:
                logger.info(f"Polling Outlook (since: {last_check.isoformat()})")
                result = self.poll_once(limit=limit, since=last_check)

                logger.info(
                    f"Poll result: fetched={result['fetched']}, "
                    f"processed={result['processed']}, errors={result['errors']}"
                )

                # Update last check time
                last_check = datetime.now(timezone.utc)

            except Exception as e:
                logger.error(f"Error in polling loop: {e}")

            # Wait before next poll
            time.sleep(self.poll_interval)


def test_outlook_connection():
    """Test Outlook connection and list recent emails."""
    print("Testing Outlook connection via Microsoft Graph API...")
    print()

    poller = OutlookEmailPoller()

    # Check configuration
    if not poller.client_id:
        print("❌ MS_CLIENT_ID not configured")
        print("Please set MS_CLIENT_ID in your .env file")
        return

    print(f"Client ID: {poller.client_id}")
    print(f"Tenant ID: {poller.tenant_id}")
    print(f"Client Secret: {'Configured' if poller.client_secret else 'Not configured'}")
    print()

    # Fetch emails
    emails = poller.fetch_emails(limit=5)

    if not emails:
        print("No emails found or authentication failed")
        return

    print(f"✅ Successfully fetched {len(emails)} emails:")
    print()
    for email in emails:
        print(f"  {email.get('receivedDateTime')} | {email.get('from', {}).get('emailAddress', {}).get('address')} | {email.get('subject')}")
        print(f"    ID: {email.get('id')}")
        print(f"    Attachments: {'Yes' if email.get('hasAttachments') else 'No'}")
        print()


if __name__ == "__main__":
    test_outlook_connection()
