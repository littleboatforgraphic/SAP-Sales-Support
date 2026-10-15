"""
Manage the outbound email allowlist.

Two layers exist:
1. EMAIL_OUTBOUND_ALLOWLIST in .env - manual, comma-separated
2. outbound_allowlist DB table - auto-learned (customer match + dmarc=pass)
   plus manually added via this script (source="manual")

Usage:
    python manage_allowlist.py --list
    python manage_allowlist.py --add user@example.com
    python manage_allowlist.py --add user@example.com --debtor 300-A001
    python manage_allowlist.py --remove user@example.com
    python manage_allowlist.py --disable user@example.com
    python manage_allowlist.py --enable user@example.com
"""

import argparse
import sys
from datetime import datetime, timezone

from config import settings
from database import init_database, get_db_session_factory, OutboundAllowlistEntry


def get_db():
    try:
        factory = get_db_session_factory()
    except RuntimeError:
        init_database(settings.database_url)
        factory = get_db_session_factory()
    return factory()


def normalize(email: str) -> str:
    from email.utils import parseaddr
    addr = parseaddr(email or "")[1].strip().lower()
    if "@" not in addr:
        raise SystemExit(f"Not a valid email address: {email!r}")
    return addr


def cmd_list(db):
    rows = db.query(OutboundAllowlistEntry).order_by(OutboundAllowlistEntry.email).all()
    if not rows:
        print("No entries in the DB allowlist.")
    for r in rows:
        state = "active" if r.active else "DISABLED"
        print(f"  {r.email:<45} {r.source:<6} {state:<8} debtor={r.debtor_code or '-':<10} "
              f"seen={r.times_seen} last={r.last_seen_at:%Y-%m-%d %H:%M}")

    env_list = settings.email_outbound_allowlist or ""
    env_items = [e.strip() for e in env_list.split(",") if e.strip()]
    print(f"\n.env allowlist ({len(env_items)}): {', '.join(env_items) or '(empty)'}")


def cmd_add(db, email: str, debtor_code: str = None):
    addr = normalize(email)
    now = datetime.now(timezone.utc)
    entry = db.query(OutboundAllowlistEntry).filter(
        OutboundAllowlistEntry.email == addr).first()
    if entry:
        entry.active = True
        entry.source = "manual"
        if debtor_code:
            entry.debtor_code = debtor_code
        entry.last_seen_at = now
        action = "updated"
    else:
        db.add(OutboundAllowlistEntry(
            email=addr, debtor_code=debtor_code, source="manual",
            first_seen_at=now, last_seen_at=now))
        action = "added"
    db.commit()
    print(f"{action}: {addr}")


def cmd_remove(db, email: str):
    addr = normalize(email)
    n = db.query(OutboundAllowlistEntry).filter(
        OutboundAllowlistEntry.email == addr).delete()
    db.commit()
    print(f"removed: {addr}" if n else f"not found: {addr}")


def cmd_set_active(db, email: str, active: bool):
    addr = normalize(email)
    entry = db.query(OutboundAllowlistEntry).filter(
        OutboundAllowlistEntry.email == addr).first()
    if not entry:
        print(f"not found: {addr}")
        return
    entry.active = active
    db.commit()
    print(f"{'enabled' if active else 'disabled'}: {addr}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true", help="list DB + env allowlist entries")
    p.add_argument("--add", metavar="EMAIL", help="add or re-enable an address (source=manual)")
    p.add_argument("--debtor", metavar="CODE", help="AutoCount debtor code to link with --add")
    p.add_argument("--remove", metavar="EMAIL", help="delete an entry entirely")
    p.add_argument("--disable", metavar="EMAIL", help="block an entry without deleting it")
    p.add_argument("--enable", metavar="EMAIL", help="re-enable a disabled entry")
    args = p.parse_args()

    if not any([args.list, args.add, args.remove, args.disable, args.enable]):
        p.print_help()
        return 1

    db = get_db()
    try:
        if args.list:
            cmd_list(db)
        if args.add:
            cmd_add(db, args.add, args.debtor)
        if args.remove:
            cmd_remove(db, args.remove)
        if args.disable:
            cmd_set_active(db, args.disable, False)
        if args.enable:
            cmd_set_active(db, args.enable, True)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
