# Outlook (Microsoft Graph) Integration Guide

## Overview

The system can poll emails from Outlook using Microsoft Graph API. This is an alternative to webhook-based email processing and is useful for:

- Office 365 / Microsoft 365 email accounts
- Exchange Online email accounts
- Continuous email polling without webhooks
- Bypassing ngrok/public URL requirements

## Prerequisites

### 1. Azure AD App Registration

You need to register an app in Azure Active Directory to access Microsoft Graph API.

**Steps:**

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Click **New registration**
4. Fill in:
   - **Name**: `Sales Admin Email Agent`
   - **Supported account types**: 
     - For personal Outlook: "Accounts in any organizational directory and personal Microsoft accounts"
     - For work/school: "Accounts in this organizational directory only"
   - **Redirect URI**: (optional, not needed for service principal)
5. Click **Register**

### 2. Configure API Permissions

1. In the app registration, go to **API permissions**
2. Click **Add a permission** → **Microsoft Graph**
3. Select **Delegated permissions** (for interactive flow) or **Application permissions** (for service principal)
4. Add:
   - `Mail.Read` - Read emails from inbox
5. Click **Add permissions**
6. Click **Grant admin consent** (for work/school accounts) or consent for your account

### 3. Get Credentials

From the app registration **Overview** page:
- Copy **Application (client) ID** → This is `MS_CLIENT_ID`
- Copy **Directory (tenant) ID** → This is `MS_TENANT_ID`

From the app registration **Certificates & secrets** page:
- Click **New client secret**
- Add a description and expiry
- Copy the **Value** → This is `MS_CLIENT_SECRET`

## Configuration

Add to your `.env` file:

```bash
# Microsoft Graph (Outlook) Configuration
MS_CLIENT_ID=your-azure-ad-client-id
MS_TENANT_ID=your-azure-ad-tenant-id  # or 'consumers' for personal accounts
MS_CLIENT_SECRET=your-azure-ad-client-secret
MS_POLL_INTERVAL=300  # Polling interval in seconds (default: 5 minutes)
```

## Testing Outlook Connection

### Step 1: Configure Credentials

Add your Azure AD credentials to `.env`:
```bash
MS_CLIENT_ID=your-client-id
MS_TENANT_ID=your-tenant-id
MS_CLIENT_SECRET=your-client-secret
```

### Step 2: Test Connection

Run the test script:
```bash
python outlook_poller.py
```

Expected output:
```
Testing Outlook connection via Microsoft Graph API...

Client ID: your-client-id
Tenant ID: your-tenant-id
Client Secret: Configured

✅ Successfully fetched 5 emails:

  2026-10-13T10:00:00Z | customer@example.com | PO-2026-001 - Wire Mesh Order
    ID: AAMk...
    Attachments: Yes

  2026-10-13T09:30:00Z | supplier@example.com | Delivery Update
    ID: AAMk...
    Attachments: No
```

### Step 3: Poll Once

To poll once and process emails:
```python
from outlook_poller import OutlookEmailPoller

poller = OutlookEmailPoller()
result = poller.poll_once(limit=10)
print(result)
```

### Step 4: Continuous Polling

To start continuous polling:
```python
from outlook_poller import OutlookEmailPoller

poller = OutlookEmailPoller()
poller.poll_continuous(limit=10)
```

This will poll every 5 minutes (configurable via `MS_POLL_INTERVAL`).

## Integration with Email Order Agent

The Outlook poller integrates with the email order agent:

1. **Fetches emails** from Outlook inbox
2. **Downloads attachments** (PDFs, images)
3. **Converts** to `InboundEmail` format
4. **Processes** through email order agent
5. **Creates drafts** in AutoCount
6. **Notifies** admin via Telegram

### Email Processing Flow

```
Outlook Poller
    ↓
Fetch emails (Graph API)
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

## Running as a Service

### Option 1: Separate Process

Run the poller as a separate background process:

```bash
python -u outlook_poller.py
```

Use a process manager like:
- **Systemd** (Linux)
- **Windows Service** (Windows)
- **Supervisor** (Cross-platform)
- **Docker Compose** (Containerized)

### Option 2: Background Thread

Add to `main.py` as a background thread:

```python
from outlook_poller import OutlookEmailPoller
import threading

@app.on_event("startup")
async def start_outlook_poller():
    if settings.ms_client_id and settings.ms_client_secret:
        poller = OutlookEmailPoller()
        thread = threading.Thread(target=poller.poll_continuous, kwargs={"limit": 10})
        thread.daemon = True
        thread.start()
        logger.info("Outlook poller started")
```

### Option 3: Scheduled Task

Use a task scheduler like:
- **Windows Task Scheduler**
- **cron** (Linux)
- **APScheduler** (Python library)

## Authentication Flows

### Service Principal Flow (Recommended for Production)

Used for automated service account without user interaction:

- Uses `MS_CLIENT_SECRET`
- No user login required
- Suitable for server-side polling
- Requires `Application permissions` in Azure AD

### Device Code Flow (Interactive)

Used for personal accounts or development:

- No `MS_CLIENT_SECRET` required
- Requires manual user login (copy device code, enter code)
- Suitable for development/testing
- Uses `Delegated permissions`

The poller currently supports service principal flow. For device code flow, use the existing `setup_test_outlook.py` script.

## Troubleshooting

### Issue: Authentication Failed

**Error**: `AADSTS700016: Application with identifier X was not found`

**Solution**:
- Verify `MS_CLIENT_ID` is correct
- Check `MS_TENANT_ID` matches your Azure AD
- Ensure app is registered in the correct directory

### Issue: Insufficient Privileges

**Error**: `403 Forbidden` or `Access token is empty`

**Solution**:
- Grant admin consent for API permissions
- Check `Mail.Read` permission is added
- For work accounts, ensure admin granted organization-wide consent

### Issue: No Emails Found

**Error**: Successfully authenticated but no emails returned

**Solution**:
- Check if emails are in the monitored folder (Inbox)
- Verify the inbox has emails
- Check the `since` parameter (may be filtering out recent emails)
- Verify `MS_POLL_INTERVAL` is not too long

### Issue: Attachment Download Failed

**Error**: Attachment content not downloaded

**Solution**:
- Check attachment size (may exceed limits)
- Verify attachment type is supported
- Check Graph API quota limits

### Issue: Token Cache Issues

**Error**: Stale token or cache corruption

**Solution**:
- Delete `token_cache.json`
- The system will re-authenticate on next run
- For service principal, check if secret expired

## Security Considerations

### 1. Store Secrets Securely

- Never commit `MS_CLIENT_SECRET` to version control
- Use environment variables or secret management
- Rotate secrets periodically

### 2. Use Least Privilege

- Only request `Mail.Read` permission (not `Mail.ReadWrite`)
- Use application-specific app registration
- Limit access to specific mailboxes if possible

### 3. Token Management

- Tokens are cached in `token_cache.json`
- Cache file should be excluded from version control
- Service principal tokens need rotation after expiry

### 4. Rate Limiting

- Microsoft Graph has rate limits
- Set `MS_POLL_INTERVAL` to at least 60 seconds
- Handle rate limit errors gracefully
- Implement exponential backoff if needed

## Monitoring

### Key Metrics

- Poll success rate
- Emails fetched per poll
- Processing success rate
- Authentication errors
- API rate limit hits

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

## Webhook vs Polling

### Webhook (Current Implementation)

**Pros:**
- Real-time processing
- No polling overhead
- Efficient for low volume

**Cons:**
- Requires public URL (ngrok for testing)
- Depends on third-party webhook provider
- More complex to set up

### Polling (Outlook Integration)

**Pros:**
- No public URL required
- Works with Office 365 directly
- Simpler infrastructure
- Good for internal email systems

**Cons:**
- Not real-time (depends on poll interval)
- Continuous polling overhead
- May miss emails between polls

### Recommendation

- **Development**: Use webhook with ngrok
- **Production**: Use Outlook polling for Office 365
- **Hybrid**: Use webhook for external providers, polling for Office 365

## Example: Scheduled Polling with Supervisor

Install Supervisor:
```bash
pip install supervisor
```

Create `/etc/supervisor/conf.d/outlook-poller.conf`:
```ini
[program:outlook-poller]
command=python /path/to/outlook_poller.py
directory=/path/to/sales-admin-autocount
user=your-user
autostart=true
autorestart=true
stderr_logfile=/var/log/outlook-poller.err.log
stdout_logfile=/var/log/outlook-poller.out.log
```

Start Supervisor:
```bash
supervisord -c /etc/supervisor/supervisord.conf
```

Check status:
```bash
supervisorctl status outlook-poller
```

## Next Steps

1. **Register Azure AD app** (if not already done)
2. **Configure credentials** in `.env`
3. **Test connection** with `python outlook_poller.py`
4. **Process a test email** and verify it creates a draft
5. **Choose deployment method** (separate process, background thread, or scheduled task)
6. **Monitor** logs and metrics
