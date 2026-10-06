"""
Mock email monitor for testing without real email server.
This simulates receiving PO emails for development and testing purposes.
"""
from typing import List, Dict, Any
from datetime import datetime, timezone


class MockEmailMonitor:
    """Mock email monitor that returns sample PO emails for testing."""

    def __init__(self):
        self.sample_pos = [
            {
                "email_id": "001",
                "sender": "customer1@example.com",
                "subject": "PO-2026-001 - Wire Mesh Order",
                "attachment": {
                    "filename": "PO-2026-001.pdf",
                    "content": b"MOCK PDF CONTENT"
                },
                "received_at": datetime.now(timezone.utc)
            },
            {
                "email_id": "002",
                "sender": "customer2@example.com",
                "subject": "Purchase Order #12345",
                "attachment": {
                    "filename": "PO-12345.pdf",
                    "content": b"MOCK PDF CONTENT"
                },
                "received_at": datetime.now(timezone.utc)
            }
        ]

    def connect(self):
        """Mock connection - does nothing."""
        print("[MOCK EMAIL] Connected to email server")

    def poll_emails(self) -> List[Dict[str, Any]]:
        """Poll for new emails (returns sample data)."""
        print(f"[MOCK EMAIL] Polled {len(self.sample_pos)} PO emails")
        return self.sample_pos

    def is_allowed_sender(self, sender: str) -> bool:
        """Check if sender is on allowlist (mock)."""
        allowed_senders = ["customer1@example.com", "customer2@example.com"]
        return any(allowed in sender for allowed in allowed_senders)

    def contains_po_keywords(self, subject: str) -> bool:
        """Check if subject contains PO keywords (mock)."""
        keywords = ["PO", "Purchase Order", "Order"]
        subject_lower = subject.lower()
        return any(keyword.lower() in subject_lower for keyword in keywords)
