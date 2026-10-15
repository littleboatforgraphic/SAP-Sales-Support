"""
End-to-end Gmail IMAP test for the Email Order Agent.

Fetches unread emails from the configured Gmail inbox, runs each through the
full pipeline (triage -> LLM extraction -> customer match -> AutoCount draft),
and prints a detailed verification report per email.

Usage:
    python test_gmail_email.py            # process unread inbox mail
    python test_gmail_email.py --fetch-only   # connectivity check only

Prerequisites (.env):
    GMAIL_IMAP_USERNAME   - the test mailbox address
    GMAIL_IMAP_PASSWORD   - Gmail app password (not the account password)
    ILMU_API_KEY          - required for order extraction
    EMAIL_ENABLED=true
    EMAIL_CAN_DRAFT=true
    (leave AOTG_* empty to use the mock AutoCount client)
"""

import argparse
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
# Keep httpx noise down
logging.getLogger("httpx").setLevel(logging.WARNING)

from config import settings
from database import get_db_session_factory, init_database
from gmail_poller import GmailEmailPoller


def print_result(idx: int, email: dict, result: dict) -> None:
    """Print a verification report for one processed email."""
    print("=" * 72)
    print(f"EMAIL {idx}: {email.get('subject', '')!r}")
    print(f"  from: {email.get('from')}")
    print(f"  attachments fetched: {[n for n, _ in email.get('attachments', [])]}")
    print("-" * 72)

    status = result.get("status")
    print(f"  pipeline status: {status}")

    if status == "duplicate":
        print("  (skipped - already processed; delete the audit row or send a new email to re-test)")
        return

    pr = result.get("processing_result") or {}
    if not pr:
        print(f"  raw result: {json.dumps(result, indent=2, default=str)[:2000]}")
        return

    draft = pr.get("draft") or {}
    ac = draft.get("autocount_draft") or {}
    customer = draft.get("customer") or {}
    order = draft.get("order") or {}
    flags = draft.get("flags") or {}

    print(f"  agent status:      {pr.get('status')}  | autonomy: {pr.get('autonomy_mode')}"
          f" -> {pr.get('autonomy_decision')} ({pr.get('autonomy_reason')})")
    print(f"  scenario:          {draft.get('scenario')}")
    print(f"  autocount draft:   {ac.get('document_type')} {ac.get('document_number')}"
          f"  [{ac.get('message')}]")
    print(f"  customer match:    {customer.get('status')}  debtor={customer.get('debtor_code')}"
          f"  name={customer.get('company_name')!r}  score={customer.get('score')}"
          f"  trading_house={customer.get('is_trading_house')}")
    print(f"  order:             doc_type={order.get('doc_type')}  po={order.get('po_number')}"
          f"  buyer={order.get('buyer_name')!r}  total={order.get('total')} {order.get('currency')}"
          f"  confidence={order.get('confidence')}")

    for line in draft.get("lines", []):
        print(f"    line: {line.get('item_code')} | {line.get('description')} |"
              f" qty={line.get('quantity')} price={line.get('unit_price')} amount={line.get('amount')}")

    for severity in ("block", "warn", "info"):
        for f in flags.get(severity, []):
            print(f"  flag[{severity}]: {f}")

    # Verification checklist
    print("-" * 72)
    expected = "ARInvoice" if order.get("po_number") else "SalesOrder"
    got = ac.get("document_type")
    matched = customer.get("status") == "matched"
    checks = [
        ("scenario matches PO presence",
         (draft.get("scenario") == "confirmed_po") == bool(order.get("po_number"))),
        # a draft is only created when the customer matched - that is by design
        (f"doc type is {expected} (or none when unmatched)",
         got == expected if matched else got == "none"),
        ("customer matched", matched),
        ("draft doc number issued", bool(ac.get("document_number")) if matched else True),
    ]
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-only", action="store_true",
                        help="only fetch email summaries, skip agent processing")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    if not (settings.gmail_imap_username and
            settings.gmail_imap_password and
            settings.gmail_imap_password.get_secret_value()):
        print("GMAIL_IMAP_USERNAME / GMAIL_IMAP_PASSWORD not set in .env")
        return 1

    if not settings.ilmu_api_key:
        print("WARNING: ILMU_API_KEY not set - order extraction will fail\n")

    poller = GmailEmailPoller()
    if not poller.use_imap:
        print("IMAP not selected (Gmail API credentials take precedence if set)")
        return 1

    print(f"Fetching up to {args.limit} unread emails from {settings.gmail_imap_username}...")
    emails = poller.fetch_emails(limit=args.limit)
    print(f"Fetched {len(emails)} emails\n")

    for e in emails:
        print(f"  - {e.get('received_at')} | {e.get('from')} | {e.get('subject')!r}"
              f" | atts={len(e.get('attachments', []))}")
    print()

    if args.fetch_only or not emails:
        return 0

    try:
        session_factory = get_db_session_factory()
    except RuntimeError:
        init_database(settings.database_url)
        session_factory = get_db_session_factory()
    db = session_factory()
    try:
        for idx, email in enumerate(emails, 1):
            try:
                result = poller.process_email_with_agent(email, db)
            except Exception as exc:
                print("=" * 72)
                print(f"EMAIL {idx}: {email.get('subject')!r}")
                print(f"  FAILED: {type(exc).__name__}: {exc}")
                continue
            print_result(idx, email, result)
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
