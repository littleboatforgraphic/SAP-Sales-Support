"""
Test script for core modules using mock data.
Run this to verify the foundation infrastructure works correctly.
Uses a temporary database to avoid polluting the development database.
"""
import tempfile
import os
from datetime import datetime, timezone
from database import get_engine, get_sessionmaker, Base
from glossary import GlossaryManager, seed_glossary
from sku_index import SKUIndexManager, seed_sku_index
from price_table import PriceTableManager, seed_price_table
from audit_log import AuditLogger
from trigger import TriggerDetector
from mock_sap_client import MockAutoCountClient
from mock_email_monitor import MockEmailMonitor
from config import settings


def get_temp_db():
    """Create a temporary database for testing."""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()
    return temp_db.name


def cleanup_temp_db(db_path: str):
    """Clean up temporary database."""
    try:
        os.unlink(db_path)
    except:
        pass


def test_glossary():
    """Test glossary lookup and term resolution."""
    print("\n=== Testing Glossary Module ===")
    temp_db = get_temp_db()
    engine = get_engine(f"sqlite:///{temp_db}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker(engine)
    db = SessionLocal()

    try:
        glossary = GlossaryManager(db)
        seed_glossary(db)

        # Test lookup
        result = glossary.lookup("pcs")
        print(f"Lookup 'pcs': {result}")
        assert result == "PCS", "Glossary lookup failed"

        result = glossary.lookup("order")
        print(f"Lookup 'order': {result}")
        assert result == "ORDER", "Glossary lookup failed"

        # Test non-existent term
        result = glossary.lookup("nonexistent")
        print(f"Lookup 'nonexistent': {result}")
        assert result is None, "Glossary should return None for non-existent term"

        print("[PASS] Glossary module tests passed")

    finally:
        db.close()
        cleanup_temp_db(temp_db)


def test_sku_index():
    """Test SKU fuzzy matching."""
    print("\n=== Testing SKU Index Module ===")
    temp_db = get_temp_db()
    engine = get_engine(f"sqlite:///{temp_db}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker(engine)
    db = SessionLocal()

    try:
        sku_index = SKUIndexManager(db)
        seed_sku_index(db)

        # Test fuzzy match
        matches = sku_index.fuzzy_match("weldmesh")
        print(f"Fuzzy match 'weldmesh': {len(matches)} matches")
        assert len(matches) > 0, "SKU fuzzy match failed"
        print(f"  Top match: {matches[0]['sku']} - {matches[0]['description']}")

        # Test exact SKU match
        entry = sku_index.get_by_sku("WM-001")
        print(f"Get by SKU 'WM-001': {entry.description if entry else 'Not found'}")
        assert entry is not None, "SKU lookup failed"

        print("[PASS] SKU index module tests passed")

    finally:
        db.close()
        cleanup_temp_db(temp_db)


def test_price_table():
    """Test price table lookup."""
    print("\n=== Testing Price Table Module ===")
    temp_db = get_temp_db()
    engine = get_engine(f"sqlite:///{temp_db}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker(engine)
    db = SessionLocal()

    try:
        price_table = PriceTableManager(db)
        seed_price_table(db)

        # Test get current price
        price = price_table.get_current_price("WM-001")
        print(f"Current price for WM-001: RM{price}")
        assert price is not None, "Price lookup failed"

        # Test non-existent SKU
        price = price_table.get_current_price("NONEXISTENT")
        print(f"Current price for NONEXISTENT: {price}")
        assert price is None, "Should return None for non-existent SKU"

        print("[PASS] Price table module tests passed")

    finally:
        db.close()
        cleanup_temp_db(temp_db)


def test_trigger_detection():
    """Test trigger detection logic."""
    print("\n=== Testing Trigger Detection ===")
    temp_db = get_temp_db()
    engine = get_engine(f"sqlite:///{temp_db}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker(engine)
    db = SessionLocal()

    try:
        glossary = GlossaryManager(db)
        seed_glossary(db)
        trigger_detector = TriggerDetector(glossary)

        # Test explicit prefix
        result = trigger_detector.detect("AI check stock for WM-001")
        print(f"Explicit prefix detection: {result}")
        assert result == "explicit", "Explicit prefix detection failed"

        # Test keyword fallback
        result = trigger_detector.detect("I need a quotation for wire mesh")
        print(f"Keyword fallback detection: {result}")
        assert result == "keyword", "Keyword fallback detection failed"

        # Test no trigger
        result = trigger_detector.detect("Hello, how are you?")
        print(f"No trigger detection: {result}")
        assert result is None, "Should return None for non-trigger message"

        print("[PASS] Trigger detection tests passed")

    finally:
        db.close()
        cleanup_temp_db(temp_db)


def test_audit_log():
    """Test audit logging."""
    print("\n=== Testing Audit Log Module ===")
    temp_db = get_temp_db()
    engine = get_engine(f"sqlite:///{temp_db}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker(engine)
    db = SessionLocal()

    try:
        audit_logger = AuditLogger(db)

        # Test log price used
        entry = audit_logger.log_price_used(
            order_reference="TEST-001",
            sku="WM-001",
            price=45.00,
            actor="test_agent"
        )
        print(f"Logged price used: {entry.id}")

        # Test log document sent
        entry = audit_logger.log_document_sent(
            order_reference="TEST-001",
            document_type="invoice",
            recipient="customer@example.com",
            channel="email",
            actor="test_agent"
        )
        print(f"Logged document sent: {entry.id}")

        # Test get audit trail
        trail = audit_logger.get_audit_trail(entity_type="order", entity_reference="TEST-001")
        print(f"Audit trail entries: {len(trail)}")
        assert len(trail) >= 2, "Audit trail should have at least 2 entries"

        print("[PASS] Audit log tests passed")

    finally:
        db.close()
        cleanup_temp_db(temp_db)


def test_mock_sap_client():
    """Test mock AutoCount client."""
    print("\n=== Testing Mock AutoCount Client ===")
    sap_client = MockAutoCountClient()

    # Test get stock
    stock = sap_client.get_stock("WM-001")
    print(f"Stock for WM-001: {stock}")
    assert stock == 150, "Mock stock lookup failed"

    # Test get customer details
    customer = sap_client.get_customer_details("CUST001")
    print(f"Customer CUST001: {customer['name']}, Trading House: {customer['is_trading_house']}")
    assert customer is not None, "Mock customer lookup failed"

    # Test is trading house
    is_trading = sap_client.is_trading_house("CUST001")
    print(f"CUST001 is trading house: {is_trading}")
    assert is_trading == True, "Trading house check failed"

    # Test get customer addresses
    addresses = sap_client.get_customer_addresses("CUST001")
    print(f"CUST001 addresses: {len(addresses)}")
    assert len(addresses) == 2, "Address lookup failed"

    # Test create sales order
    so_ref = sap_client.create_sales_order({"customer_id": "CUST001"})
    print(f"Created sales order: {so_ref}")
    assert so_ref.startswith("SO-"), "Sales order creation failed"

    print("[PASS] Mock AutoCount client tests passed")


def test_mock_email_monitor():
    """Test mock email monitor."""
    print("\n=== Testing Mock Email Monitor ===")
    email_monitor = MockEmailMonitor()

    # Test connect
    email_monitor.connect()

    # Test poll emails
    emails = email_monitor.poll_emails()
    print(f"Polled {len(emails)} PO emails")
    assert len(emails) == 2, "Email polling failed"

    # Test is allowed sender
    allowed = email_monitor.is_allowed_sender("customer1@example.com")
    print(f"customer1@example.com is allowed: {allowed}")
    assert allowed == True, "Sender allowlist check failed"

    # Test contains PO keywords
    has_keywords = email_monitor.contains_po_keywords("PO-2026-001")
    print(f"'PO-2026-001' contains PO keywords: {has_keywords}")
    assert has_keywords == True, "PO keyword check failed"

    print("[PASS] Mock email monitor tests passed")


def test_trigger_detection():
    """Test trigger detection logic."""
    print("\n=== Testing Trigger Detection ===")
    temp_db = get_temp_db()
    engine = get_engine(f"sqlite:///{temp_db}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker(engine)
    db = SessionLocal()

    try:
        glossary = GlossaryManager(db)
        seed_glossary(db)
        trigger_detector = TriggerDetector(glossary)

        # Test explicit prefix with word boundary
        result = trigger_detector.detect("AI check stock for WM-001")
        print(f"Explicit prefix detection: {result}")
        assert result == "explicit", "Explicit prefix detection failed"

        # Test that "Aiman" doesn't trigger "ai"
        result = trigger_detector.detect("Aiman is coming tomorrow")
        print(f"'Aiman' should not trigger: {result}")
        assert result is None, "Word boundary should prevent 'Aiman' from triggering"

        # Test that "aircond" doesn't trigger "air"
        result = trigger_detector.detect("The aircond is broken")
        print(f"'aircond' should not trigger: {result}")
        assert result is None, "Word boundary should prevent 'aircond' from triggering"

        # Test keyword fallback
        result = trigger_detector.detect("I need a quotation for wire mesh")
        print(f"Keyword fallback detection: {result}")
        assert result == "keyword", "Keyword fallback detection failed"

        # Test risky keyword without context
        result = trigger_detector.detect("What time is the meeting?")
        print(f"'meeting' without business context: {result}")
        assert result is None, "Risky keyword without context should not trigger"

        # Test risky keyword with context
        result = trigger_detector.detect("Check stock for the order")
        print(f"'order' with business context: {result}")
        assert result == "keyword", "Risky keyword with context should trigger"

        # Test no trigger
        result = trigger_detector.detect("Hello, how are you?")
        print(f"No trigger detection: {result}")
        assert result is None, "Should return None for non-trigger message"

        print("[PASS] Trigger detection tests passed")

    finally:
        db.close()
        cleanup_temp_db(temp_db)


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Core Modules with Mock Data")
    print("=" * 60)

    try:
        test_glossary()
        test_sku_index()
        test_price_table()
        test_trigger_detection()
        test_audit_log()
        test_mock_sap_client()
        test_mock_email_monitor()

        print("\n" + "=" * 60)
        print("[PASS] ALL TESTS PASSED")
        print("=" * 60)
        print("\nThe foundation infrastructure is working correctly.")
        print("You can now build the agents using these mock clients for testing.")

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
