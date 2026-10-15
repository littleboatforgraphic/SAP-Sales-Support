# Agent Framework Testing Guide

This guide shows you how to test the proper agent framework with LLM using mock data, following the PRD-defined agent architecture.

## Architecture

The system now follows the PRD design with 5 agents:

1. **Stock & Quote Agent** - Check stock and provide quotes
2. **Order-to-Invoice Agent** - Process orders and create invoices
3. **Shipment Agent** - Manage shipments and delivery orders
4. **Customer Onboarding Agent** - Onboard new customers
5. **Payment Follow-up Agent** - Process payment documents

These agents use:
- **Existing `llm_client.py`** - OpenAI-compatible wrapper for Ilmu Claw
- **Existing `mock_autocount_client.py`** - Mock data for testing
- **Existing `autocount_client.py`** - Real AOTG integration (when configured)
- **Proper agent base class** - Extensible framework for all agents

## Step 1: Configure Ilmu API

Add to your `.env` file:
```bash
ILMU_API_KEY=your_ilmu_api_key_here
ILMU_BASE_URL=https://api.ilmu.ai/v1
ILMU_MODEL=ilmu-mini-v3.3
```

## Step 2: Set Webhook to Agents Endpoint

```bash
python setup_webhook.py --webhook-url https://unblended-amusable-limes.ngrok-free.dev/api/v1/webhook/agents-telegram --secret-token dfgce34inDS56LING_23fFg
```

## Step 3: Start Server

```bash
python main.py
```

## Step 4: Test with Natural Language

Send natural language queries to your bot (@Eastcoastmetal_salessupport_bot). The system will automatically route to the appropriate agent based on trigger keywords.

### Stock & Quote Agent

Trigger keywords: `stock`, `quote`, `quotation`, `price`, `inventory`, `available`

**Examples:**
```
What's the stock for WM-001?
Check inventory for BRC-A142
Give me a quote for WM-002
What items are available?
Price for WM-003
```

### Order-to-Invoice Agent

Trigger keywords: `order`, `invoice`, `po`, `purchase order`, `sales order`

**Examples:**
```
I want to place an order for WM-001
Create an invoice for 300-A001
Process this purchase order
Sales order for XYZ Construction
```

### Shipment Agent

Trigger keywords: `shipment`, `delivery`, `deliver`, `ship`, `pickup`, `pack`

**Examples:**
```
Check shipment status
When will the delivery arrive?
Is the order ready for pickup?
Pack status for WM-001
```

### Customer Onboarding Agent

Trigger keywords: `new customer`, `customer onboarding`, `register`, `onboard`, `new account`

**Examples:**
```
I want to onboard a new customer
Register this new account
Customer onboarding for ABC Corp
```

### Payment Follow-up Agent

Trigger keywords: `payment`, `paid`, `receipt`, `transaction`, `bank`

**Examples:**
```
Process this payment
Check payment status
Receipt for transaction
```

## How It Works

1. **User sends message** to Telegram bot
2. **Webhook receives** the message
3. **Trigger detection** identifies which agent should handle it
4. **Agent instantiates** with mock or real AutoCount client (based on AOTG config)
5. **LLM processes** using existing `llm_client.py` with relevant data context
6. **Response sent** back to Telegram

## Mock vs Real Data

The framework automatically switches between mock and real data:

**Mock Mode** (when AOTG credentials not configured):
- Uses `mock_autocount_client.py` data
- 3 customers, 6 stock items
- Perfect for testing without real AutoCount

**Real Mode** (when AOTG credentials configured):
- Uses `autocount_client.py` with AOTG API
- Real AutoCount data
- Production use

## Current Implementation Status

### ✅ Implemented
- Base agent class with LLM integration
- Stock & Quote Agent (with mock stock data)
- Agent trigger detection
- Automatic mock/real client switching
- Telegram webhook routing

### 🚧 Partially Implemented
- Order-to-Invoice Agent (structure exists, needs AOTG operations)
- Shipment Agent (structure exists, needs AOTG operations)
- Customer Onboarding Agent (structure exists, needs document processing)
- Payment Follow-up Agent (structure exists, needs document processing)

### ❌ Not Yet Implemented
- Document PDF processing (for PO, customer onboarding, payment)
- Real AOTG operations for order/invoice creation
- Delivery order generation
- Address validation logic
- Price table integration in database

## Next Steps

1. **Test Stock & Quote Agent** with the examples above
2. **Add price data** to the `PriceReferenceEntry` table
3. **Implement AOTG operations** for order/invoice creation
4. **Add document processing** for PDF extraction
5. **Implement address validation** logic
6. **Complete remaining agents** with full functionality

## Troubleshooting

### "No trigger detected"
- Try using one of the trigger keywords listed above
- The system defaults to Stock & Quote Agent if no trigger is found

### "Error: Ilmu API key not configured"
- Add `ILMU_API_KEY` to your `.env` file
- Restart the server

### Agent not responding
- Check server logs for errors
- Verify webhook is set to `/api/v1/webhook/agents-telegram`
- Ensure your Telegram user ID is in the allowlist

## Advantages of This Approach

✅ **Follows PRD design** - Uses the 5-agent architecture from your PRD
✅ **Uses existing infrastructure** - Leverages `llm_client.py`, `mock_autocount_client.py`, `autocount_client.py`
✅ **Extensible** - Easy to add new agents or enhance existing ones
✅ **Automatic switching** - Seamlessly switches between mock and real data
✅ **Proper LLM integration** - Uses the OpenAI-compatible wrapper, not simplified httpx calls
✅ **Trigger-based routing** - Automatically routes to the right agent based on keywords
