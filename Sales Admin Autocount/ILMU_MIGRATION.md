# Ilmu Claw Migration Summary

## Changes Made to Switch from Anthropic to Ilmu Claw

### 1. Configuration Files Updated

**`config.py`**
- Changed from `anthropic_api_key` to `ilmu_api_key`
- Added `ilmu_base_url` (default: https://api.ilmu.ai/v1)
- Added `ilmu_model` (default: ilmu-mini-v3.3)

**`.env` and `.env.example`**
- Replaced `ANTHROPIC_API_KEY` with `ILMU_API_KEY`
- Added `ILMU_BASE_URL=https://api.ilmu.ai/v1`
- Added `ILMU_MODEL=ilmu-mini-v3.3`

### 2. Dependencies Updated

**`requirements.txt`**
- Removed: `anthropic>=0.39.0`
- Added: `openai>=1.0.0`
- Installed: `openai==3.24.0`

### 3. Code Modules Updated

**`usage_tracker.py`**
- Changed import from `anthropic` to `openai`
- Updated `_calculate_cost()` method with placeholder pricing for Ilmu Claw
  - INPUT_PRICE_PER_M: 0.15 USD (placeholder - UPDATE WITH ACTUAL PRICING)
  - OUTPUT_PRICE_PER_M: 0.60 USD (placeholder - UPDATE WITH ACTUAL PRICING)
- Updated comment from "Anthropic's pricing" to "Ilmu Claw's pricing"

**NEW: `llm_client.py`**
- Created new LLM client wrapper for Ilmu Claw API
- Uses OpenAI SDK with Ilmu Claw's base URL
- Provides simple interface:
  - `chat_completion()` - basic chat requests
  - `extract_text_from_pdf()` - PDF extraction (placeholder, check Ilmu Claw docs)
  - `draft_message()` - message drafting
- Global `get_llm_client()` function for easy access

### 4. Documentation Updated

**`05-Technical-Specification.md`**
- Updated technology stack table
- Changed LLM from "Anthropic API" to "Ilmu Claw API (OpenAI-compatible)"
- Changed SDK from `anthropic` to `openai`
- Added `llm_client.py` to module structure
- Updated environment configuration section with Ilmu Claw variables
- Added open technical questions about Ilmu Claw pricing and PDF capabilities

**`04-Software-Architecture-Document.md`**
- Updated LLM calls reference from "Anthropic API" to "Ilmu Claw API"
- Updated credential handling from "Anthropic API key" to "Ilmu Claw API key"

**`TESTING_GUIDE.md`**
- Updated references from "Anthropic API" to "Ilmu Claw API"

**`README.md`**
- Updated environment variable reference from `ANTHROPIC_API_KEY` to `ILMU_API_KEY`

### 5. New Test Script

**`test_ilmu_integration.py`**
- Created test script to verify Ilmu Claw API integration
- Tests basic chat completion
- Tests message drafting
- Validates API key configuration
- Shows token usage and cost

## What You Need to Do

### 1. Set Your Ilmu Claw API Key

Edit the `.env` file and set your actual API key:

```bash
ILMU_API_KEY=your_actual_ilmu_api_key_here
```

### 2. Update Pricing (Important)

The pricing in `usage_tracker.py` is currently set to placeholder values:

```python
INPUT_PRICE_PER_M = 0.15  # USD per million input tokens
OUTPUT_PRICE_PER_M = 0.60  # USD per million output tokens
```

**You need to update these with the actual Ilmu Claw pricing for the `ilmu-mini-v3.3` model.**

Check Ilmu Claw's documentation or pricing page and update:
- Line 55 in `usage_tracker.py`
- Line 66 in `llm_client.py`

### 3. Test the Integration

Run the Ilmu Claw integration test:

```bash
python test_ilmu_integration.py
```

This will:
- Verify your API key is correct
- Test a basic API call
- Test message drafting
- Show token usage and cost

### 4. Verify PDF Processing

The `llm_client.py` includes a placeholder for PDF extraction. You need to check:

1. Does Ilmu Claw support file uploads directly?
2. If yes, update `extract_text_from_pdf()` to use file upload
3. If no, you may need to:
   - Convert PDF to text first using a library like `PyPDF2` or `pdfplumber`
   - Then send the text to Ilmu Claw for extraction

Check Ilmu Claw's documentation for their file upload capabilities.

## Important Notes

### Pricing Configuration

The current pricing values are placeholders. **Ilmu Claw's actual pricing may be different.** 

To get accurate cost tracking:
1. Find Ilmu Claw's pricing for `ilmu-mini-v3.3`
2. Update `INPUT_PRICE_PER_M` and `OUTPUT_PRICE_PER_M` in:
   - `usage_tracker.py` (line 55-56)
   - `llm_client.py` (line 66-67)

### PDF Processing

The PDF extraction logic in `llm_client.py` is a placeholder. Depending on Ilmu Claw's capabilities, you may need to:

**Option A: If Ilmu Claw supports file uploads:**
```python
response = self.client.chat.completions.create(
    model=self.model,
    messages=messages,
    files=[{"file": pdf_content, "filename": "document.pdf"}]
)
```

**Option B: If Ilmu Claw does not support file uploads:**
```python
# Convert PDF to text first
import PyPDF2
pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
text = "\n".join(page.extract_text() for page in pdf_reader.pages)

# Then send text to Ilmu Claw
messages.append({"role": "user", "content": f"Document text:\n\n{text}"})
```

### API Compatibility

Ilmu Claw uses the OpenAI-compatible API format, which means:
- The code uses the standard `openai` Python SDK
- The base URL is changed to `https://api.ilmu.ai/v1`
- The model name is `ilmu-mini-v3.3`
- All other OpenAI parameters should work as expected

## Testing Your Setup

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Set API Key
Edit `.env`:
```bash
ILMU_API_KEY=your_actual_api_key
```

### Step 3: Test Integration
```bash
python test_ilmu_integration.py
```

### Step 4: Update Pricing
Edit `usage_tracker.py` and `llm_client.py` with actual Ilmu Claw pricing.

### Step 5: Test PDF Processing (if needed)
Test PDF extraction with real documents once you confirm Ilmu Claw's capabilities.

## Summary

✅ **Configuration updated** - All config files now use Ilmu Claw
✅ **Dependencies updated** - Switched from anthropic to openai
✅ **Code updated** - Created LLM client wrapper for Ilmu Claw
✅ **Documentation updated** - All docs reference Ilmu Claw
✅ **Test script created** - Ready to verify your API key

⚠️ **Action required** - You need to:
1. Set your actual Ilmu Claw API key in `.env`
2. Update pricing values with actual Ilmu Claw pricing
3. Verify PDF processing capabilities for Ilmu Claw

The code is now ready to use Ilmu Claw API!
