"""
Test script for address validation logic using mock AutoCount client.
This tests the new fraud prevention feature for delivery address validation.
Uses a temporary database to avoid polluting the development database.
"""
import tempfile
import os
from database import get_engine, get_sessionmaker, Base
from address_validator import AddressValidator
from mock_autocount_client import MockAutoCountClient
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


def test_address_validation():
    """Test address validation scenarios."""
    print("\n=== Testing Address Validation ===")
    temp_db = get_temp_db()
    engine = get_engine(f"sqlite:///{temp_db}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker(engine)
    db = SessionLocal()
    autocount_client = MockAutoCountClient()

    try:
        validator = AddressValidator(db, autocount_client)

        # Test 1: Trading house with matching address
        print("\n--- Test 1: Trading house with matching address ---")
        result = validator.validate_delivery_address(
            "123, Jalan Industri, 40000 Shah Alam, Selangor",
            "300-A001"
        )
        print(f"Customer: {result['customer_id']}")
        print(f"Is Trading House: {result['is_trading_house']}")
        print(f"Match Found: {result['match_found']}")
        print(f"Best Similarity: {result['best_similarity']:.2f}")
        print(f"Validation Level: {result['validation_level']}")
        print(f"Requires Admin Approval: {result['requires_admin_approval']}")
        assert result['match_found'] == True, "Should find match"
        assert result['requires_admin_approval'] == False, "Should not require approval for match"
        print("[PASS] Test 1 passed")

        # Test 2: Trading house with new address (proceed with caution)
        print("\n--- Test 2: Trading house with new address ---")
        result = validator.validate_delivery_address(
            "999, New Address, 50000 Kuala Lumpur",
            "300-A001"
        )
        print(f"Customer: {result['customer_id']}")
        print(f"Is Trading House: {result['is_trading_house']}")
        print(f"Match Found: {result['match_found']}")
        print(f"Best Similarity: {result['best_similarity']:.2f}")
        print(f"Validation Level: {result['validation_level']}")
        print(f"Requires Admin Approval: {result['requires_admin_approval']}")
        assert result['match_found'] == False, "Should not find match"
        assert result['is_trading_house'] == True, "Should be trading house"
        assert result['validation_level'] == "trading_house_mismatch", "Should be trading house mismatch"
        assert result['requires_admin_approval'] == True, "Should require admin approval"
        print("[PASS] Test 2 passed")

        # Test 3: Non-trading house with matching address
        print("\n--- Test 3: Non-trading house with matching address ---")
        result = validator.validate_delivery_address(
            "789, Jalan Bangunan, 60000 Kuala Lumpur",
            "300-A002"
        )
        print(f"Customer: {result['customer_id']}")
        print(f"Is Trading House: {result['is_trading_house']}")
        print(f"Match Found: {result['match_found']}")
        print(f"Best Similarity: {result['best_similarity']:.2f}")
        print(f"Validation Level: {result['validation_level']}")
        print(f"Requires Admin Approval: {result['requires_admin_approval']}")
        assert result['match_found'] == True, "Should find match"
        assert result['requires_admin_approval'] == False, "Should not require approval for match"
        print("[PASS] Test 3 passed")

        # Test 4: Non-trading house with new address (HIGH RISK)
        print("\n--- Test 4: Non-trading house with new address (HIGH RISK) ---")
        result = validator.validate_delivery_address(
            "999, Suspicious Address, 50000 Kuala Lumpur",
            "300-A002"
        )
        print(f"Customer: {result['customer_id']}")
        print(f"Is Trading House: {result['is_trading_house']}")
        print(f"Match Found: {result['match_found']}")
        print(f"Best Similarity: {result['best_similarity']:.2f}")
        print(f"Validation Level: {result['validation_level']}")
        print(f"Requires Admin Approval: {result['requires_admin_approval']}")
        assert result['match_found'] == False, "Should not find match"
        assert result['is_trading_house'] == False, "Should not be trading house"
        assert result['validation_level'] == "high_risk_mismatch", "Should be high risk mismatch"
        assert result['requires_admin_approval'] == True, "Should require admin approval"
        print("[PASS] Test 4 passed")

        # Test 5: Address normalization and similarity
        print("\n--- Test 5: Address normalization and similarity ---")
        addr1 = "123, Jalan Industri, 40000 Shah Alam, Selangor"
        addr2 = "123 jalan industri 40000 shah alam selangor"
        normalized1 = validator.normalize_address(addr1)
        normalized2 = validator.normalize_address(addr2)
        print(f"Address 1: {addr1}")
        print(f"Normalized 1: {normalized1}")
        print(f"Address 2: {addr2}")
        print(f"Normalized 2: {normalized2}")
        print(f"Match: {normalized1 == normalized2}")
        similarity = validator.calculate_similarity(addr1, addr2)
        print(f"Similarity: {similarity:.2f}")
        assert normalized1 == normalized2, "Normalization should make addresses match"
        assert similarity == 1.0, "Similarity should be 1.0 for identical addresses"
        print("[PASS] Test 5 passed")

        # Test 6: Partial match with "No." prefix
        print("\n--- Test 6: Partial match with 'No.' prefix ---")
        addr1 = "No. 123, Jalan Industri, 40000 Shah Alam"
        addr2 = "123, Jalan Industri, 40000 Shah Alam"
        similarity = validator.calculate_similarity(addr1, addr2)
        print(f"Address 1: {addr1}")
        print(f"Address 2: {addr2}")
        print(f"Similarity: {similarity:.2f}")
        assert similarity > 0.8, "Should still match with 'No.' prefix removed"
        print("[PASS] Test 6 passed")

        print("\n[PASS] All address validation tests passed")

    finally:
        db.close()
        cleanup_temp_db(temp_db)


def main():
    """Run address validation tests."""
    print("=" * 60)
    print("Testing Address Validation Logic")
    print("=" * 60)

    try:
        test_address_validation()

        print("\n" + "=" * 60)
        print("[PASS] ALL ADDRESS VALIDATION TESTS PASSED")
        print("=" * 60)
        print("\nThe address validation logic is working correctly.")
        print("Trading houses: new addresses flagged for caution")
        print("Non-trading houses: new addresses flagged as high-risk")
        print("Token-overlap similarity scoring prevents false positives")

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
