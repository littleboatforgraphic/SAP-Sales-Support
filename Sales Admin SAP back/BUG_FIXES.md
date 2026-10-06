# Bug Fixes Summary

This document summarizes all critical and moderate bugs fixed in the codebase based on the comprehensive review.

## Critical Bugs Fixed

### 1. Trigger Detection False Positives ✅
**Problem:** Trigger detection had three root causes causing false positives:
- Prefix matching had no word boundary (`normalized.startswith("ai")` matched "Aiman", "aircond", "air")
- Risky keyword guard was a no-op (always returned True)
- Substring matching without word boundaries ("order" matched "border", "do" matched "don't")

**Fix:**
- Implemented word-boundary regex matching for prefixes: `rf"^{re.escape(prefix)}\b"`
- Implemented word-boundary regex matching for keywords: `rf"\b{re.escape(keyword)}\b"`
- Replaced faulty context guard with proper business-context word list check
- Added specific tests for word boundary edge cases

**Files Changed:**
- `trigger.py` - Complete rewrite of detection logic with regex word boundaries

### 2. Webhook Verification Failure ✅
**Problem:** Meta requires `hub.challenge` returned as raw response body, but code returned JSON `{"status": "ok", "challenge": challenge}`. This would cause webhook setup to fail in Meta dashboard.

**Fix:**
- Changed GET endpoint to return `Response(content=challenge, media_type="text/plain")` instead of JSON
- Uses FastAPI Response class for raw string return

**Files Changed:**
- `routers/whatsapp_webhook.py` - Line 158-162

### 3. Inconsistent Datetime Handling ✅
**Problem:** Code mixed `datetime.now(timezone.utc)` (aware) with deprecated `datetime.utcnow()` (naive). Could cause `TypeError` or silent mismatches.

**Fix:**
- Standardized all datetime usage to `datetime.now(timezone.utc)`
- Updated database Column defaults to use lambda: `default=lambda: datetime.now(timezone.utc)`
- Updated all occurrences across codebase

**Files Changed:**
- `database.py` - Lines 96-97
- `routers/whatsapp_webhook.py` - Line 88

### 4. get_monthly_usage No Upper Bound ✅
**Problem:** `get_monthly_usage` only filtered `date >= target_month`, so querying last month returned last month plus everything since.

**Fix:**
- Added month-end calculation using `calendar.monthrange()`
- Added upper bound filter: `UsageLogEntry.date <= month_end`
- Now correctly returns only the target month's data

**Files Changed:**
- `usage_tracker.py` - Lines 125-148

### 5. Address Validation in Test File ✅
**Problem:** `validate_delivery_address` was defined in test file, not used by production code. `AddressValidationResult` table was never written to. Exact string matching was brittle (failed on "No. 123" vs "123").

**Fix:**
- Created production module `address_validator.py` with proper AddressValidator class
- Implemented token-overlap similarity scoring (Jaccard similarity) instead of exact match
- Added similarity threshold (80%) for matching
- AddressValidator now writes to AddressValidationResult table
- Updated test to use production module

**Files Changed:**
- `address_validator.py` - NEW FILE (142 lines)
- `test_address_validation.py` - Updated to use production module

### 6. Two Independent DB Engines ✅
**Problem:** `main.py` and `routers/whatsapp_webhook.py` each created their own engine against same SQLite file. Locking hazard under concurrent writes.

**Fix:**
- Implemented global engine and session factory in `database.py`
- Added `get_db_engine()` and `get_db_session_factory()` functions
- All modules now use shared engine via these accessors
- Removed local engine creation from main.py and router

**Files Changed:**
- `database.py` - Lines 215-250 (global engine/session factory)
- `main.py` - Lines 15-22 (use shared engine)
- `routers/whatsapp_webhook.py` - Lines 17-20 (use shared session factory)

### 7. No Webhook Signature Verification ✅
**Problem:** POST endpoint accepted any JSON without validating `X-Hub-Signature-256`. Anyone discovering URL could inject fake messages.

**Fix:**
- Added `whatsapp_app_secret` to config
- Implemented HMAC-SHA256 signature verification in POST endpoint
- Uses `hmac.compare_digest()` for constant-time comparison
- Gracefully skips verification if app secret not configured (dev mode)
- Added proper Header import and signature extraction

**Files Changed:**
- `config.py` - Line 25 (added whatsapp_app_secret)
- `routers/whatsapp_webhook.py` - Lines 1-9 (imports), 42-71 (verification function), 214-264 (POST endpoint with verification)

### 8. check_budget In-Band Cost Alerts ✅
**Problem:** `check_budget` returned `(True, "Cost alert...")` making it impossible to distinguish "passed" from "passing but over threshold" without string parsing.

**Fix:**
- Created `BudgetStatus` enum with values: `PASSED`, `EXCEEDED`, `COST_ALERT`
- Changed return type from `tuple[bool, str]` to `tuple[BudgetStatus, str]`
- Updated all callers to use enum comparison

**Files Changed:**
- `usage_tracker.py` - Lines 1-14 (enum), 72-108 (updated check_budget)
- `test_core_modules.py` - Line 143 (updated test to use enum)

### 9. Tests Mutate Shared Dev Database ✅
**Problem:** Test scripts wrote real rows into `usage_log` and `audit_log` in `sales_admin_sap.db`. Running tests repeatedly would cause `check_budget` to fail.

**Fix:**
- Implemented `get_temp_db()` function using `tempfile.NamedTemporaryFile`
- Implemented `cleanup_temp_db()` function for cleanup
- Updated all test functions to use temp database
- Tests now create isolated databases that are cleaned up after each test

**Files Changed:**
- `test_core_modules.py` - Lines 1-66 (temp DB helpers), all test functions updated
- `test_address_validation.py` - Lines 1-40 (temp DB helpers), cleanup

## Moderate Issues Fixed

### 10. CORS Invalid Combination ✅
**Problem:** `allow_origins=["*"]` combined with `allow_credentials=True` is invalid per CORS spec.

**Fix:**
- Changed `allow_credentials=False` when using wildcard origins
- Added comment explaining configuration requirement

**Files Changed:**
- `main.py` - Lines 52-56

### 11. Duplicate Glossary Entry ✅
**Problem:** `glossary.py` had duplicate "kg" entry mapping to both "KG" and "KILOGRAM". Second entry was silently skipped.

**Fix:**
- Changed second entry from "kg" to "kilogram" to map to "KILOGRAM"
- Now both mappings are distinct and functional

**Files Changed:**
- `glossary.py` - Line 152

### 12. Optional API Key for Dev ✅
**Problem:** `config.py` required `ILMU_API_KEY` just to boot, creating friction for webhook-only dev runs.

**Fix:**
- Changed `ilmu_api_key: str` to `ilmu_api_key: str = ""`
- Added comment explaining it's optional for webhook-only dev

**Files Changed:**
- `config.py` - Line 17

### 13. Environment Variable Updates ✅
**Problem:** Environment files still referenced old Anthropic config and missing new webhook app secret.

**Fix:**
- Updated `.env` and `.env.example` with Ilmu Claw variables
- Added `WHATSAPP_APP_SECRET` for signature verification
- Removed obsolete `WHATSAPP_BUSINESS_ACCOUNT_ID`

**Files Changed:**
- `.env` - Lines 11-14
- `.env.example` - Lines 11-14

## Summary

All 13 critical and moderate issues have been fixed:

✅ Trigger detection false positives (word boundaries)
✅ Webhook verification (raw challenge)
✅ Datetime handling (timezone-aware)
✅ get_monthly_usage upper bound
✅ Address validation (production module + similarity scoring)
✅ Shared DB engine
✅ Webhook signature verification
✅ check_budget status enum
✅ Tests use temp database
✅ CORS invalid combination
✅ Duplicate glossary entry
✅ Optional API key for dev
✅ Environment variable updates

The codebase is now production-ready for the foundation infrastructure with proper security, reliability, and development workflow.
