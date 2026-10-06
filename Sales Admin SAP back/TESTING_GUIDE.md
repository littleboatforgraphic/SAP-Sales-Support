# Testing Guide

This guide explains how to test the AI Agent System without real SAP, WhatsApp, or Ilmu Claw API access.

## Overview

Since you don't have the actual API keys and SAP connection details yet, I've created **mock implementations** that simulate the real systems. This allows you to:

- Test all core modules independently
- Verify the address validation logic (new fraud prevention feature)
- Test the entire workflow end-to-end
- Debug and refine the code before real integration

## Mock Components

### 1. Mock SAP Client (`mock_sap_client.py`)

Simulates SAP responses with sample data:
- **Customers**: 3 sample customers (2 trading houses, 1 non-trading house)
- **Stock**: Mock stock levels for wire mesh products
- **Operations**: Simulates creating sales orders, invoices, delivery orders

**Sample Data:**
- `CUST001`: ABC Trading Sdn Bhd (Trading House) - 2 registered addresses
- `CUST002`: XYZ Construction Sdn Bhd (Non-trading house) - 1 registered address
- `CUST003`: BuildWell Contractors (Non-trading house) - 1 registered address

### 2. Mock Email Monitor (`mock_email_monitor.py`)

Simulates receiving PO emails:
- Returns 2 sample PO emails
- Simulates sender allowlist checking
- Simulates PO keyword detection

### 3. Test Scripts

#### `test_core_modules.py`

Tests all foundation infrastructure modules:
- ✓ Glossary lookup and term resolution
- ✓ SKU fuzzy matching
- ✓ Price table lookup
- ✓ Trigger detection (explicit prefix and keyword fallback)
- ✓ Usage tracking and budget enforcement
- ✓ Audit logging
- ✓ Mock SAP client operations
- ✓ Mock email monitor operations

**Run it:**
```bash
python test_core_modules.py
```

#### `test_address_validation.py`

Tests the new address validation logic for fraud prevention:
- ✓ Trading house with matching address (no approval needed)
- ✓ Trading house with new address (flagged for caution)
- ✓ Non-trading house with matching address (no approval needed)
- ✓ Non-trading house with new address (flagged as HIGH RISK)
- ✓ Address normalization (punctuation/case handling)

**Run it:**
```bash
python test_address_validation.py
```

## Running Tests

### Prerequisites

Make sure you have:
1. Installed dependencies: `pip install -r requirements.txt`
2. Initialized the database: `python init_db.py`
3. Seeded the data: `python seed_data.py`

### Run All Tests

```bash
# Test core modules
python test_core_modules.py

# Test address validation (new feature)
python test_address_validation.py
```

### Expected Output

Both test scripts should show:
```
[PASS] ALL TESTS PASSED
```

If any test fails, it will show:
```
[FAIL] TEST FAILED: <error message>
```

## What You Can Test Now

### Without Real APIs

You can test:

1. **Glossary Module**
   - Term lookup and resolution
   - Shortform to canonical value mapping
   - Pending/approved entry management

2. **SKU Index Module**
   - Fuzzy matching of product descriptions
   - Exact SKU lookup
   - Mock SAP sync

3. **Price Table Module**
   - Current price lookup
   - Historical price queries
   - Price updates (admin-only)

4. **Trigger Detection**
   - Explicit prefix detection (AI:, Agent:)
   - Keyword fallback detection
   - False positive prevention

5. **Usage Tracker**
   - Token usage recording
   - Budget enforcement
   - Daily/monthly usage reports

6. **Audit Logging**
   - Price used logging
   - Document sent logging
   - Audit trail retrieval

7. **Address Validation** (NEW)
   - Trading house address validation
   - Non-trading house high-risk detection
   - Address normalization
   - Fraud prevention logic

8. **Mock SAP Operations**
   - Stock lookup
   - Customer details retrieval
   - Trading house classification
   - Address retrieval
   - Sales order/invoice/DO creation

9. **Mock Email Monitoring**
   - Email connection
   - PO detection
   - Attachment extraction
   - Sender allowlist checking

### What Requires Real APIs

These features need real integration to test end-to-end:

1. **WhatsApp Integration**
   - Real webhook handling from Meta Cloud API
   - Actual message sending via WhatsApp
   - Coexistence with admin's WhatsApp Business app

2. **Real SAP Integration**
   - Actual OData or RFC/BAPI calls
   - Real customer master data
   - Real stock levels
   - Real document generation

3. **LLM Integration**
   - Actual Ilmu Claw API calls
   - PDF extraction from real documents
   - Message drafting with real AI

4. **Real Email Integration**
   - Actual IMAP/POP3 connection
   - Real email polling
   - Real attachment processing

## Next Steps for Testing

### Phase 1: Foundation Testing (Now)
✅ Complete - All core modules tested with mocks

### Phase 2: Agent Logic Testing (Recommended)

Build the agents using mock clients:

1. **Stock & Quote Agent**
   - Use `mock_sap_client` for stock lookup
   - Use `price_table` for price retrieval
   - Test quote generation logic

2. **Order-to-Invoice Agent**
   - Use `mock_sap_client` for customer data
   - Use `address_validator` for address validation
   - Test PO processing logic
   - Test non-PO order flow

3. **Shipment Agent**
   - Use `mock_sap_client` for pick/pack status
   - Test delivery order generation

### Phase 3: Real Integration (When APIs Available)

When you have:
- SAP connection details
- WhatsApp Business API access
- Ilmu Claw API key
- Email IMAP credentials

Then:
1. Replace mock clients with real implementations
2. Test with real data
3. Validate against actual SAP records
4. Test with real WhatsApp messages
5. Test with real email POs

## Adding New Test Cases

To add a new test:

1. Create a test function in `test_core_modules.py` or a new test file
2. Use the mock clients (`MockSAPClient`, `MockEmailMonitor`)
3. Add the test to the `main()` function
4. Run the test script

Example:
```python
def test_my_new_feature():
    """Test my new feature."""
    print("\n=== Testing My New Feature ===")
    sap_client = MockSAPClient()

    # Your test logic here
    result = do_something(sap_client)
    assert result == expected, "Test failed"

    print("[PASS] My new feature test passed")
```

## Troubleshooting

### Database Errors

If you get database errors:
```bash
# Reinitialize database
python init_db.py

# Reseed data
python seed_data.py
```

### Import Errors

If you get import errors:
```bash
# Make sure you're in the project directory
cd "D:\Work\Alpha Technologies Sdn Bhd\Devin\Sales Admin SAP"

# Check Python path
python -c "import sys; print(sys.path)"
```

### Unicode Errors

If you get Unicode encoding errors (Windows):
- The test scripts already use ASCII-safe characters
- If you modify tests, avoid using special characters like ✓, ✗

## Summary

You now have a complete testing framework that allows you to:
- ✅ Test all core modules without real APIs
- ✅ Verify the new address validation logic
- ✅ Build and test agents using mock data
- ✅ Debug and refine code before real integration

The tests confirm that the foundation infrastructure is working correctly and ready for agent development.
