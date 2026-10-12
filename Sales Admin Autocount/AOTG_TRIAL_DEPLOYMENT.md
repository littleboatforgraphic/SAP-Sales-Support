# AOTG Trial Deployment Guide

This guide walks you through deploying and testing the AOTG catalog query system via Telegram.

## Prerequisites

1. **Telegram Bot**: Create a bot via @BotFather and get the bot token
2. **AOTG Access**: Ensure the AOTG API is accessible (no credentials needed for catalog loading)
3. **Python Environment**: Python 3.10+ with dependencies installed

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Configure Environment

Create or update your `.env` file:

```bash
# Database (SQLite for development)
DATABASE_URL=sqlite:///./sales_admin_autocount.db

# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_WEBHOOK_SECRET_TOKEN=random_secret_string_32_chars_or_more

# Environment
ENVIRONMENT=development
LOG_LEVEL=INFO
```

## Step 3: Initialize Database and Load AOTG Catalog

Run the setup script:

```bash
python setup_test_deployment.py --init-only
```

This will:
- Initialize the database with AOTG knowledge models
- Fetch and load the AOTG Swagger catalog
- Display a summary of loaded operations

## Step 4: Add Your Telegram User to Allowlist

First, get your Telegram user ID:
1. Start a chat with @userinfobot
2. Send any message
3. It will reply with your user ID

Then add yourself to the allowlist:

```bash
python setup_test_deployment.py --add-staff YOUR_TELEGRAM_USER_ID --name "Your Name"
```

## Step 5: Set Up Telegram Webhook

You need a public URL for the webhook. For testing, you can use ngrok:

```bash
# Start ngrok
ngrok http 8000

# Note the HTTPS URL provided by ngrok (e.g., https://abc123.ngrok-free.app)
```

Set the webhook:

```bash
python setup_webhook.py --webhook-url https://your-ngrok-url.ngrok-free.app/api/v1/webhook/aotg-telegram --secret-token YOUR_SECRET_TOKEN
```

Verify the webhook:

```bash
python setup_webhook.py --info
```

## Step 6: Start the Server

```bash
python main.py
```

The server will start on `http://0.0.0.0:8000`

## Step 7: Test via Telegram

In your Telegram bot, try these commands:

```
/catalog - Show catalog summary
/list - List all enabled operations
/list Debtor - List Debtor operations
/search invoice - Search for invoice operations
/details POST /api/public/v1/SalesOrder - Show operation details
/help - Show help
```

## Step 8: Enable Specific Operations (Optional)

By default, all operations are disabled for safety. To enable specific operations:

```bash
# List operations to find the operation_id
python load_aotg_catalog.py --list

# Enable a specific operation
python load_aotg_catalog.py --enable "GET /api/public/v1/Debtor"
```

## Troubleshooting

### Database Already Exists

If you get an error about tables already existing, delete the old database:

```bash
rm sales_admin_autocount.db
```

Then re-run the setup.

### Webhook Not Receiving Messages

1. Check the webhook info:
   ```bash
   python setup_webhook.py --info
   ```

2. Verify the secret token matches between `.env` and webhook setup

3. Check server logs for errors

### Unauthorized User Error

Ensure your Telegram user ID is in the staff allowlist:

```bash
# Check current staff (requires manual DB query or add a list command)
# Re-add if needed:
python setup_test_deployment.py --add-staff YOUR_USER_ID
```

### AOTG Catalog Load Failed

If the AOTG API is not accessible, you can load from a local Swagger file:

```bash
# Download the Swagger spec manually
curl -o swagger.json https://aotgapi.autocountcloud.com/swagger/docs/v1

# Load from file
python load_aotg_catalog.py --load --spec-file swagger.json
```

## Architecture Overview

The trial deployment uses:

1. **AOTG Knowledge Models** (`aotg_knowledge_models.py`):
   - AOTGSpecSnapshot: Immutable catalog snapshots
   - AOTGOperation: Individual API operations with risk classification
   - AgentCommand: Mapped user commands to operations
   - OperationPolicy: Role-based access control

2. **Catalog Loader** (`aotg_catalog_loader.py`):
   - Fetches and parses AOTG Swagger specification
   - Classifies operations by risk level
   - Resolves Swagger references

3. **Query Agent** (`aotg_query_agent.py`):
   - Provides read-only catalog queries
   - Commands: /catalog, /list, /search, /details
   - Role-based access control

4. **Telegram Webhook** (`routers/aotg_telegram_webhook.py`):
   - Receives Telegram messages
   - Verifies webhook secret
   - Checks user allowlist
   - Routes to query agent
   - Sends responses back

## Next Steps

After successful trial:

1. **Enable operations**: Review and enable safe operations for your use case
2. **Create agent commands**: Map business intents to specific operations
3. **Define policies**: Set up role-based access and approval workflows
4. **Integrate with AutoCount**: Configure AOTG credentials for actual API calls
5. **Build full agents**: Implement end-to-end workflows with LLM integration
