"""
Setup script for AOTG trial deployment.

This script:
1. Initializes the database with AOTG knowledge models
2. Loads the AOTG catalog from Swagger
3. Adds a test staff member to the allowlist
4. Provides deployment instructions

Usage:
    python setup_test_deployment.py --telegram-user-id YOUR_TELEGRAM_ID
"""

import argparse
import sys
from sqlalchemy.orm import Session

from database import init_database, get_db_session_factory, StaffAllowlistEntry, Role
from config import settings
from load_aotg_catalog import load_catalog, list_catalog


def add_test_staff(telegram_user_id: str, name: str = "Test User"):
    """Add a test staff member to the allowlist."""
    SessionLocal = get_db_session_factory()

    with SessionLocal() as session:
        # Check if user already exists
        existing = (
            session.query(StaffAllowlistEntry)
            .filter(StaffAllowlistEntry.telegram_user_id == telegram_user_id)
            .first()
        )

        if existing:
            print(f"Staff member already exists: {existing.name} (ID: {telegram_user_id})")
            return

        staff = StaffAllowlistEntry(
            telegram_user_id=telegram_user_id,
            name=name,
            role=Role.ADMIN,
            active=True,
            added_by="setup_script",
        )

        session.add(staff)
        session.commit()

        print(f"Added staff member: {name}")
        print(f"  Telegram User ID: {telegram_user_id}")
        print(f"  Role: {Role.ADMIN.value}")


def setup():
    """Run the complete setup."""
    print("=" * 60)
    print("AOTG Trial Deployment Setup")
    print("=" * 60)

    # Initialize database
    print("\n1. Initializing database...")
    init_database(settings.database_url)
    print("   Database initialized successfully")

    # Load AOTG catalog
    print("\n2. Loading AOTG catalog...")
    load_catalog()

    # List catalog
    print("\n3. Catalog summary:")
    list_catalog()

    print("\n" + "=" * 60)
    print("Setup complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Add your Telegram user ID to the allowlist:")
    print("   python setup_test_deployment.py --add-staff YOUR_TELEGRAM_ID")
    print("\n2. Configure your .env file with:")
    print("   - TELEGRAM_BOT_TOKEN (from @BotFather)")
    print("   - TELEGRAM_WEBHOOK_SECRET_TOKEN (random string)")
    print("\n3. Set up the Telegram webhook:")
    print("   python setup_webhook.py --webhook-url YOUR_PUBLIC_URL/api/v1/webhook/telegram")
    print("\n4. Start the server:")
    print("   python main.py")
    print("\n5. Try commands in Telegram:")
    print("   /catalog")
    print("   /list")
    print("   /search debtor")


def main():
    parser = argparse.ArgumentParser(
        description="Setup AOTG trial deployment"
    )
    parser.add_argument(
        "--add-staff",
        type=str,
        metavar="TELEGRAM_USER_ID",
        help="Add your Telegram user ID to the staff allowlist"
    )
    parser.add_argument(
        "--name",
        type=str,
        default="Test User",
        help="Name for the staff member (default: Test User)"
    )
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Only initialize database and load catalog (no staff setup)"
    )

    args = parser.parse_args()

    if args.init_only:
        setup()
    elif args.add_staff:
        # Initialize database first
        init_database(settings.database_url)
        add_test_staff(args.add_staff, args.name)
    else:
        setup()


if __name__ == "__main__":
    main()
