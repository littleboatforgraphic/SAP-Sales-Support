# Sales Admin SAP AI Agent System

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
├── mock_sap_client.py        # Mock SAP client for testing
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

### Pending (Requires SAP/WhatsApp Integration)
- SAP integration layer (sap_client.py)
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

- LLM pricing lives in one place: the `llm_pricing` table in `config.py` (USD per
  million tokens, keyed by model name). Override it without code changes by setting
  `LLM_PRICING` (JSON) in `.env`.
- Every usage log row records the model used, so usage summaries (`get_daily_usage`
  / `get_monthly_usage`) include a per-model breakdown alongside per-agent.

## Architecture

The system follows the architecture defined in `04-Software-Architecture-Document.md`:

```
WhatsApp / Telegram → Webhook Router → Core Message Handler → Agent Orchestration → Reference Data & SAP
                                              ↓
                                      Audit Log & Usage Tracker
```

## Next Steps

1. **Get SAP Integration Details**: Confirm SAP version and API access method (OData vs RFC/BAPI)
2. **Set Up WhatsApp Coexistence**: Configure Meta Cloud API with coexistence enabled
3. **Build SAP Client**: Implement sap_client.py with actual SAP integration
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
