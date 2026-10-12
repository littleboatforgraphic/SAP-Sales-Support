# Deployment Guide

This guide explains how to deploy the Sales Admin Autocount AI Agent System on a computer connected to AutoCount and test it via Telegram bot.

## Prerequisites

### Required on the AutoCount Computer:
- **Docker** installed (https://docs.docker.com/get-docker/)
- **Docker Compose** installed (usually included with Docker Desktop)
- **Git** (to clone the repository)
- **Python 3.10+** (for local debugging if needed)
- **Internet access** for:
  - Telegram Bot API
  - Ilmu Claw API
  - AOTG API (AutoCount Cloud Bridge)
  - ngrok tunnel (if using ngrok)

### Required Access:
- **Ilmu API key** (you mentioned this is ready)
- **Telegram bot token** (from @BotFather)
- **AOTG API credentials** (username, password, API key from AOTG Cloud)
- **AutoCount SQL Server access** (for stock/inventory queries)
- **AutoCount network access** from the deployment computer

### Required for Telegram Webhook:
Since the AutoCount computer is on a private network, you need one of:
- **ngrok** (free tier, easiest for testing)
- **Cloudflare Tunnel** (free, more stable)
- **SSH reverse tunnel** (requires technical setup)
- **VPN** (requires infrastructure setup)

---

## Quick Start (Testing with Mock AutoCount)

If you want to test the Telegram integration first without real AutoCount connection:

### Step 1: Clone the Codebase

```bash
git clone <repository-url>
cd "Sales Admin Autocount"
```

### Step 2: Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and set:
```env
DATABASE_URL=sqlite:///./sales_admin_autocount.db
ILMU_API_KEY=your_ilmu_api_key_here
ILMU_BASE_URL=https://api.ilmu.ai/v1
ILMU_MODEL=ilmu-mini-v3.3
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_WEBHOOK_SECRET_TOKEN=random_secret_string_32_chars
ENVIRONMENT=development
```

**Note**: Leave AOTG credentials empty to use mock AutoCount client.

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Initialize Database

```bash
python init_db.py
```

### Step 5: Seed Initial Data

```bash
python seed_data.py
```

### Step 6: Run the Application

```bash
python main.py
```

The API will be available at `http://localhost:8000`

### Step 7: Set Up ngrok Tunnel

In a new terminal:

```bash
ngrok http 8000
```

Note the public HTTPS URL (e.g., `https://xxxx-xx-xx-xx-xx.ngrok-free.app`)

### Step 8: Register Telegram Webhook

```bash
python setup_webhook.py --webhook-url https://your-ngrok-url.ngrok-free.app/api/v1/webhook/telegram
```

### Step 9: Add Your Telegram User ID to Staff Allowlist

1. Start a conversation with your bot in Telegram
2. Send a message to the bot
3. Use @userinfobot to get your Telegram user ID
4. Add it to the database:

```bash
python
```

```python
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("INSERT INTO staff_allowlist (name, telegram_user_id) VALUES ('Your Name', '123456789')"))
db.commit()
db.close()
```

### Step 10: Test the Bot

1. Open Telegram on your phone
2. Search for your bot by username
3. Click "Start"
4. Send: "AI: help"

The bot should respond (if agents are implemented).

---

## Docker Deployment (Recommended for Production)

### Step 1: Clone the Codebase

```bash
git clone <repository-url>
cd "Sales Admin Autocount"
```

### Step 2: Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and set all required variables:

**Essential:**
```env
DATABASE_URL=sqlite:////app/data/sales_admin_autocount.db
ILMU_API_KEY=your_ilmu_api_key_here
ILMU_BASE_URL=https://api.ilmu.ai/v1
ILMU_MODEL=ilmu-mini-v3.3
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_WEBHOOK_SECRET_TOKEN=random_secret_string_32_chars
ENVIRONMENT=development
```

**AOTG API Configuration (AutoCount Cloud Bridge):**
```env
AOTG_BASE_URL=https://aotgapi.autocountcloud.com
AOTG_USERNAME=your_aotg_username
AOTG_PASSWORD=your_aotg_password
AOTG_API_KEY=your_aotg_api_key
```

**AutoCount SQL Server Configuration (for stock queries):**
```env
AUTOCOUNT_SQL_SERVER=localhost
AUTOCOUNT_SQL_DATABASE=AutoCountDB
AUTOCOUNT_SQL_USERNAME=sa
AUTOCOUNT_SQL_PASSWORD=your_sql_password
AUTOCOUNT_SQL_DRIVER=ODBC Driver 17 for SQL Server
```

**Note**: SQL Server driver (pyodbc) is already included in requirements.txt.

### Step 3: Build Docker Image

```bash
docker build -t sales-admin-autocount-agent .
```

### Step 4: Run Docker Container

```bash
docker-compose up -d
```

### Step 5: Verify Container is Running

```bash
docker ps
docker logs sales-admin-autocount-agent
```

### Step 6: Test Health Endpoint

```bash
curl http://localhost:8000/health
```

### Step 7: Initialize Database (Inside Container)

```bash
docker exec -it sales-admin-autocount-agent python init_db.py
```

### Step 8: Seed Initial Data (Inside Container)

```bash
docker exec -it sales-admin-autocount-agent python seed_data.py
```

### Step 9: Add Your Telegram User ID to Staff Allowlist

```bash
docker exec -it sales-admin-autocount-agent python
```

```python
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("INSERT INTO staff_allowlist (name, telegram_user_id) VALUES ('Your Name', '123456789')"))
db.commit()
db.close()
exit()
```

### Step 10: Set Up ngrok Tunnel

In a new terminal:

```bash
ngrok http 8000
```

Note the public HTTPS URL.

### Step 11: Register Telegram Webhook

```bash
python setup_webhook.py --webhook-url https://your-ngrok-url.ngrok-free.app/api/v1/webhook/telegram
```

### Step 12: Test the Bot

Same as Quick Start Step 10.

---

## Implementing Real AutoCount Integration

### AOTG API Setup

1. **Install AOTG Client** on the AutoCount server
2. **Activate Account Book** in AOTG Client
3. **Retrieve API Key** from AOTG Cloud:
   - Login to AOTG at https://aotg.autocountcloud.com
   - Go to Account Settings → AOTG Subscription
   - Click My Subscription → ACCOUNT BOOK(S)
   - View the API Key for your account book

### Configure AOTG Client

Edit `.env` with your AOTG credentials:
```env
AOTG_USERNAME=your_username
AOTG_PASSWORD=your_password
AOTG_API_KEY=your_api_key
```

### Configure SQL Server Access

For stock/inventory queries, configure SQL Server access:
```env
AUTOCOUNT_SQL_SERVER=localhost
AUTOCOUNT_SQL_DATABASE=AutoCountDB
AUTOCOUNT_SQL_USERNAME=sa
AUTOCOUNT_SQL_PASSWORD=your_password
```

**Note**: The SQL table structure for stock may vary. Verify the actual table name (e.g., StockItem, Item) and column names in your AutoCount database.

### Test AutoCount Connection Independently

Before integrating with agents:

```python
# Create a test script test_autocount_connection.py
from autocount_client import get_autocount_client

client = get_autocount_client()

# Test customer lookup
customer = client.get_customer_details("300-A001")
print(f"Customer: {customer}")

# Test stock lookup
stock = client.get_stock_info("WM-001")
print(f"Stock: {stock}")
```

Run the test:
```bash
python test_autocount_connection.py
```

---

## Alternative Tunneling Solutions

If ngrok is not suitable for your environment:

### Cloudflare Tunnel (Recommended for Production)

1. Install cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/
2. Authenticate: `cloudflared tunnel login`
3. Create tunnel: `cloudflared tunnel create sales-admin-autocount`
4. Configure tunnel to point to localhost:8000
5. Use the provided URL for Telegram webhook

### SSH Reverse Tunnel

Requires a public server:

```bash
ssh -R 80:localhost:8000 user@public-server.com
```

Then use `public-server.com` as your webhook URL.

### VPN

Set up a VPN between the AutoCount computer and a public server, then use the VPN IP for webhook.

---

## Production Considerations

### Security

- **Never commit `.env` to git** - it contains sensitive credentials
- **Use strong webhook secret tokens** - 32+ random characters
- **Enable webhook signature verification** - Already implemented in code
- **Configure firewall rules** - Only allow necessary ports
- **Rotate API keys periodically** - Especially for production
- **Use HTTPS in production** - Required for Telegram webhooks

### Reliability

- **Docker restart policy** - Already configured as `restart: unless-stopped`
- **Database persistence** - Volumes configured in docker-compose.yml
- **PostgreSQL for production** - More reliable than SQLite
- **Database backups** - Set up automated backups
- **Log aggregation** - Configure centralized logging
- **Monitoring** - Set up alerts for critical failures

### Performance

- **Rate limiting** - Already configured in settings
- **Caching** - Implement caching for reference data
- **Database optimization** - Add indexes for frequently queried fields
- **Load balancing** - For high-traffic deployments

### Scaling

For multiple deployments or high traffic:
- Use PostgreSQL instead of SQLite
- Deploy behind a load balancer
- Use container orchestration (Kubernetes)
- Consider message queue for webhook processing

---

## Troubleshooting

### Docker Container Won't Start

**Problem**: Container exits immediately

**Solutions**:
```bash
# Check logs
docker logs sales-admin-autocount-agent

# Check if port 8000 is already in use
netstat -ano | findstr :8000

# Verify .env file exists
ls -la .env

# Rebuild container
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Webhook Not Receiving Messages

**Problem**: Telegram messages not reaching the application

**Solutions**:
```bash
# Check ngrok is running
curl http://localhost:4040/api/tunnels

# Verify webhook is set
python setup_webhook.py --info

# Check webhook URL is correct
curl https://your-ngrok-url.ngrok-free.app/health

# Check container logs
docker logs -f sales-admin-sap-agent

# Verify staff allowlist
docker exec -it sales-admin-autocount-agent python
# Then: from database import SessionLocal; db = SessionLocal(); print(db.execute(text("SELECT * FROM staff_allowlist")).fetchall())
```

### AutoCount Connection Fails

**Problem**: Cannot connect to AutoCount

**Solutions**:
```bash
# Verify AOTG credentials in .env
cat .env | grep AOTG

# Test AOTG connectivity from container
docker exec -it sales-admin-autocount-agent bash
curl https://aotgapi.autocountcloud.com

# Verify SQL Server credentials
cat .env | grep AUTOCOUNT_SQL

# Review AutoCount logs for authentication errors
```

### Telegram Bot Doesn't Respond

**Problem**: Bot receives messages but doesn't respond

**Solutions**:
```bash
# Check your user ID is in staff allowlist
docker exec -it sales-admin-autocount-agent python
# Then: from database import SessionLocal; print(SessionLocal().execute(text("SELECT * FROM staff_allowlist")).fetchall())

# Verify trigger phrases are correct
# Expected: "AI:" or "Agent:" prefix

# Check agent implementations exist
ls agents/

# Review logs for processing errors
docker logs -f sales-admin-sap-agent
```

### Database Errors

**Problem**: Database initialization or connection errors

**Solutions**:
```bash
# Reinitialize database
docker exec -it sales-admin-autocount-agent python init_db.py

# Reseed data
docker exec -it sales-admin-autocount-agent python seed_data.py

# Check database file permissions
ls -la sales_admin_autocount.db

# Check data directory exists
ls -la data/
```

---

## Monitoring and Maintenance

### View Logs

```bash
# Follow logs in real-time
docker logs -f sales-admin-sap-agent

# View last 100 lines
docker logs --tail 100 sales-admin-sap-agent
```

### Restart Container

```bash
docker-compose restart
```

### Stop Container

```bash
docker-compose down
```

### Update Application

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d
```

### Backup Database

```bash
# For SQLite
cp sales_admin_autocount.db sales_admin_autocount.db.backup

# For PostgreSQL (if using)
pg_dump sales_admin_autocount > backup.sql
```

---

## Next Steps

### Phase 1: Testing with Mock AutoCount (Current)
- ✅ Docker deployment
- ✅ Telegram webhook setup
- ✅ Test basic message flow
- ⏳ Implement agents with mock AutoCount client

### Phase 2: Real AutoCount Integration
- ✅ Configure AOTG API credentials
- ✅ Implement AOTG client methods (Sales Order, AR Invoice, Delivery Order)
- ⏳ Test AutoCount connection independently
- ⏳ Update agents to use real AutoCount client

### Phase 3: Agent Implementation
- ⏳ Stock & Quote Agent
- ⏳ Order-to-Invoice Agent
- ⏳ Shipment Agent
- ⏳ Customer Onboarding Agent
- ⏳ Payment Follow-up Agent

### Phase 4: Production Setup
- ⏳ Switch to PostgreSQL
- ⏳ Set up monitoring and alerting
- ⏳ Configure automated backups
- ⏳ Implement rate limiting and caching
- ⏳ Security hardening

---

## Additional Resources

- **Telegram Bot API**: https://core.telegram.org/bots/api
- **Docker Documentation**: https://docs.docker.com/
- **ngrok Documentation**: https://ngrok.com/docs
- **Ilmu Claw API**: Check your API documentation
- **AutoCount Documentation**: https://wiki.autocountsoft.com/wiki/Category:AOTGApi

---

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review application logs: `docker logs sales-admin-autocount-agent`
3. Check Telegram webhook info: `python setup_webhook.py --info`
4. Consult the main README.md for architecture details
