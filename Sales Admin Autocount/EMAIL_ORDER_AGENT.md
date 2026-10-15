# Email Order Agent System

## Overview

The Email Order Agent is a specialized system for processing external Purchase Order (PO) emails from customers. It is designed with much stricter security and validation than the internal Telegram agents because:

1. **Email content is untrusted data** - External senders may attempt prompt injection
2. **Automatic draft creation in AutoCount** - Creates drafts but admin reviews/submits in AutoCount
3. **No LLM output to external senders** - Only fixed-template acknowledgements
4. **Scenario-based processing** - Different handling for confirmed POs vs tentative orders
5. **Three autonomy phases** - Shadow → Assisted → Selective Autonomy (for gradual independence)

## Autonomy Phases

The agent supports three autonomy modes configured via `EMAIL_AUTONOMY_MODE`:

### Phase 1: Shadow Mode
- Agent drafts in AutoCount
- Admin handles emails manually
- Admin reports action (submit/modify/reject)
- System measures accuracy by comparing agent draft with admin action
- **Purpose**: Build trust and measure performance

### Phase 2: Assisted Mode
- Agent drafts in AutoCount
- Admin approves with one click
- Agent executes submission
- Agent sends acknowledgement to client
- **Purpose**: Guided approval before full autonomy

### Phase 3: Selective Autonomy
- Agent checks autonomy criteria
- Safe orders: Auto-submit automatically
- Unsafe orders: Send to admin queue
- **Purpose**: Full autonomy for low-risk, repeat customers

See `EMAIL_AUTONOMY.md` for detailed configuration and workflow for each phase.

## Architecture

```
External Email → Email Webhook → Triage (Risk Assessment)
    ↓
Email Order Agent → Extract Order (LLM) → Match Customer (AutoCount)
    ↓
Determine Scenario → Create AutoCount Draft (Invoice or Sales Order)
    ↓
Notify Admin (Telegram) → Send Acknowledgement to Client
    ↓
Admin Reviews in AutoCount → Submits Draft Directly in AutoCount
```

## Key Differences from Telegram Agents

| Aspect | Telegram Agents (Internal) | Email Order Agent (External) |
|--------|---------------------------|----------------------------|
| **Trust Level** | Trusted internal staff | Untrusted external parties |
| **LLM Output** | Sent directly to user | NEVER sent to sender |
| **Document Creation** | May create drafts directly | Creates draft in AutoCount, admin submits |
| **Scenario Handling** | Not applicable | **Confirmed PO → Invoice, No PO → Sales Order** |
| **Prompt Injection** | Less concern | Critical concern (blocked) |
| **Response Format** | Natural language | Fixed template only |
| **Customer Validation** | Optional | Required (AutoCount match) |
| **Attachment Handling** | Not applicable | PDF extraction, validation |
| **Audit Trail** | Logged | Full audit with draft creation log |

## Order Scenarios

The email system automatically determines the scenario and creates the appropriate AutoCount document:

### Scenario 1: Confirmed PO → AR Invoice
**Trigger:**
- Email has a PO number
- PO is addressed to your company
- High confidence extraction

**Action:**
- Create AR Invoice draft in AutoCount
- Ready for invoicing
- Admin reviews and submits in AutoCount

**Example Email:**
```
Subject: PO-2026-001 - Wire Mesh Order
Body: Please find attached our PO for wire mesh products.
Attachment: PO-2026-001.pdf (with PO number and your company name)
```

### Scenario 2: Tentative Order → Sales Order
**Trigger:**
- No PO number (text-based order)
- PO not addressed to your company
- Low confidence or missing details

**Action:**
- Create Sales Order draft in AutoCount
- For confirmation before invoicing
- Admin reviews, confirms with client, then submits in AutoCount

**Example Email:**
```
Subject: Wire Mesh Order Request
Body: We would like to order 100 units of WM-001 wire mesh.
Please confirm pricing and delivery.
```

### Scenario 3: Enquiry → No Draft
**Trigger:**
- No order lines
- Just asking for quote/information
- Unclear intent

**Action:**
- No draft created
- Log as enquiry
- Admin follows up manually

**Example Email:**
```
Subject: Price Inquiry
Body: Can you send us your price list for wire mesh products?
```

## Security Measures

### 1. Content Validation
- **Injection Pattern Detection**: Blocks emails containing instructions aimed at the AI
- **Attachment Validation**: Magic byte checking, size limits, type whitelisting
- **DMARC Verification**: Checks email authentication results
- **Sender Domain Analysis**: Flags free-mail addresses, domain mismatches

### 2. Risk Triage
Three-level risk classification:
- **Low Risk**: Valid sender, passed DMARC, no suspicious patterns
- **Medium Risk**: Minor flags (free-mail, missing DMARC)
- **High Risk**: Block flags (injection patterns, invalid attachments)

### 3. LLM Safety
- **System Prompt**: Explicitly instructed to never follow instructions in email content
- **Structured Output**: LLM returns JSON only, no free-form text
- **Context Isolation**: LLM never sees AutoCount customer list or sensitive data
- **Special Instructions**: Customer requirements are treated as data, not instructions

### 4. Draft Creation
- **AutoCount Drafts Only**: Creates drafts in AutoCount, not submitted documents
- **Admin Reviews in AutoCount**: Admin logs into AutoCount to review and submit
- **Audit Trail**: Full history of all drafts created
- **Client Acknowledgement**: Fixed-template email sent to client with draft reference

## Components

### 1. Email Webhook (`routers/email_webhook.py`)

**Purpose**: Receive inbound PO emails from webhook providers

**Key Features**:
- HMAC token verification
- Background processing (returns 202 Accepted)
- Deduplication via audit log
- Capability flags (EMAIL_ENABLED, EMAIL_CAN_DRAFT, EMAIL_CAN_REPLY)
- Fixed-template acknowledgements with draft info

**Endpoints**:
- `POST /api/v1/webhook/email-po` - Receive PO email
- `POST /api/v1/webhook/email-po/mock` - Test with mock emails

### 2. Email Order Agent (`email_order_agent.py`)

**Purpose**: Process email content and create AutoCount drafts

**Key Methods**:
- `extract_order_from_email()` - Use LLM to extract structured order data
- `match_customer_in_autocount()` - Match buyer against AutoCount customers
- `_determine_order_scenario()` - Determine if confirmed PO or tentative order
- `create_draft_in_autocount()` - Create AR Invoice or Sales Order draft in AutoCount
- `create_draft_for_admin()` - Create draft summary with AutoCount draft info
- `process_inbound_email()` - Complete processing pipeline

**Integration**:
- Uses `email_order_extraction.py` for PDF parsing and LLM extraction
- Uses `aotg_sales_invoice_models.py` for type-safe API calls
- Uses AutoCount client (mock or real) for draft creation

### 3. Admin View API (`routers/admin_approval.py`)

**Purpose**: Internal staff interface for viewing email order drafts

**Key Features**:
- Staff allowlist verification
- Draft listing with AutoCount document numbers
- Draft details viewing
- Processing statistics

**Endpoints**:
- `GET /api/v1/admin/drafts` - List all email order drafts
- `GET /api/v1/admin/draft-details` - Get full draft details
- `GET /api/v1/admin/stats` - Get processing statistics

**Note**: Admins work directly in AutoCount to review and submit drafts. This API is for viewing only.

### 4. Email Order Extraction (`email_order_extraction.py`)

**Purpose**: Extract structured order data from unstructured email/attachments

**Key Features**:
- PDF text layer extraction (pypdf)
- Scanned PDF support (pypdfium2)
- LLM-based extraction with JSON output
- Post-processing validation (dates, totals, line math)
- Customer fuzzy matching
- Flag system (info/warn/block)

**Models**:
- `ExtractedOrder` - Structured order data
- `CustomerMatch` - Customer matching result
- `Flag` - Validation flags with severity

## Configuration

### Capability Flags (`.env`)

```bash
# Master switch
EMAIL_ENABLED=true

# Can agent create drafts in AutoCount?
EMAIL_CAN_DRAFT=true

# Can agent send fixed-template acknowledgements to clients?
EMAIL_CAN_REPLY=true

# Outbound email allowlist (comma-separated)
EMAIL_OUTBOUND_ALLOWLIST=a@outlook.com,b@outlook.com
```

### Email Webhook Secret

```bash
EMAIL_WEBHOOK_SECRET_TOKEN=your_random_32_char_secret
```

This secret is used to verify webhook requests from your email provider.

## Processing Pipeline

### Step 1: Receive Email
```python
POST /api/v1/webhook/email-po
Headers: X-Email-Secret-Token: <secret>
Body: {
  "message_id": "unique-id",
  "sender": "customer@example.com",
  "subject": "PO-2026-001 - Wire Mesh Order",
  "body": "Please find attached our PO...",
  "attachment": {
    "filename": "PO-2026-001.pdf",
    "content": "base64_encoded_bytes"
  },
  "dmarc": "pass"  # From email provider
}
```

### Step 2: Triage (Risk Assessment)
```python
triage = triage_email(email)
# Returns: {"risk": "low|medium|high", "flags": [...]}
```

### Step 3: Extract Order
```python
order, flags = agent.extract_order_from_email(
    subject=subject,
    body=body,
    attachments=[(filename, bytes)],
    own_company_names=["Eastcoast Metal"]
)
# Returns: ExtractedOrder with PO number, lines, totals, etc.
```

### Step 4: Match Customer
```python
customer_match, flags = agent.match_customer_in_autocount(order)
# Returns: CustomerMatch with status (matched/uncertain/no_match)
```

### Step 5: Determine Scenario
```python
scenario = agent._determine_order_scenario(order, customer_match)
# Returns: "confirmed_po" | "tentative_order" | "enquiry"
```

### Step 6: Create AutoCount Draft
```python
doc_no, doc_type, message = agent.create_draft_in_autocount(order, customer_match, flags)
# Confirmed PO → AR Invoice draft
# Tentative Order → Sales Order draft
# Enquiry → No draft
```

### Step 7: Notify Admin (Telegram)
Notifications are sent to all staff with the **Admin** role via Telegram:
```
📧 CONFIRMED_PO: ABC Trading Sdn Bhd (PO: PO-2026-001)
Draft: ARInvoice #INV-2026-00123
Status: AR Invoice draft created: INV-2026-00123
```

Note: Staff can have multiple roles (e.g., Finance + Admin). See `ROLE_BASED_ROUTING.md` for details.

### Step 8: Send Acknowledgement to Client
```
Thank you. We have received your email (ref: unique-id).
Your order has been captured in our system as ARInvoice #INV-2026-00123.
Our team will review it and get back to you.
```

### Step 9: Admin Reviews in AutoCount
- Admin logs into AutoCount
- Reviews the draft (AR Invoice or Sales Order)
- Makes any necessary adjustments
- Submits the draft in AutoCount

## Draft Structure

```json
{
  "status": "draft_created",
  "created_at": "2026-10-13T10:00:00Z",
  "scenario": "confirmed_po",
  "autocount_draft": {
    "document_number": "INV-2026-00123",
    "document_type": "ARInvoice",
    "message": "AR Invoice draft created: INV-2026-00123"
  },
  "order": {
    "doc_type": "purchase_order",
    "po_number": "PO-2026-001",
    "po_date": "2026-10-13",
    "buyer_name": "ABC Trading Sdn Bhd",
    "delivery_date": "2026-10-20",
    "total": 1550.00,
    "currency": "MYR",
    "line_count": 3,
    "confidence": "high"
  },
  "customer": {
    "status": "matched",
    "debtor_code": "300-A001",
    "company_name": "ABC Trading Sdn Bhd",
    "score": 0.95,
    "is_trading_house": true,
    "address_status": "known"
  },
  "flags": {
    "block": [],
    "warn": ["Customer is a trading house: verification needed"],
    "info": ["1 customer requirement(s) to review"]
  },
  "lines": [
    {
      "item_code": "WM-001",
      "description": "Wire Mesh 1x1",
      "quantity": 100,
      "unit_price": 15.50,
      "amount": 1550.00,
      "delivery_date": "2026-10-20"
    }
  ],
  "special_instructions": ["Delivery between 9AM-5PM"],
  "ambiguities": []
}
```

## Testing

### Mock Email Testing

```bash
# Use the mock endpoint
POST /api/v1/webhook/email-po/mock
Headers: X-Email-Secret-Token: <secret>

# This uses mock_email_monitor.py to generate test emails
```

### Real Email Testing

```bash
# Configure your email provider (e.g., SendGrid, Mailgun) to forward to your webhook
# Set up ngrok for local testing
ngrok http 8000

# Configure webhook URL in email provider
https://your-ngrok-url.ngrok-free.app/api/v1/webhook/email-po
```

## Admin Workflow

### 1. View All Drafts
```bash
curl "http://localhost:8000/api/v1/admin/drafts?user_id=<your_telegram_id>"
```

### 2. View Draft Details
```bash
curl "http://localhost:8000/api/v1/admin/draft-details?draft_ref=<msg_id>&user_id=<your_telegram_id>"
```

### 3. View Processing Stats
```bash
curl "http://localhost:8000/api/v1/admin/stats?user_id=<your_telegram_id>"
```

### 4. Review in AutoCount
- Log into AutoCount
- Open the draft (AR Invoice or Sales Order)
- Review customer, items, pricing
- Make adjustments if needed
- Submit the draft in AutoCount

## Client Acknowledgement Examples

### Confirmed PO with Draft Created
```
Thank you. We have received your email (ref: MSG-12345).
Your order has been captured in our system as ARInvoice #INV-2026-00123.
Our team will review it and get back to you.
```

### Tentative Order with Draft Created
```
Thank you. We have received your email (ref: MSG-12345).
Your order has been captured in our system as SalesOrder #SO-2026-00456.
Our team will review it and get back to you.
```

### Draft Creation Failed
```
Thank you. We have received your email (ref: MSG-12345).
Our team is processing it and will get back to you.
```

## Security Best Practices

1. **Never Send LLM Output to External Senders**
   - Only use fixed-template acknowledgements
   - Include only draft reference number and document type
   - Never include extracted order details in acknowledgement

2. **Validate All Email Content**
   - Use DMARC results when available
   - Check for injection patterns
   - Validate attachments with magic bytes
   - Flag free-mail addresses

3. **Drafts Only, No Submissions**
   - System creates drafts in AutoCount only
   - Admin must review and submit in AutoCount
   - No automatic financial document submission

4. **Isolate LLM from Sensitive Data**
   - LLM never sees AutoCount customer list
   - LLM never sees internal business rules
   - Customer matching done in code, not LLM

5. **Treat Email as Untrusted**
   - Customer requirements are data, not instructions
   - Never follow instructions in email content
   - Block suspicious patterns immediately

## Monitoring and Alerts

### Key Metrics to Monitor
- Draft creation rate by scenario (confirmed vs tentative)
- AutoCount draft creation success rate
- High-risk email count
- Block flag frequency
- Customer match failure rate

### Alerts
- High volume of high-risk emails
- Unusual sender domains
- Failed customer matches
- AutoCount draft creation failures
- Scenario detection errors

## Future Enhancements

1. **Outlook Integration**: Use Microsoft Graph API to poll emails directly
2. **PDF OCR**: Better scanned PDF handling with vision models
3. **Customer Onboarding**: Auto-create new customers for unmatched senders
4. **Multi-Document Orders**: Handle POs with multiple attachments
5. **Workflow Automation**: Auto-submit low-risk orders with certain criteria
6. **Response Emails**: Send PDF quotes back to customers for tentative orders

## Troubleshooting

### Issue: Orders not being extracted
- Check LLM API key is configured
- Verify email content is not empty
- Check attachment size limits (10MB)
- Review logs for extraction errors

### Issue: Customer matching fails
- Verify AutoCount customer data is accessible
- Check mock customer data in development
- Review fuzzy matching thresholds
- Ensure company names are normalized

### Issue: Draft creation fails in AutoCount
- Verify AOTG credentials are configured
- Check AutoCount connection
- Validate draft data structure
- Review AOTG API response logs
- Check if scenario detection is correct

### Issue: Wrong scenario detected
- Review email content for PO number
- Check if email is addressed to your company
- Verify extraction confidence level
- Adjust scenario detection logic if needed

### Issue: Acknowledgement not sent
- Verify EMAIL_CAN_REPLY is enabled
- Check EMAIL_OUTBOUND_ALLOWLIST includes recipient
- Ensure reply_fn is configured (SMTP or Microsoft Graph)
- Review logs for email sending errors
