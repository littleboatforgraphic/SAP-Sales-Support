"""
Sync the item catalogue from AutoCount/AOTG into the agent's SKU index.

The synced catalog is what the agent uses to know what items exist:
- enquiry replies resolve item codes/descriptions from it
- order drafting resolves description-only lines against it
- Telegram/email lookups can list what is on sale

Run at deploy time and on a schedule (Task Scheduler / cron) to keep it
fresh. Only catalogue identity is stored (code, description, UOM) - stock
levels are always read live via get_stock_info() at reply time.

Usage:
    python sync_item_catalog.py                  # full pull (authoritative)
    python sync_item_catalog.py --keyword mesh   # partial pull, upsert only
    python sync_item_catalog.py --mock           # force the mock client
    python sync_item_catalog.py --list           # show the synced catalog
"""

import argparse
import json

from config import settings
from database import init_database, get_db_session_factory, SKUIndexEntry


def _client(force_mock: bool):
    if force_mock:
        from mock_autocount_client import MockAutoCountClient
        return MockAutoCountClient()
    from autocount_client import get_autocount_client
    return get_autocount_client()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync item catalogue from AutoCount")
    parser.add_argument("--keyword", help="Only pull items matching this keyword")
    parser.add_argument("--mock", action="store_true", help="Force the mock client")
    parser.add_argument("--list", action="store_true", help="List the synced catalog and exit")
    args = parser.parse_args()

    init_database(settings.database_url)
    db = get_db_session_factory()()
    try:
        if args.list:
            rows = db.query(SKUIndexEntry).filter(SKUIndexEntry.active == True).order_by(SKUIndexEntry.sku).all()
            for r in rows:
                spec = json.loads(r.spec_attributes) if r.spec_attributes else {}
                uom = spec.get("UOM") or ""
                print(f"{r.sku:<12} uom={uom:<6} {r.description}")
            print(f"\n{len(rows)} active SKUs")
            return

        from sku_index import SKUIndexManager
        count = SKUIndexManager(db).sync_from_autocount(
            client=_client(args.mock), keyword=args.keyword)
        print(f"Done: {count} SKUs upserted")
    finally:
        db.close()


if __name__ == "__main__":
    main()
