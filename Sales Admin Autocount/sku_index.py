from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database import SKUIndexEntry, get_sessionmaker
import json


class SKUIndexManager:
    """Manages SKU index for product lookup and fuzzy matching."""

    def __init__(self, session: Session):
        self.session = session

    def sync_from_sap(self) -> int:
        """
        Legacy method name - calls sync_from_autocount for backward compatibility.
        """
        return self.sync_from_autocount()

    def sync_from_autocount(self, client=None, keyword: Optional[str] = None) -> int:
        """
        Pull the item catalogue from AutoCount/AOTG (POST StockItem/GetList)
        and upsert it into the SKU index. This is the agent's knowledge of
        what items exist - item resolution, enquiries and order drafting all
        read this table rather than querying the ERP per request.

        Only catalogue identity is stored: code, description, UOM. Stock
        levels and prices are deliberately NOT persisted - quantities are
        always read live at answer time so the agent never repeats a stale
        snapshot.

        A full pull (no keyword) is authoritative: SKUs missing from the pull
        are deactivated so stale items stop matching. A keyword pull only
        upserts the returned subset (top-up refresh, nothing deactivated).

        Returns the number of SKUs upserted (0 = pull failed, index untouched).
        """
        if client is None:
            from autocount_client import get_autocount_client
            client = get_autocount_client()

        rows = client.list_stock_items(keyword=keyword) or []
        if not rows:
            print("Stock item pull returned 0 rows - catalogue left unchanged")
            return 0

        now = datetime.now(timezone.utc)
        seen = set()
        upserted = 0

        for row in rows:
            sku = (row.get("ItemCode") or "").strip().upper()
            if not sku:
                continue
            seen.add(sku)

            # Catalogue identity only - no stock levels or prices are stored
            spec = {k: row[k] for k in ("UOM",) if row.get(k) is not None}

            entry = self.session.query(SKUIndexEntry).filter(
                SKUIndexEntry.sku == sku
            ).first()
            if entry:
                entry.description = row.get("Description") or entry.description
                entry.spec_attributes = json.dumps(spec)
                entry.last_synced_at = now
                entry.active = True
            else:
                entry = SKUIndexEntry(
                    sku=sku,
                    description=row.get("Description") or sku,
                    spec_attributes=json.dumps(spec),
                    last_synced_at=now,
                    active=True,
                )
                self.session.add(entry)
            upserted += 1

        if keyword is None:
            # Full pull is authoritative: anything not returned is gone from
            # the catalogue and should no longer match.
            stale = self.session.query(SKUIndexEntry).filter(
                SKUIndexEntry.active == True,
                SKUIndexEntry.sku.notin_(seen),
            ).all()
            for entry in stale:
                entry.active = False

        self.session.commit()
        print(f"Synced {upserted} SKUs from AutoCount" +
              ("" if keyword is None else f" (keyword '{keyword}', no deactivation)"))
        return upserted

    def fuzzy_match(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Perform fuzzy matching against SKU index.
        Returns top matching candidates with confidence scores.
        Currently uses simple substring matching - can be enhanced with
        proper fuzzy matching library (e.g., fuzzywuzzy, rapidfuzz) later.
        """
        query_normalized = query.strip().lower()

        # Get all active SKUs
        entries = self.session.query(SKUIndexEntry).filter(
            SKUIndexEntry.active == True
        ).all()

        # Simple substring matching on SKU and description
        matches = []
        for entry in entries:
            score = 0

            # Check if query matches SKU exactly
            if query_normalized == entry.sku.lower():
                score = 100
            # Check if query is contained in SKU
            elif query_normalized in entry.sku.lower():
                score = 80
            # Whole query appears verbatim in the description - stronger
            # than any partial word overlap, so it must out-score the
            # word-match branch below (previously tied at 60).
            elif query_normalized in entry.description.lower():
                score = 75
            # Check partial word matches in description
            else:
                words = query_normalized.split()
                for word in words:
                    if word in entry.description.lower():
                        score += 15

            if score > 0:
                matches.append({
                    "sku": entry.sku,
                    "description": entry.description,
                    "spec_attributes": json.loads(entry.spec_attributes) if entry.spec_attributes else {},
                    "score": score,
                    "last_synced_at": entry.last_synced_at
                })

        # Sort by score descending and return top matches
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches[:limit]

    def get_by_sku(self, sku: str) -> Optional[SKUIndexEntry]:
        """Get SKU entry by exact SKU match."""
        return self.session.query(SKUIndexEntry).filter(
            SKUIndexEntry.sku == sku,
            SKUIndexEntry.active == True
        ).first()

    def add_entry(
        self,
        sku: str,
        description: str,
        spec_attributes: Optional[Dict[str, Any]] = None
    ) -> SKUIndexEntry:
        """Add or update a SKU entry (for manual seeding/testing)."""
        existing = self.session.query(SKUIndexEntry).filter(
            SKUIndexEntry.sku == sku
        ).first()

        if existing:
            existing.description = description
            existing.spec_attributes = json.dumps(spec_attributes) if spec_attributes else None
            existing.last_synced_at = datetime.now(timezone.utc)
            existing.active = True
            self.session.commit()
            return existing

        entry = SKUIndexEntry(
            sku=sku,
            description=description,
            spec_attributes=json.dumps(spec_attributes) if spec_attributes else None,
            last_synced_at=datetime.now(timezone.utc),
            active=True
        )

        self.session.add(entry)
        self.session.commit()
        return entry

    def deactivate_sku(self, sku: str) -> bool:
        """Soft-delete a SKU by setting active=False."""
        entry = self.session.query(SKUIndexEntry).filter(
            SKUIndexEntry.sku == sku
        ).first()

        if entry:
            entry.active = False
            self.session.commit()
            return True
        return False


# Mock seed data for wire mesh products
SEED_SKUS = [
    {
        "sku": "WM-001",
        "description": "Welded Wire Mesh 6mm x 6mm x 2.4m x 1.2m",
        "spec_attributes": {
            "wire_diameter": "6mm",
            "mesh_size": "6mm x 6mm",
            "length": "2.4m",
            "width": "1.2m",
            "material": "Mild Steel"
        }
    },
    {
        "sku": "WM-002",
        "description": "Welded Wire Mesh 8mm x 8mm x 2.4m x 1.2m",
        "spec_attributes": {
            "wire_diameter": "8mm",
            "mesh_size": "8mm x 8mm",
            "length": "2.4m",
            "width": "1.2m",
            "material": "Mild Steel"
        }
    },
    {
        "sku": "WM-003",
        "description": "Galvanized Wire Mesh 6mm x 6mm x 2.4m x 1.2m",
        "spec_attributes": {
            "wire_diameter": "6mm",
            "mesh_size": "6mm x 6mm",
            "length": "2.4m",
            "width": "1.2m",
            "material": "Galvanized Steel"
        }
    },
    {
        "sku": "BRC-A142",
        "description": "BRC Mesh A142 10mm x 10mm x 2.4m x 1.2m",
        "spec_attributes": {
            "wire_diameter": "10mm",
            "mesh_size": "10mm x 10mm",
            "length": "2.4m",
            "width": "1.2m",
            "material": "Mild Steel",
            "type": "BRC"
        }
    },
    {
        "sku": "BRC-A193",
        "description": "BRC Mesh A193 12mm x 12mm x 2.4m x 1.2m",
        "spec_attributes": {
            "wire_diameter": "12mm",
            "mesh_size": "12mm x 12mm",
            "length": "2.4m",
            "width": "1.2m",
            "material": "Mild Steel",
            "type": "BRC"
        }
    },
    {
        "sku": "WELD-5050",
        "description": "Weldmesh 5mm x 5mm x 2.4m x 1.2m",
        "spec_attributes": {
            "wire_diameter": "5mm",
            "mesh_size": "5mm x 5mm",
            "length": "2.4m",
            "width": "1.2m",
            "material": "Mild Steel"
        }
    },
]


def seed_sku_index(session: Session):
    """Seed the SKU index with mock wire mesh products."""
    for sku_data in SEED_SKUS:
        existing = session.query(SKUIndexEntry).filter(
            SKUIndexEntry.sku == sku_data["sku"]
        ).first()

        if not existing:
            entry = SKUIndexEntry(
                sku=sku_data["sku"],
                description=sku_data["description"],
                spec_attributes=json.dumps(sku_data["spec_attributes"]),
                last_synced_at=datetime.now(timezone.utc),
                active=True
            )
            session.add(entry)

    session.commit()
    print(f"Seeded {len(SEED_SKUS)} SKU entries.")
