# Sales Admin Autocount AI Agent System

AI Agent System for Office Admin & Sales Workflow — Wire Mesh Manufacturing

## Project Structure

```
.
├── agents/                    # Agent implementations (to be added)
├── routers/                   # FastAPI route handlers (WhatsApp + Telegram webhooks)
├── tests/                     # Test files
├── database.py               # Database schema and models
├── config.py                 # Configuration management (incl. LLM pricing table)
├── glossary.py               # Glossary/shortform resolution
├── sku_index.py              # SKU index and fuzzy matching
├── price_table.py            # Price reference table
├── usage_tracker.py          # Token usage and budget tracking (per-model)
├── audit_log.py              # Audit logging
├── trigger.py                # Trigger detection logic
├── message_handler.py        # Channel-agnostic core message handling
├── telegram_client.py        # Telegram Bot API client (send/webhook management)
├── llm_client.py             # LLM client (Ilmu Claw, OpenAI-compatible)
├── address_validator.py      # Delivery address validation (fraud prevention)
├── autocount_client.py       # AutoCount AOTG API client
├── mock_autocount_client.py  # Mock AutoCount client for testing
├── mock_email_monitor.py     # Mock email monitor for testing
├── main.py                   # FastAPI application entry point
├── init_db.py                # Database initialization + lightweight migrations
├── seed_data.py              # Database seeding script
├── requirements.txt          # Python dependencies
├── .env.example             # Environment variables template
└── README.md                 # This file
```

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:
- `DATABASE_URL` (SQLite for development, PostgreSQL for production)
- `ILMU_API_KEY` (for LLM integration with Ilmu Claw)

### 3. Initialize Database

```bash
python init_db.py
```

This creates all database tables.

### 4. Seed Initial Data

```bash
python seed_data.py
```

This seeds:
- Glossary with common wire mesh terms (English & Malay)
- SKU index with mock wire mesh products
- Price table with mock prices
- Sample staff member for testing

### 5. Run the Application

```bash
python main.py
```

Or using uvicorn directly:

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

### 6. Verify Health Check

```bash
curl http://localhost:8000/health
```

## Current Implementation Status

### Completed (Foundation Infrastructure)
- ✓ Project structure and Python environment
- ✓ Database schema and data models
- ✓ Configuration management (environment variables)
- ✓ Glossary module with manual seed data
- ✓ SKU index module with mock data structure
- ✓ Price table module (read-only)
- ✓ Usage tracker module with budget stopper
- ✓ Audit logging module
- ✓ FastAPI main application structure
- ✓ Webhook handler stub (staff allowlist, trigger detection)

### Pending (Requires AutoCount/WhatsApp Integration)
- AutoCount integration layer (autocount_client.py)
- Stock & Quote Agent
- Order-to-Invoice Agent
- Shipment Agent
- Customer Onboarding Agent
- Payment Follow-up Agent
- WhatsApp integration (actual webhook handling)
- Email notification module
- Retry and error handling layer
- Rate limiting layer
- Backup and recovery implementation

## Messaging Channels

The system supports two inbound channels, both feeding the same agent pipeline
(`message_handler.py` → trigger detection → agent orchestration):

| Channel | Webhook endpoint | Sender identity | Signature verification |
|---|---|---|---|
| WhatsApp (Meta Cloud API) | `GET/POST /api/v1/webhook` | Phone number | `X-Hub-Signature-256` (HMAC-SHA256 with `WHATSAPP_APP_SECRET`) |
| Telegram (Bot API) | `POST /api/v1/webhook/telegram` | Numeric user ID | `X-Telegram-Bot-Api-Secret-Token` (constant-time compare with `TELEGRAM_WEBHOOK_SECRET_TOKEN`) |

Telegram is offered as a lower-cost alternative for staff messaging. To set it up:

1. Create a bot via [@BotFather](https://t.me/BotFather) and put its token in `TELEGRAM_BOT_TOKEN`.
2. Generate a random secret string for `TELEGRAM_WEBHOOK_SECRET_TOKEN`.
3. Register the webhook (the bot must be able to reach your server over HTTPS):
   ```python
   from telegram_client import telegram_client
   telegram_client.set_webhook(
       "https://your-server.example.com/api/v1/webhook/telegram",
       secret=settings.telegram_webhook_secret_token
   )
   ```
4. Add staff Telegram user IDs to the `telegram_user_id` column of `staff_allowlist`.

In production, both webhooks refuse unsigned traffic if their secrets are unset;
in development, verification is skipped with a log warning.

## LLM Cost Tracking

- Token usage, cost (MYR) and monthly budgets are tracked centrally by the LLM gateway
  (`littleboatforgraphic/llm-gateway`), not by this app. Set `LLM_GATEWAY_URL` /
  `LLM_GATEWAY_KEY` (see `DEPLOYMENT.md`); every call is tagged `app:sales-autocount` and
  `op:<operation>` for per-operation reports.
- Budgets and alerts are set per client on the gateway (`gw set-budget`). The app still gets
  token counts in each `chat_completion` result but keeps no price table or budget of its own.

## Architecture

The system follows the architecture defined in `04-Software-Architecture-Document.md`:

```
WhatsApp / Telegram → Webhook Router → Core Message Handler → Agent Orchestration → Reference Data & AutoCount
                                              ↓
                                      Audit Log & Usage Tracker
```

## Next Steps

1. **Get AutoCount Integration Details**: Configure AOTG API credentials and SQL Server access
2. **Set Up WhatsApp Coexistence**: Configure Meta Cloud API with coexistence enabled
3. **Complete AutoCount Client**: Implement autocount_client.py with AOTG API and SQL queries
4. **Implement Stock & Quote Agent**: First agent to go end-to-end
5. **Add Retry & Rate Limiting**: Implement resilience patterns
6. **Build Remaining Agents**: Order-to-Invoice, Shipment, Customer Onboarding, Payment Follow-up

## Documentation

See the following documents for detailed specifications:
- `01-Product-Requirements-Document.md` - Product requirements
- `02-Scope-Document.md` - Project scope and phases
- `03-UI-Specifications.md` - UI/UX specifications
- `04-Software-Architecture-Document.md` - System architecture
- `05-Technical-Specification.md` - Technical implementation details

## Development Notes

- The database uses SQLite by default for development. Change `DATABASE_URL` in `.env` to use PostgreSQL for production.
- All modules are designed to be testable with mock implementations.
- The system is built to keep human decision-makers in the loop for financial/contractual actions.
- No business or customer data is processed by third-party workflow platforms (pure Python implementation).
