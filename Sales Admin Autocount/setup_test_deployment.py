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

from database import init_database, get_db_session_factory, StaffAllowlistEntry, StaffRole, Role, EmailConfig
from config import settings
from load_aotg_catalog import load_catalog, list_catalog


def add_test_staff(telegram_user_id: str, name: str = "Test User", roles: list = None):
    """Add a test staff member to the allowlist with specified roles."""
    if roles is None:
        roles = [Role.ADMIN]  # Default to Admin role

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
            # Add roles if they don't exist
            for role in roles:
                from role_helpers import add_role_to_staff
                if add_role_to_staff(session, existing.id, role):
                    print(f"  Added role: {role.value}")
            session.commit()
            return

        staff = StaffAllowlistEntry(
            telegram_user_id=telegram_user_id,
            name=name,
            active=True,
            added_by="setup_script",
        )

        session.add(staff)
        session.flush()  # Get the ID

        # Add roles
        for role in roles:
            staff_role = StaffRole(staff_id=staff.id, role=role)
            session.add(staff_role)

        session.commit()

        print(f"Added staff member: {name}")
        print(f"  Telegram User ID: {telegram_user_id}")
        print(f"  Roles: {', '.join([r.value for r in roles])}")


def add_test_prices():
    """Add test price data for mock items."""
    SessionLocal = get_db_session_factory()

    with SessionLocal() as session:
        from database import PriceReferenceEntry
        from datetime import datetime, timezone

        # Check if prices already exist
        existing = session.query(PriceReferenceEntry).first()
        if existing:
            print("Price data already exists")
            return

        # Add mock prices
        mock_prices = [
            {"sku": "WM-001", "price": 100.0},
            {"sku": "WM-002", "price": 150.0},
            {"sku": "WM-003", "price": 200.0},
            {"sku": "BRC-A142", "price": 50.0},
            {"sku": "BRC-A193", "price": 75.0},
            {"sku": "WELD-5050", "price": 300.0},
        ]

        for price_data in mock_prices:
            price = PriceReferenceEntry(
                sku=price_data["sku"],
                price=price_data["price"],
                updated_by="setup_script",
                effective_from=datetime.now(timezone.utc),
            )
            session.add(price)

        session.commit()
        print(f"Added {len(mock_prices)} price entries")


def add_email_config():
    """Add test email configuration for PO processing."""
    SessionLocal = get_db_session_factory()

    with SessionLocal() as session:
        # Check if config already exists
        existing = session.query(EmailConfig).first()
        if existing:
            print("Email config already exists")
            return

        # Add mock email config (no sender allowlist - accepts all PO emails)
        config = EmailConfig(
            imap_server="imap.example.com",
            imap_port=993,
            username="sales@example.com",
            password="mock_password",  # Should use SecretStr in production
            folder="INBOX",
            po_sender_allowlist=[],  # Empty list - accepts all senders
            po_keywords=["PO", "Purchase Order", "Order"],
            active=True
        )
        session.add(config)
        session.commit()
        print("Added email configuration (accepts all PO emails)")


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
        "--roles",
        type=str,
        default="admin",
        help="Comma-separated roles (admin,sales,finance,logistics) - default: admin"
    )
    parser.add_argument(
        "--add-prices",
        action="store_true",
        help="Add test price data for mock items"
    )
    parser.add_argument(
        "--add-email-config",
        action="store_true",
        help="Add test email configuration for PO processing"
    )
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Only initialize database and load catalog (no staff setup)"
    )

    args = parser.parse_args()

    if args.init_only:
        setup()
    elif args.add_prices:
        # Initialize database first
        init_database(settings.database_url)
        add_test_prices()
    elif args.add_email_config:
        # Initialize database first
        init_database(settings.database_url)
        add_email_config()
    elif args.add_staff:
        # Initialize database first
        init_database(settings.database_url)
        # Parse roles
        role_names = [r.strip().lower() for r in args.roles.split(",")]
        role_map = {
            "admin": Role.ADMIN,
            "sales": Role.SALES,
            "finance": Role.FINANCE,
            "logistics": Role.LOGISTICS
        }
        roles = [role_map.get(name) for name in role_names if name in role_map]
        if not roles:
            print(f"Invalid roles: {args.roles}. Valid roles: admin, sales, finance, logistics")
            print("Defaulting to admin role")
            roles = [Role.ADMIN]
        add_test_staff(args.add_staff, args.name, roles)
    else:
        setup()


if __name__ == "__main__":
    main()
