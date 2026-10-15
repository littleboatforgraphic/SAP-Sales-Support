# Email PO Processing Testing Guide

This guide shows you how to test the Purchase Order (PO) email processing using the Order-to-Invoice Agent.

## Architecture

The email PO processing system:

1. **Email webhook** receives PO emails (via webhook or mock polling)
2. **Validates sender** against PO allowlist
3. **Routes to Order-to-Invoice Agent** for processing
4. **Agent processes** using LLM with customer data context
5. **Logs to audit trail** for tracking

## Setup Steps

### Step 1: Add Email Configuration

Add email configuration for PO processing:

```bash
python setup_test_deployment.py --add-email-config
```

This adds:
- Mock email server settings
- PO keywords for detection
- **No sender allowlist** - accepts all PO emails from any sender

### Step 2: Configure Email Webhook Secret

Add to your `.env` file:

```bash
EMAIL_WEBHOOK_SECRET_TOKEN=random_secret_32_chars_here
```

### Step 3: Start the Server

```bash
python main.py
```

## Testing Methods

### Method 1: Mock Email Test (Recommended for Development)

Use the mock endpoint to test without a real email server:

```bash
python test_email_po.py
```

This will:
- Use `mock_email_monitor.py` to simulate incoming PO emails
- Process 2 sample PO emails
- Route to Order-to-Invoice Agent
- Return agent responses

**Expected Output:**
```
Testing Email PO Processing with Mock Data
============================================================
Status Code: 200

Response:
{
  "status": "success",
  "processed_count": 2,
  "results": [
    {
      "email_id": "001",
      "sender": "customer1@example.com",
      "subject": "PO-2026-001 - Wire Mesh Order",
      "agent_response": "300-A001: ABC Trading Sdn Bhd - Contact: Mr Tan...",
      "status": "processed"
    },
    ...
  ]
}

✅ Successfully processed 2 PO emails
```

### Method 2: Real Email Webhook Test

For production testing with a real email service:

**Endpoint:** `POST /api/v1/webhook/email-po`

**Headers:**
```
Content-Type: application/json
X-Email-Secret-Token: your_secret_token
```

**Payload:**
```json
{
  "sender": "customer1@example.com",
  "subject": "PO-2026-001 - Wire Mesh Order",
  "body": "Please find attached our purchase order for wire mesh products.",
  "attachment": {
    "filename": "PO-2026-001.pdf",
    "content": "base64_encoded_pdf_content_here"
  },
  "received_at": "2026-10-12T10:00:00Z"
}
```

**Test with curl:**
```bash
curl -X POST http://localhost:8000/api/v1/webhook/email-po \
  -H "Content-Type: application/json" \
  -H "X-Email-Secret-Token: your_secret_token" \
  -d '{
    "sender": "customer1@example.com",
    "subject": "PO-2026-001 - Wire Mesh Order",
    "body": "PO for wire mesh products",
    "attachment": {
      "filename": "PO-2026-001.pdf",
      "content": "mock_content"
    },
    "received_at": "2026-10-12T10:00:00Z"
  }'
```

## How It Works

### 1. Email Reception

**Mock mode:**
- `mock_email_monitor.py` provides sample PO emails
- 2 mock emails with different senders and subjects

**Real mode:**
- Email server forwards emails to webhook
- External service (e.g., SendGrid, Mailgun) triggers webhook

### 2. Validation

**PO keyword detection:**
- Checks subject for PO keywords: "PO", "Purchase Order", "Order"
- Skips emails without PO keywords

**Note:** No sender validation - accepts PO emails from any sender

### 3. Agent Processing

**Order-to-Invoice Agent:**
- Receives email data as a message
- Uses LLM to process with customer data context
- Returns concise response (under 200 chars)

**Customer data context:**
- 3 mock customers (ABC Trading, XYZ Construction, BuildWell)
- Contact details, addresses, trading house status

### 4. Audit Logging

All PO emails are logged to `AuditLogEntry`:
- Sender, subject, attachment filename
- Received timestamp
- Agent response

## Mock Data

### Sample PO Emails

**Email 1:**
- Sender: customer1@example.com
- Subject: PO-2026-001 - Wire Mesh Order
- Attachment: PO-2026-001.pdf

**Email 2:**
- Sender: customer2@example.com
- Subject: Purchase Order #12345
- Attachment: PO-12345.pdf

### PO Sender Allowlist

- customer1@example.com
- customer2@example.com

## Current Limitations

The current implementation is a **proof of concept**:

✅ **Implemented:**
- Email webhook with validation
- Routing to Order-to-Invoice Agent
- LLM processing with customer data
- Audit logging
- Mock email testing

❌ **Not Yet Implemented:**
- PDF attachment extraction (structured data extraction)
- Real email server polling (IMAP integration)
- Delivery address validation
- Price table cross-checking
- Draft order/invoice creation
- Automatic response email
- Integration with AOTG API for actual order creation

## Next Steps for Production

1. **Implement PDF extraction:**
   - Use Ilmu Claw or specialized PDF parser
   - Extract items, quantities, prices, delivery terms
   - Validate data structure

2. **Add email polling:**
   - IMAP integration to poll email inbox
   - Process attachments automatically
   - Handle errors and retries

3. **Implement validation:**
   - Delivery address validation against customer data
   - Trading house checks
   - Price cross-checking against price table

4. **Create draft orders:**
   - Use AOTG API to create draft sales orders
   - Send to admin for approval
   - Track approval workflow

5. **Send confirmations:**
   - Email customer with order confirmation
   - CC salesperson
   - Attach order/invoice documents

## Troubleshooting

### "Sender not on PO allowlist"
- Add sender to `EmailConfig.po_sender_allowlist`
- Use `--add-email-config` to reset allowlist
- Check database for email config

### "Email not configured"
- Ensure email config exists in database
- Run `python setup_test_deployment.py --add-email-config`
- Check `EmailConfig.active = True`

### "No PO emails found"
- Mock email monitor returns empty list
- Check subject contains PO keywords
- Verify sender is on allowlist

### Agent response is generic
- Ensure Ilmu API key is configured
- Check LLM is accessible
- Verify customer data is loaded

### Webhook returns 403
- Check `EMAIL_WEBHOOK_SECRET_TOKEN` in `.env`
- Verify header matches: `X-Email-Secret-Token`
- Ensure secret is at least 32 characters

## Monitoring

### View Audit Logs

```sql
SELECT 
    entity_id as subject,
    details,
    performed_by,
    created_at
FROM audit_log_entry
WHERE entity_type = 'email_po'
ORDER BY created_at DESC
LIMIT 20;
```

### View Email Config

```sql
SELECT 
    imap_server,
    username,
    po_sender_allowlist,
    po_keywords,
    active
FROM email_config;
```

## Security Notes

⚠️ **Important:**
- Email passwords are stored in plaintext (TODO: migrate to encrypted storage)
- Use separate email account for PO processing
- Never use personal email credentials
- Implement proper secret management in production
- Use environment-specific secrets
