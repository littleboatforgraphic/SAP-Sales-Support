# Gmail (Google) Integration Guide

## Overview

The system can poll emails from Gmail using two methods:

1. **Gmail API** (OAuth 2.0) - Recommended for production, more reliable and feature-rich
2. **Gmail IMAP** - Simpler setup, uses app passwords

Both methods fetch emails and process them through the email order agent.

## Prerequisites

### Method 1: Gmail API (Recommended)

#### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select an existing one
3. Enable the **Gmail API**:
   - Go to **APIs & Services** → **Library**
   - Search for "Gmail API"
   - Click **Enable**

#### Step 2: Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Choose **Desktop app** (for installed applications)
4. Name it "Sales Admin Email Agent"
5. Click **Create**
6. Download the JSON file (contains client_id and client_secret)

#### Step 3: Get Refresh Token

Run the authorization script to get a refresh token:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes for Gmail API
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Load client secrets
flow = InstalledAppFlow.from_client_secrets_file(
    'credentials.json',  # Downloaded from Google Cloud
    SCOPES
)
creds = flow.run_local_server(port=0)

# Save credentials
with open('token.json', 'w') as token:
    token.write(creds.to_json())
```

This will open a browser for authorization. After you authorize, it will save `token.json` containing the refresh token.

#### Step 4: Configure .env

```bash
# Gmail API Configuration
GMAIL_CLIENT_ID=your-client-id
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REFRESH_TOKEN=your-refresh-token
GMAIL_POLL_INTERVAL=300
```

### Method 2: Gmail IMAP (Alternative)

#### Step 1: Enable IMAP in Gmail

1. Go to Gmail → Settings → See all settings
2. Go to **Forwarding and POP/IMAP** tab
3. Enable **IMAP**
4. Save changes

#### Step 2: Create App Password

1. Go to [Google Account](https://myaccount.google.com)
2. Go to **Security** → **2-Step Verification**
3. Enable 2-Step Verification (required for app passwords)
4. Go to **App passwords**
5. Select **Mail** and **Windows Computer**
6. Click **Generate**
7. Copy the generated app password

#### Step 3: Configure .env

```bash
# Gmail IMAP Configuration
GMAIL_IMAP_USERNAME=your-email@gmail.com
GMAIL_IMAP_PASSWORD=your-app-password
GMAIL_IMAP_PORT=993
GMAIL_POLL_INTERVAL=300
```

## Testing Gmail Connection

### Step 1: Configure Credentials

Add your Gmail credentials to `.env` (use either API or IMAP method):

**For Gmail API:**
```bash
GMAIL_CLIENT_ID=your-client-id
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REFRESH_TOKEN=your-refresh-token
```

**For IMAP:**
```bash
GMAIL_IMAP_USERNAME=your-email@gmail.com
GMAIL_IMAP_PASSWORD=your-app-password
```

### Step 2: Test Connection

Run the test script:
```bash
python gmail_poller.py
```

Expected output for Gmail API:
```
Testing Gmail connection...

Method: Gmail API (OAuth 2.0)
Client ID: your-client-id

✅ Successfully fetched 5 emails:

  2026-10-13T10:00:00Z | customer@example.com | PO-2026-001 - Wire Mesh Order
    ID: AAMk...
    Attachments: 1
```

Expected output for IMAP:
```
Testing Gmail connection...

Method: IMAP
Username: your-email@gmail.com

✅ Successfully fetched 5 emails:
```

### Step 3: Poll Once

To poll once and process emails:
```python
from gmail_poller import GmailEmailPoller

poller = GmailEmailPoller()
result = poller.poll_once(limit=10)
print(result)
```

### Step 4: Continuous Polling

To start continuous polling:
```python
from gmail_poller import GmailEmailPoller

poller = GmailEmailPoller()
poller.poll_continuous(limit=10)
```

## Integration with Email Order Agent

The Gmail poller integrates with the email order agent:

1. **Fetches emails** from Gmail inbox
2. **Downloads attachments** (PDFs, images)
3. **Converts** to `InboundEmail` format
4. **Processes** through email order agent
5. **Creates AutoCount drafts** automatically
6. **Notifies** admin via Telegram

### Email Processing Flow

```
Gmail Poller (API or IMAP)
    ↓
Fetch emails
    ↓
Download attachments
    ↓
Convert to InboundEmail
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
```

## Running Multiple Poller (Outlook + Gmail)

You can run both Outlook and Gmail pollers simultaneously:

### Option 1: Separate Processes

```bash
# Terminal 1: Outlook poller
python -u outlook_poller.py

# Terminal 2: Gmail poller
python -u gmail_poller.py
```

### Option 2: Combined in main.py

```python
from outlook_poller import OutlookEmailPoller
from gmail_poller import GmailEmailPoller
import threading

@app.on_event("startup")
async def start_email_pollers():
    # Outlook poller
    if settings.ms_client_id and settings.ms_client_secret:
        outlook_poller = OutlookEmailPoller()
        outlook_thread = threading.Thread(
            target=outlook_poller.poll_continuous,
            kwargs={"limit": 10}
        )
        outlook_thread.daemon = True
        outlook_thread.start()
        logger.info("Outlook poller started")

    # Gmail poller
    if (settings.gmail_client_id and settings.gmail_refresh_token) or \
       (settings.gmail_imap_username and settings.gmail_imap_password):
        gmail_poller = GmailEmailPoller()
        gmail_thread = threading.Thread(
            target=gmail_poller.poll_continuous,
            kwargs={"limit": 10}
        )
        gmail_thread.daemon = True
        gmail_thread.start()
        logger.info("Gmail poller started")
```

## Gmail API vs IMAP Comparison

### Gmail API (Recommended)

**Pros:**
- More reliable and feature-rich
- Better attachment handling
- Supports complex search queries
- Can access labels and folders
- No manual password handling (OAuth 2.0)

**Cons:**
- More complex setup
- Requires Google Cloud project
- Requires OAuth 2.0 credentials
- Token refresh management

### IMAP (Alternative)

**Pros:**
- Simpler setup
- No Google Cloud required
- Works with any Gmail account
- Uses standard email protocol

**Cons:**
- Requires app password (security risk if compromised)
- Limited attachment handling
- Less reliable for high volume
- May be flagged as less secure

### Recommendation

- **Production**: Use Gmail API (OAuth 2.0)
- **Development**: Use IMAP (simpler setup)
- **High volume**: Use Gmail API (better performance)

## Gmail API Scopes

The poller uses the `gmail.readonly` scope which allows:
- Reading emails from inbox
- Downloading attachments
- Viewing email metadata

If you need to send emails or modify labels, you'll need additional scopes:
- `https://www.googleapis.com/auth/gmail.send` - Send emails
- `https://www.googleapis.com/auth/gmail.modify` - Modify labels, mark read/unread

## Security Considerations

### 1. Store Secrets Securely

- Never commit `GMAIL_CLIENT_SECRET` or `GMAIL_REFRESH_TOKEN` to version control
- Use environment variables or secret management
- Rotate secrets periodically

### 2. Use App Passwords for IMAP

- Regular Gmail passwords won't work with IMAP
- App passwords are 16-character codes generated by Google
- They can be revoked without changing your main password
- Store them securely (not in plaintext)

### 3. OAuth 2.0 Token Management

- Refresh tokens are long-lived (typically 6 months)
- Access tokens expire after ~1 hour
- The poller automatically refreshes expired tokens
- Store `token.json` securely

### 4. Rate Limiting

- Gmail API has rate limits (queries per day)
- IMAP has connection limits
- Set `GMAIL_POLL_INTERVAL` to at least 60 seconds
- Handle rate limit errors gracefully

## Troubleshooting

### Issue: Authentication Failed (Gmail API)

**Error**: `invalid_grant` or `Token has been expired`

**Solution**:
- Check `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET`
- Verify `GMAIL_REFRESH_TOKEN` is valid
- Ensure Gmail API is enabled in Google Cloud
- Regenerate refresh token if needed

### Issue: Authentication Failed (IMAP)

**Error**: `AUTHENTICATIONFAILED` or `Invalid credentials`

**Solution**:
- Verify you're using an app password (not regular password)
- Check 2-Step Verification is enabled
- Ensure IMAP is enabled in Gmail settings
- Try generating a new app password

### Issue: No Emails Found

**Error**: Successfully authenticated but no emails returned

**Solution**:
- Check if emails are in the monitored folder (Inbox)
- Verify the inbox has unread emails
- Check the query parameter (e.g., "is:unread")
- Verify `GMAIL_POLL_INTERVAL` is not too long

### Issue: Attachment Download Failed (Gmail API)

**Error**: Attachment content not downloaded

**Solution**:
- Check attachment size (may exceed limits)
- Verify attachment type is supported
- Check API quota limits
- Ensure proper scopes are granted

### Issue: Attachment Download Failed (IMAP)

**Error**: Attachment content empty or corrupt

**Solution**:
- Check attachment encoding (may need base64 decoding)
- Verify multipart parsing is correct
- Check attachment size limits

## Monitoring

### Key Metrics

- Poll success rate
- Emails fetched per poll
- Processing success rate
- Authentication errors
- API rate limit hits (Gmail API)
- Connection errors (IMAP)

### Logging

The poller logs:
- Authentication events
- Email fetch results
- Processing errors
- Attachment download status
- Autonomy decisions

### Alerts

Alert on:
- Authentication failures
- Polling errors
- High error rate (> 10%)
- No emails fetched for extended period

## Gmail API vs Outlook Comparison

| Feature | Gmail API | Outlook (Microsoft Graph) |
|---------|-----------|---------------------------|
| **Authentication** | OAuth 2.0 | OAuth 2.0 |
| **Setup Complexity** | Medium | Medium |
| **Real-time** | Polling only | Polling only |
| **Attachment Support** | Full | Full |
| **Search Capabilities** | Good | Good |
| **Rate Limits** | 250 queries/day/user | Higher limits |
| **Ease of Use** | Medium | Medium |

## Webhook vs Polling

Both Gmail and Outlook use polling (not webhooks) in this implementation.

**Advantages of polling:**
- No public URL required
- Works with internal email systems
- More control over polling frequency
- No webhook security concerns

**Disadvantages of polling:**
- Not real-time (depends on poll interval)
- Continuous polling overhead
- May miss emails between polls
- Requires persistent connection

## Example: Combined Multi-Provider Setup

Run both Outlook and Gmail simultaneously:

```bash
# Terminal 1: Outlook
python -u outlook_poller.py

# Terminal 2: Gmail API
python -u gmail_poller.py

# Terminal 3: Gmail IMAP (alternative)
# python -u gmail_poller.py  # with IMAP credentials in .env
```

Or in a single process:

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

# Start both pollers
outlook_thread = threading.Thread(target=run_outlook_poller)
gmail_thread = threading.Thread(target=run_gmail_poller)

outlook_thread.daemon = True
gmail_thread.daemon = True

outlook_thread.start()
gmail_thread.start()

# Keep main thread alive
import time
while True:
    time.sleep(1)
```

## Next Steps

1. **Set up Gmail API** (recommended) or **Gmail IMAP**
2. **Configure credentials** in `.env`
3. **Test connection** with `python gmail_poller.py`
4. **Process a test email** and verify it creates a draft
5. **Choose deployment method** (separate process, background thread, or combined)
6. **Monitor** logs and metrics
