# Email Integration Summary

## Overview

The system supports three ways to receive emails for processing by the Email Order Agent:

1. **Email Webhook** - Receive emails via webhook (SendGrid, Mailgun, etc.)
2. **Outlook (Microsoft Graph)** - Poll emails from Office 365/Exchange Online
3. **Gmail** - Poll emails from Gmail (API or IMAP)

## Supported Email Providers

| Provider | Method | Setup Complexity | Authentication | Notes |
|----------|--------|------------------|----------------|-------|
| **Webhook** | HTTP POST | Medium | API Key | Requires webhook URL |
| **Outlook** | Microsoft Graph API | Medium | OAuth 2.0 | Requires Azure AD |
| **Gmail** | Gmail API | Medium | OAuth 2.0 | Requires Google Cloud |
| **Gmail** | IMAP | Simple | App Password | Easier setup |

## Files Created

### Core Poller Modules

- **`outlook_poller.py`** - Outlook (Microsoft Graph) email poller
  - Fetches emails via Graph API
  - Downloads attachments
  - Integrates with email order agent
  - Service principal authentication

- **`gmail_poller.py`** - Gmail email poller
  - Supports both Gmail API (OAuth 2.0) and IMAP
  - Fetches emails
  - Downloads attachments
  - Integrates with email order agent

### Configuration

- **`config.py`** - Added email poller settings:
  - `MS_CLIENT_ID`, `MS_TENANT_ID`, `MS_CLIENT_SECRET`, `MS_POLL_INTERVAL` (Outlook)
  - `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_POLL_INTERVAL` (Gmail API)
  - `GMAIL_IMAP_USERNAME`, `GMAIL_IMAP_PASSWORD`, `GMAIL_IMAP_PORT`, `GMAIL_POLL_INTERVAL` (Gmail IMAP)

- **`.env.example`** - Added all email poller configuration variables

### Documentation

- **`OUTLOOK_INTEGRATION.md`** - Complete Outlook setup guide
  - Azure AD app registration
  - API permissions
  - Credential setup
  - Testing instructions
  - Deployment options
  - Troubleshooting

- **`GMAIL_INTEGRATION.md`** - Complete Gmail setup guide
  - Gmail API setup (OAuth 2.0)
  - IMAP setup (app password)
  - Credential setup
  - Testing instructions
  - Comparison: Gmail API vs IMAP
  - Troubleshooting

## Usage Examples

### Outlook Poller

```python
from outlook_poller import OutlookEmailPoller

# One-time polling
poller = OutlookEmailPoller()
result = poller.poll_once(limit=10)

# Continuous polling
poller.poll_continuous(limit=10)
```

### Gmail Poller (API)

```python
from gmail_poller import GmailEmailPoller

# One-time polling (Gmail API)
poller = GmailEmailPoller()
result = poller.poll_once(limit=10, query="is:unread")

# Continuous polling
poller.poll_continuous(limit=10)
```

### Gmail Poller (IMAP)

```python
from gmail_poller import GmailEmailPoller

# One-time polling (IMAP - no query parameter)
poller = GmailEmailPoller()
result = poller.poll_once(limit=10)

# Continuous polling
poller.poll_continuous(limit=10)
```

## Running Multiple Poller

You can run multiple email pollers simultaneously:

```python
from outlook_poller import OutlookEmailPoller
from gmail_poller import GmailEmailPoller
import threading

def run_outlook_poller():
    poller = OutlookEmailPoller()
    poller.poll_continuous(limit=10)

def run_gmail_poller():
    poller = GmailEmailPoller()
    poller.poll_continuous(limit=10)

# Start both pollers in background threads
outlook_thread = threading.Thread(target=run_outlook_poller)
gmail_thread = threading.Thread(target=run_gmail_poller)

outlook_thread.daemon = True
gmail_thread.daemon = True

outlook_thread.start()
gmail_thread.start()
```

## Configuration Matrix

### Required for Each Method

| Method | Required Settings |
|--------|-------------------|
| **Outlook** | `MS_CLIENT_ID`, `MS_TENANT_ID`, `MS_CLIENT_SECRET` |
| **Gmail API** | `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` |
| **Gmail IMAP** | `GMAIL_IMAP_USERNAME`, `GMAIL_IMAP_PASSWORD` |

### Optional Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `MS_POLL_INTERVAL` | Outlook poll interval (seconds) | 300 |
| `GMAIL_POLL_INTERVAL` | Gmail poll interval (seconds) | 300 |

## Complete .env Example

```bash
# Email Webhook (if using webhook-based approach)
EMAIL_ENABLED=true
EMAIL_CAN_DRAFT=true
EMAIL_CAN_REPLY=true
EMAIL_WEBHOOK_SECRET_TOKEN=your-secret-token
EMAIL_OUTBOUND_ALLOWLIST=a@outlook.com,b@outlook.com

# Email Agent Autonomy Mode
EMAIL_AUTONOMY_MODE=shadow  # Options: shadow, assisted, selective_autonomy
EMAIL_AUTO_SUBMIT_MAX_AMOUNT=10000.0
EMAIL_AUTO_SUBMIT_REPEAT_CUSTOMER=true
EMAIL_AUTO_SUBMIT_TRADING_HOUSE_ALLOWED=false

# Microsoft Graph (Outlook)
MS_CLIENT_ID=your-azure-ad-client-id
MS_TENANT_ID=your-tenant-id
MS_CLIENT_SECRET=your-client-secret
MS_POLL_INTERVAL=300

# Gmail API (OAuth 2.0 - Recommended)
GMAIL_CLIENT_ID=your-google-cloud-client-id
GMAIL_CLIENT_SECRET=your-google-cloud-client-secret
GMAIL_REFRESH_TOKEN=your-refresh-token
GMAIL_POLL_INTERVAL=300

# OR Gmail IMAP (Alternative - Simpler)
GMAIL_IMAP_USERNAME=your-email@gmail.com
GMAIL_IMAP_PASSWORD=your-app-password
GMAIL_IMAP_PORT=993
GMAIL_POLL_INTERVAL=300
```

## Integration Flow

All three email providers integrate with the email order agent:

```
Email Provider (Webhook/Outlook/Gmail)
    ↓
Poller fetches emails
    ↓
Convert to InboundEmail format
    ↓
Email Order Agent
    ↓
Extract order (LLM)
    ↓
Match customer (AutoCount)
    ↓
Create AutoCount draft
    ↓
Notify admin (Telegram)
    ↓
Send acknowledgement to client
```

## Choosing a Provider

### Use Webhook When:
- Using external email provider (SendGrid, Mailgun, etc.)
- Need real-time processing
- Can set up webhook URL
- Low email volume

### Use Outlook When:
- Using Office 365 / Exchange Online
- Need to poll internal email server
- Don't want to use webhook
- Medium email volume

### Use Gmail API When:
- Using Gmail
- Want reliable, feature-rich integration
- Have Google Cloud project
- Medium to high email volume

### Use Gmail IMAP When:
- Using Gmail
- Want simpler setup
- Don't want to create Google Cloud project
- Lower email volume
- Quick testing

## Next Steps

1. **Choose email provider(s)**:
   - Webhook (if using external email provider)
   - Outlook (if using Office 365)
   - Gmail API or IMAP (if using Gmail)

2. **Set up credentials**:
   - Webhook: Configure secret token
   - Outlook: Register Azure AD app
   - Gmail API: Create Google Cloud project
   - Gmail IMAP: Enable IMAP + create app password

3. **Configure `.env`** with your chosen method(s)

4. **Test connection**:
   - `python outlook_poller.py` (Outlook)
   - `python gmail_poller.py` (Gmail)

5. **Start poller(s)**:
   - One-time: `poller.poll_once(limit=10)`
   - Continuous: `poller.poll_continuous(limit=10)`

6. **Monitor** logs and metrics

## Dependencies

Make sure you have the required packages installed:

```bash
# For Outlook
pip install msal httpx

# For Gmail API
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

# For Gmail IMAP
# Uses built-in imaplib (no additional packages needed)
```

## Troubleshooting

See the specific integration guides:
- `OUTLOOK_INTEGRATION.md` - Outlook troubleshooting
- `GMAIL_INTEGRATION.md` - Gmail troubleshooting
