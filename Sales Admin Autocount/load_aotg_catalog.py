"""
Load AOTG API catalog from Swagger specification into the database.

This script fetches the AOTG Swagger specification and imports it into
the knowledge models for controlled agent access.

Usage:
    python load_aotg_catalog.py
"""

import argparse
import json
import sys
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from database import get_db_session_factory
from aotg_catalog_loader import import_catalog
from config import settings


def fetch_aotg_swagger() -> dict:
    """Fetch the AOTG Swagger specification from the official API."""
    swagger_url = f"{settings.aotg_base_url}/swagger/docs/v1"

    print(f"Fetching AOTG Swagger specification from: {swagger_url}")

    try:
        response = httpx.get(swagger_url, timeout=30.0)
        response.raise_for_status()
        spec = response.json()

        print(f"Successfully fetched Swagger specification")
        print(f"  Title: {spec.get('info', {}).get('title', 'Unknown')}")
        print(f"  Version: {spec.get('info', {}).get('version', 'Unknown')}")
        print(f"  Paths: {len(spec.get('paths', {}))}")

        return spec
    except httpx.HTTPStatusError as e:
        print(f"ERROR: HTTP error fetching Swagger: {e.response.status_code}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to fetch Swagger specification: {e}")
        sys.exit(1)


def load_catalog(spec: Optional[dict] = None, source_url: Optional[str] = None):
    """Load the AOTG catalog into the database."""
    SessionLocal = get_db_session_factory()

    if spec is None:
        spec = fetch_aotg_swagger()

    if source_url is None:
        source_url = f"{settings.aotg_base_url}/swagger/docs/v1"

    with SessionLocal() as session:
        try:
            print("\nImporting catalog into database...")
            snapshot = import_catalog(session, spec, source_url)

            print(f"\nSuccessfully imported catalog:")
            print(f"  Snapshot ID: {snapshot.id}")
            print(f"  Base URL: {snapshot.base_url}")
            print(f"  Document Version: {snapshot.document_version}")
            print(f"  Operation Count: {snapshot.operation_count}")
            print(f"  Document SHA256: {snapshot.document_sha256}")

            # Count operations by risk level
            from aotg_knowledge_models import RiskLevel, AOTGOperation

            risk_counts = {}
            for risk in RiskLevel:
                count = (
                    session.query(AOTGOperation)
                    .filter(
                        AOTGOperation.spec_snapshot_id == snapshot.id,
                        AOTGOperation.risk_level == risk,
                    )
                    .count()
                )
                risk_counts[risk.value] = count

            print(f"\nOperations by risk level:")
            for risk, count in risk_counts.items():
                print(f"  {risk}: {count}")

            session.commit()
            print("\nCatalog loaded successfully!")

        except Exception as e:
            session.rollback()
            print(f"ERROR: Failed to import catalog: {e}")
            sys.exit(1)


def list_catalog():
    """List all loaded AOTG catalogs in the database."""
    SessionLocal = get_db_session_factory()

    with SessionLocal() as session:
        from aotg_knowledge_models import AOTGSpecSnapshot, AOTGOperation

        snapshots = session.query(AOTGSpecSnapshot).order_by(
            AOTGSpecSnapshot.imported_at.desc()
        ).all()

        if not snapshots:
            print("No AOTG catalogs loaded in the database.")
            return

        print(f"\nLoaded AOTG catalogs ({len(snapshots)}):")
        for snapshot in snapshots:
            active_marker = " [ACTIVE]" if snapshot.active else ""
            print(f"\n  ID: {snapshot.id}{active_marker}")
            print(f"  Source URL: {snapshot.source_url}")
            print(f"  Base URL: {snapshot.base_url}")
            print(f"  Document Version: {snapshot.document_version}")
            print(f"  Swagger Version: {snapshot.swagger_version}")
            print(f"  Operation Count: {snapshot.operation_count}")
            print(f"  Imported At: {snapshot.imported_at}")
            print(f"  Document SHA256: {snapshot.document_sha256}")

            # Count enabled operations
            enabled_count = (
                session.query(AOTGOperation)
                .filter(
                    AOTGOperation.spec_snapshot_id == snapshot.id,
                    AOTGOperation.enabled_for_agent == True,
                )
                .count()
            )
            print(f"  Enabled Operations: {enabled_count}/{snapshot.operation_count}")


def enable_operation(operation_id: str):
    """Enable a specific operation for agent use."""
    SessionLocal = get_db_session_factory()

    with SessionLocal() as session:
        from aotg_knowledge_models import AOTGOperation

        operation = (
            session.query(AOTGOperation)
            .filter(AOTGOperation.operation_id == operation_id)
            .first()
        )

        if not operation:
            print(f"ERROR: Operation not found: {operation_id}")
            sys.exit(1)

        operation.enabled_for_agent = True
        operation.execution_verified = True
        operation.verified_by = "system"
        operation.verified_at = session.bind.execute(
            "SELECT datetime('now')"
        ).scalar()

        session.commit()
        print(f"Enabled operation: {operation_id}")
        print(f"  Tag: {operation.tag}")
        print(f"  Method: {operation.http_method}")
        print(f"  Path: {operation.path}")
        print(f"  Risk Level: {operation.risk_level.value}")


def main():
    parser = argparse.ArgumentParser(
        description="Load and manage AOTG API catalog"
    )
    parser.add_argument(
        "--load",
        action="store_true",
        help="Load AOTG catalog from Swagger specification"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all loaded catalogs"
    )
    parser.add_argument(
        "--enable",
        type=str,
        metavar="OPERATION_ID",
        help="Enable a specific operation for agent use"
    )
    parser.add_argument(
        "--spec-file",
        type=str,
        metavar="PATH",
        help="Load from local Swagger JSON file instead of fetching"
    )
    parser.add_argument(
        "--source-url",
        type=str,
        metavar="URL",
        help="Override source URL for the catalog"
    )

    args = parser.parse_args()

    if args.list:
        list_catalog()
    elif args.enable:
        enable_operation(args.enable)
    elif args.load:
        spec = None
        if args.spec_file:
            print(f"Loading Swagger specification from file: {args.spec_file}")
            with open(args.spec_file, "r", encoding="utf-8") as f:
                spec = json.load(f)
        load_catalog(spec=spec, source_url=args.source_url)
    else:
        parser.print_help()
        print("\nExample usage:")
        print("  python load_aotg_catalog.py --load")
        print("  python load_aotg_catalog.py --list")
        print("  python load_aotg_catalog.py --enable 'GET /api/public/v1/Debtor'")
        print("  python load_aotg_catalog.py --load --spec-file swagger.json")


if __name__ == "__main__":
    main()
