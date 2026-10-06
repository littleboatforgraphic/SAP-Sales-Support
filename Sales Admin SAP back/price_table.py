from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database import PriceReferenceEntry, get_sessionmaker


class PriceTableManager:
    """
    Manages price reference table.
    This is read-only for agents - price updates are done manually by admin.
    """

    def __init__(self, session: Session):
        self.session = session

    def get_current_price(self, sku: str) -> Optional[float]:
        """
        Get the current price for a SKU.
        Returns the price if a valid entry exists, None otherwise.
        A valid entry has effective_to as NULL (current) and effective_to >= now.
        """
        now = datetime.now(timezone.utc)

        entry = self.session.query(PriceReferenceEntry).filter(
            PriceReferenceEntry.sku == sku,
            PriceReferenceEntry.effective_from <= now,
            (PriceReferenceEntry.effective_to.is_(None) | (PriceReferenceEntry.effective_to >= now))
        ).order_by(PriceReferenceEntry.effective_from.desc()).first()

        if entry:
            return entry.price

        return None

    def get_price_at_date(self, sku: str, date: datetime) -> Optional[float]:
        """
        Get the price for a SKU at a specific date.
        Used for historical price lookup and audit purposes.
        """
        entry = self.session.query(PriceReferenceEntry).filter(
            PriceReferenceEntry.sku == sku,
            PriceReferenceEntry.effective_from <= date,
            (PriceReferenceEntry.effective_to.is_(None) | (PriceReferenceEntry.effective_to >= date))
        ).order_by(PriceReferenceEntry.effective_from.desc()).first()

        if entry:
            return entry.price

        return None

    def update_price(
        self,
        sku: str,
        new_price: float,
        updated_by: str,
        effective_from: Optional[datetime] = None
    ) -> PriceReferenceEntry:
        """
        Update the price for a SKU.
        This creates a new entry with the new price and sets the previous
        entry's effective_to to now (historical price tracking).
        This method is intended for admin use only, not agent use.
        """
        now = datetime.now(timezone.utc)
        effective_from = effective_from or now

        # Get current price entry and set its effective_to
        current_entry = self.session.query(PriceReferenceEntry).filter(
            PriceReferenceEntry.sku == sku,
            PriceReferenceEntry.effective_to.is_(None)
        ).first()

        if current_entry:
            current_entry.effective_to = now

        # Create new price entry
        new_entry = PriceReferenceEntry(
            sku=sku,
            price=new_price,
            updated_by=updated_by,
            updated_at=now,
            effective_from=effective_from,
            effective_to=None
        )

        self.session.add(new_entry)
        self.session.commit()
        return new_entry

    def get_price_history(self, sku: str) -> list[PriceReferenceEntry]:
        """Get the full price history for a SKU."""
        return self.session.query(PriceReferenceEntry).filter(
            PriceReferenceEntry.sku == sku
        ).order_by(PriceReferenceEntry.effective_from.desc()).all()

    def get_all_current_prices(self) -> list[PriceReferenceEntry]:
        """Get all current prices (effective_to is NULL)."""
        now = datetime.now(timezone.utc)

        return self.session.query(PriceReferenceEntry).filter(
            PriceReferenceEntry.effective_to.is_(None),
            PriceReferenceEntry.effective_from <= now
        ).all()


# Mock seed data for prices
SEED_PRICES = [
    ("WM-001", 45.00),
    ("WM-002", 55.00),
    ("WM-003", 65.00),
    ("BRC-A142", 85.00),
    ("BRC-A193", 110.00),
    ("WELD-5050", 40.00),
]


def seed_price_table(session: Session):
    """Seed the price table with mock prices."""
    for sku, price in SEED_PRICES:
        existing = session.query(PriceReferenceEntry).filter(
            PriceReferenceEntry.sku == sku,
            PriceReferenceEntry.effective_to.is_(None)
        ).first()

        if not existing:
            entry = PriceReferenceEntry(
                sku=sku,
                price=price,
                updated_by="seed",
                updated_at=datetime.now(timezone.utc),
                effective_from=datetime.now(timezone.utc),
                effective_to=None
            )
            session.add(entry)

    session.commit()
    print(f"Seeded {len(SEED_PRICES)} price entries.")
