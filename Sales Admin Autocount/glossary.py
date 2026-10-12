from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database import GlossaryEntry, GlossaryStatus, GlossaryCategory, get_sessionmaker
from config import settings


class GlossaryManager:
    """Manages glossary entries for shortform/term resolution."""

    def __init__(self, session: Session):
        self.session = session

    def lookup(self, term: str) -> Optional[str]:
        """
        Look up a term in the glossary.
        Returns the canonical value if found and approved, None otherwise.
        Increments usage count on successful lookup.
        """
        term_normalized = term.strip().lower()

        entry = self.session.query(GlossaryEntry).filter(
            GlossaryEntry.term == term_normalized,
            GlossaryEntry.status == GlossaryStatus.APPROVED
        ).first()

        if entry:
            # Increment usage count
            entry.usage_count += 1
            entry.last_used_at = datetime.now(timezone.utc)
            self.session.commit()
            return entry.canonical_value

        return None

    def propose_entry(
        self,
        term: str,
        canonical_value: str,
        category: GlossaryCategory,
        conversation_id: Optional[str] = None
    ) -> GlossaryEntry:
        """
        Propose a new glossary entry.
        Entry is created with PENDING status awaiting admin approval.
        """
        term_normalized = term.strip().lower()

        # Check if already exists
        existing = self.session.query(GlossaryEntry).filter(
            GlossaryEntry.term == term_normalized
        ).first()

        if existing:
            # Update existing entry if it's pending
            if existing.status == GlossaryStatus.PENDING:
                existing.canonical_value = canonical_value
                existing.category = category
                existing.created_from_conversation = conversation_id or existing.created_from_conversation
                self.session.commit()
                return existing
            else:
                # Already approved or rejected, don't create duplicate
                return existing

        entry = GlossaryEntry(
            term=term_normalized,
            canonical_value=canonical_value,
            category=category,
            status=GlossaryStatus.PENDING,
            created_from_conversation=conversation_id,
            created_at=datetime.now(timezone.utc)
        )

        self.session.add(entry)
        self.session.commit()
        return entry

    def approve_entry(self, entry_id: int, approved_by: str) -> bool:
        """Approve a pending glossary entry."""
        entry = self.session.query(GlossaryEntry).filter(
            GlossaryEntry.id == entry_id
        ).first()

        if not entry:
            return False

        entry.status = GlossaryStatus.APPROVED
        entry.approved_by = approved_by
        entry.approved_at = datetime.now(timezone.utc)
        self.session.commit()
        return True

    def reject_entry(self, entry_id: int, approved_by: str) -> bool:
        """Reject a pending glossary entry."""
        entry = self.session.query(GlossaryEntry).filter(
            GlossaryEntry.id == entry_id
        ).first()

        if not entry:
            return False

        entry.status = GlossaryStatus.REJECTED
        entry.approved_by = approved_by
        entry.approved_at = datetime.now(timezone.utc)
        self.session.commit()
        return True

    def get_pending_entries(self) -> List[GlossaryEntry]:
        """Get all pending glossary entries awaiting approval."""
        return self.session.query(GlossaryEntry).filter(
            GlossaryEntry.status == GlossaryStatus.PENDING
        ).order_by(GlossaryEntry.created_at).all()

    def get_approved_entries(self) -> List[GlossaryEntry]:
        """Get all approved glossary entries."""
        return self.session.query(GlossaryEntry).filter(
            GlossaryEntry.status == GlossaryStatus.APPROVED
        ).order_by(GlossaryEntry.usage_count.desc()).all()

    def search_similar(self, term: str, limit: int = 5) -> List[GlossaryEntry]:
        """
        Search for similar terms (simple substring match).
        Used when suggesting alternatives for unresolved terms.
        """
        term_normalized = term.strip().lower()

        entries = self.session.query(GlossaryEntry).filter(
            GlossaryEntry.status == GlossaryStatus.APPROVED,
            GlossaryEntry.term.contains(term_normalized)
        ).limit(limit).all()

        return entries


# Seed data for initial glossary
SEED_GLOSSARY = [
    # Wire mesh specific terms
    ("mesh", "MESH", GlossaryCategory.PRODUCT_SPEC),
    ("wire", "WIRE", GlossaryCategory.PRODUCT_SPEC),
    ("steel", "STEEL", GlossaryCategory.PRODUCT_SPEC),
    ("brc", "BRC", GlossaryCategory.PRODUCT_SPEC),
    ("weldmesh", "WELDMESH", GlossaryCategory.PRODUCT_SPEC),
    ("galvanized", "GALVANIZED", GlossaryCategory.PRODUCT_SPEC),
    ("mild steel", "MS", GlossaryCategory.PRODUCT_SPEC),

    # Units
    ("pcs", "PCS", GlossaryCategory.UNIT),
    ("pieces", "PCS", GlossaryCategory.UNIT),
    ("set", "SET", GlossaryCategory.UNIT),
    ("kg", "KG", GlossaryCategory.UNIT),
    ("kilogram", "KILOGRAM", GlossaryCategory.UNIT),
    ("mt", "MT", GlossaryCategory.UNIT),
    ("meter", "M", GlossaryCategory.UNIT),
    ("m", "M", GlossaryCategory.UNIT),
    ("sqm", "SQM", GlossaryCategory.UNIT),
    ("sq ft", "SQFT", GlossaryCategory.UNIT),
    ("sqft", "SQFT", GlossaryCategory.UNIT),

    # Business terms (English)
    ("quotation", "QUOTATION", GlossaryCategory.BUSINESS_TERM),
    ("quote", "QUOTATION", GlossaryCategory.BUSINESS_TERM),
    ("invoice", "INVOICE", GlossaryCategory.BUSINESS_TERM),
    ("so", "SALES_ORDER", GlossaryCategory.BUSINESS_TERM),
    ("sales order", "SALES_ORDER", GlossaryCategory.BUSINESS_TERM),
    ("po", "PURCHASE_ORDER", GlossaryCategory.BUSINESS_TERM),
    ("purchase order", "PURCHASE_ORDER", GlossaryCategory.BUSINESS_TERM),
    ("do", "DELIVERY_ORDER", GlossaryCategory.BUSINESS_TERM),
    ("delivery order", "DELIVERY_ORDER", GlossaryCategory.BUSINESS_TERM),
    ("new acc", "NEW_CUSTOMER", GlossaryCategory.BUSINESS_TERM),
    ("new account", "NEW_CUSTOMER", GlossaryCategory.BUSINESS_TERM),
    ("payment", "PAYMENT", GlossaryCategory.BUSINESS_TERM),
    ("stock", "STOCK", GlossaryCategory.BUSINESS_TERM),
    ("order", "ORDER", GlossaryCategory.BUSINESS_TERM),

    # Business terms (Malay)
    ("sebut harga", "QUOTATION", GlossaryCategory.BUSINESS_TERM),
    ("invois", "INVOICE", GlossaryCategory.BUSINESS_TERM),
    ("pesanan", "ORDER", GlossaryCategory.BUSINESS_TERM),
    ("stok", "STOCK", GlossaryCategory.BUSINESS_TERM),
    ("bayaran", "PAYMENT", GlossaryCategory.BUSINESS_TERM),
]


def seed_glossary(session: Session):
    """Seed the glossary with initial entries."""
    for term, canonical_value, category in SEED_GLOSSARY:
        existing = session.query(GlossaryEntry).filter(
            GlossaryEntry.term == term
        ).first()

        if not existing:
            entry = GlossaryEntry(
                term=term,
                canonical_value=canonical_value,
                category=category,
                status=GlossaryStatus.APPROVED,
                created_from_conversation="seed",
                created_at=datetime.now(timezone.utc)
            )
            session.add(entry)

    session.commit()
    print(f"Seeded {len(SEED_GLOSSARY)} glossary entries.")
