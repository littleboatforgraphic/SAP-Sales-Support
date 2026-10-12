"""
Seed the database with initial data.
Run this after init_db.py to populate glossary, SKU index, and price table.
"""
from datetime import datetime, timezone
from database import get_engine, get_sessionmaker, StaffAllowlistEntry, Role
from glossary import GlossaryManager, seed_glossary
from sku_index import SKUIndexManager, seed_sku_index
from price_table import PriceTableManager, seed_price_table
from config import settings
import sys


def main():
    print("Seeding database with initial data...")

    engine = get_engine(settings.database_url)
    SessionLocal = get_sessionmaker(engine)
    db = SessionLocal()

    try:
        # Seed glossary
        print("\n--- Seeding Glossary ---")
        seed_glossary(db)

        # Seed SKU index
        print("\n--- Seeding SKU Index ---")
        seed_sku_index(db)

        # Seed price table
        print("\n--- Seeding Price Table ---")
        seed_price_table(db)

        # Add sample staff member (for testing)
        print("\n--- Adding Sample Staff Member ---")
        existing = db.query(StaffAllowlistEntry).filter(
            StaffAllowlistEntry.phone_number == "+60123456789"
        ).first()

        if not existing:
            staff = StaffAllowlistEntry(
                phone_number="+60123456789",
                telegram_user_id="123456789",  # Sample Telegram user ID for testing
                name="Test Admin",
                role=Role.ADMIN,
                active=True,
                added_at=datetime.now(timezone.utc),
                added_by="seed"
            )
            db.add(staff)
            db.commit()
            print("Added test admin: +60123456789 (Telegram ID 123456789)")
        else:
            print("Test admin already exists")

        print("\nDatabase seeding completed successfully!")
        print("\nNext steps:")
        print("1. Add real staff members to staff_allowlist table")
        print("2. Review and extend glossary entries based on real chat samples")
        print("3. Replace SKU index with real SAP data when SAP integration is ready")
        print("4. Update price table with current prices")

    except Exception as e:
        print(f"Error seeding database: {e}", file=sys.stderr)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    from datetime import datetime
    main()
