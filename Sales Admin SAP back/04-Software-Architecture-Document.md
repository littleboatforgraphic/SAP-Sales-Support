# Software Architecture Document (SAD)
## AI Agent System for Office Admin & Sales Workflow — Wire Mesh Manufacturing

**Status:** Draft for review
**Version:** 0.1

---

## 1. Architectural Goals

- Keep all confidential business data inside infrastructure the business controls — no third-party workflow/automation platform in the data path.
- Give agents access to just enough SAP and reference data to act, without duplicating SAP as a system of record.
- Make it straightforward to add human confirmation/approval steps anywhere in the flow, since this system deliberately keeps a human in the loop for financially or contractually meaningful actions.
- Support future extension into a multi-client, resold product (see Section 8) without a fundamental redesign.

## 2. High-Level Architecture

```
                         ┌───────────────────────────┐
   WhatsApp (coexistence)│    Meta Cloud API webhook  │
   salesperson + admin ──┤                            │
   share one number      └──────────────┬─────────────┘
                                         │
                           ┌─────────────┴─────────────┐
                           ▼                           ▼
         ┌───────────────────────────┐  ┌───────────────────────────┐
         │  Webhook Handler            │  │  Email Monitor            │
         │  - staff allowlist check    │  │  - IMAP/POP3 connection   │
         │  - trigger detection         │  │  - PO detection           │
         │  - admin-takeover detection   │  │  - Attachment extraction  │
         └──────────────┬─────────────┘  └──────────────┬─────────────┘
                                         │                       │
                                         └───────────┬───────────┘
                                                     │
                                                     ▼
                         ┌───────────────────────────┐
                         │  Agent Orchestration Layer  │
                         │  - Stock & Quote Agent       │
                         │  - Order-to-Invoice Agent    │
                         │  - Shipment Agent            │
                         │  - Customer Onboarding Agent │
                         │  - Payment Follow-up Agent   │
                         └───┬───────────┬────────────┘
                             │           │
              ┌──────────────┘           └───────────────┐
              ▼                                           ▼
   ┌─────────────────────┐                    ┌─────────────────────┐
   │ Reference Data Layer │                    │  SAP Integration     │
   │ - Price table         │                    │  Layer                │
   │ - Glossary             │◄──────────────────┤  (sap_client)          │
   │ - SKU index (SAP sync) │                    │  OData / RFC — TBD    │
   │ - Customer classification│                    │  - Customer master     │
   └─────────────────────┘                    │  - Address validation  │
              │                                 └─────────────────────┘
              ▼                                           │
   ┌─────────────────────┐        ┌─────────────────────┐
   │  Audit / Data Store   │        │  Notifier             │
   │  (Postgres/SQLite)     │        │  - WhatsApp send        │
   │  - order versions       │        │  - Email send (customer) │
   │  - price-used log        │        │  - Rate-limited queue   │
   │  - usage/cost log          │        └─────────────────────┘
   │  - conversation state     │
   │  - address validation log │
   └─────────────────────┘
              │
              ▼
   ┌─────────────────────┐        ┌─────────────────────┐
   │  Retry & Error        │        │  Rate Limiting        │
   │  Handling Layer        │        │  Layer                 │
   │  - Exponential backoff │        │  - WhatsApp MPS control│
   │  - Circuit breaker     │        │  - SAP API throttling  │
   │  - Transient vs non-   │        │  - LLM request queue   │
   │    transient errors    │        └─────────────────────┘
   └─────────────────────┘
              │
              ▼
   ┌─────────────────────┐
   │  Backup & Recovery   │
   │  Layer                │
   │  - Daily DB backups   │
   │  - Data versioning    │
   │  - File storage backup│
   └─────────────────────┘
```

## 3. Components

### 3.1 Webhook Handler
- Receives every synced message from the shared WhatsApp number (coexistence delivers both salesperson-sent and admin-sent messages here).
- Checks sender against the **staff allowlist** before any further processing — unauthorized numbers are dropped/logged, never reach the agent layer.
- Runs **trigger detection**: explicit prefix match, then keyword fallback match against the glossary-derived keyword list.
- Detects admin manual replies (synced outgoing messages) to suppress agent auto-action on a conversation the admin has taken over.

### 3.1.1 Email Monitor
- Monitors configured email inbox(es) via IMAP/POP3 for incoming customer POs.
- Detects PO attachments (PDF) based on sender allowlist and subject/content keywords.
- Extracts PO PDFs and passes them to the Order-to-Invoice Agent for processing.
- Email is read-only for PO detection; agents do not send conversational emails to customers.
- Logging of all PO detections and processing for audit trail.

### 3.2 Agent Orchestration Layer
- One module per agent (Stock & Quote, Order-to-Invoice, Shipment, Customer Onboarding, Payment Follow-up).
- Each agent follows the same internal shape: capture → resolve (glossary/SKU/SAP lookup) → confirmation-echo → (admin approval where required) → act (SAP write / document send) → log.
- LLM calls (Ilmu Claw API) are used only for the judgment/drafting parts — extraction, drafting messages, interpreting edit instructions — not for deterministic lookups.

### 3.3 Reference Data Layer
- **Price table**: admin-maintained, read-only to agents. No agent calculates or monitors price.
- **Glossary**: shortform/business-term → canonical SAP value mapping, many-to-one, with a pending/approved state for new entries proposed by agents.
- **SKU index**: a local, periodically-synced cache of SAP's product/material master, used for fast fuzzy matching before falling back to a live SAP query.
- **Customer classification**: SAP customer master data includes a trading house classification flag; this is cached locally for address validation logic.

### 3.4 SAP Integration Layer (`sap_client`)
- Exact interface depends on SAP version — OData (S/4HANA) or BAPI/RFC via `pyrfc` (ECC) — **pending confirmation**.
- Exposes functions such as: stock lookup, sales order/invoice creation, warehouse pick/pack status, customer master lookup/duplicate-check, customer classification retrieval, address validation against registered addresses, and (where permitted) customer master creation.
- Treated as the system of record — the local SKU index and any cached data are conveniences, not replacements.

### 3.5 Audit / Data Store
- Persists order/quote versions (every edit is a new version, not an overwrite), the price used at time of each transaction, glossary change history, document-send logs, and address validation results (for fraud prevention audit trail).
- Also holds the token-usage log described in Section 6.

### 3.6 Notifier
- Sends finalized documents to the salesperson (WhatsApp) and customer (email, with CC list).
- Keeps delivery channel logic separate from drafting logic, so a channel change (e.g. adding SMS later) doesn't touch agent code.
- Implements rate-aware throttling via an outbound message queue to respect WhatsApp MPS limits.

### 3.7 Retry and Error Handling Layer
- Implements exponential backoff retry logic for transient failures (timeouts, rate limits, temporary network issues).
- Distinguishes between retryable errors (5xx, 429, timeouts) and non-retryable errors (4xx auth, 400 bad request).
- Integrates with the audit log to track retry attempts and failures for observability.

### 3.8 Rate Limiting Layer
- WhatsApp message queue with configurable MPS (messages per second) limits and burst window controls.
- SAP API rate limiter with circuit breaker pattern to prevent cascade failures during SAP outages.
- LLM API request queue to respect rate limits and implement token budget enforcement.

### 3.9 Backup and Recovery Layer
- Automated daily database backups with 90-day retention (full + incremental).
- Reference data versioning (price table, glossary, SKU index) with point-in-time restore capability.
- File-based storage backup for document attachments and generated PDFs.
- Separate storage volume from primary database with offsite replication if available.

## 4. Deployment Architecture

- Runs on infrastructure the business controls — a self-managed cloud VM or on-prem server, not a third-party SaaS/workflow platform.
- If SAP is on-prem, the service reaches it via VPN or an internal network path; if hosted, via a secured API gateway/Cloud Connector as appropriate.
- WhatsApp integration goes directly against Meta's Cloud API (no paid Business Solution Provider inbox platform in the path), consistent with the project's cost and confidentiality constraints.
- Scheduling (e.g. shipment status polling, future payment-status polling if revisited) via a simple cron/APScheduler process alongside the main service.

## 5. Data Flows (summary)

1. **Quote flow**: Salesperson message → trigger detected → SKU/glossary resolve → SAP stock + price-table read → confirmation-echo → send quote.
2. **Order-to-invoice flow (chat-based)**: Chat confirmation → SKU/price resolve → confirmation-echo → admin approval → SAP SO/invoice draft → document fetch → send to salesperson (WhatsApp) + customer (email).
3. **Order-to-invoice flow (PO-based)**: PO received via email or WhatsApp → extraction → SKU/price resolve and cross-check → **address validation against SAP customer master** → confirmation-echo (with address validation results) → admin approval (escalated if address mismatch) → SAP SO/invoice draft → document fetch → send to salesperson (WhatsApp) + customer (email).
4. **Order-to-invoice flow (non-PO)**: Order initiated without PO → agent retrieves SAP sales order format → issues to customer for signature → customer signs and returns → agent proceeds with DO and invoicing.
5. **Shipment flow**: Triggered post-invoice-approval → salesperson delivery-timing confirmation → SAP pick/pack check → Delivery Order → shipment notice (in-house/3PL) → exceptions to admin.
6. **Customer onboarding flow**: PDF received → extraction → duplicate check against SAP → admin review against source PDF → admin performs SAP write.
7. **Payment follow-up flow**: Payment transaction PDF forwarded by salesperson/account admin → extraction → draft SAP entry prepared → accountant reconciles against bank records → accountant confirms (agent never auto-confirms a payment).

## 6. Security & Confidentiality

- **Confidentiality principle**: no business or customer data is processed by a third-party workflow platform — this is the reason pure Python was chosen over n8n, and why the WhatsApp integration avoids a paid inbox/BSP product.
- **Staff-only access**: phone-number allowlist checked before any message reaches the agent layer.
- **Credential handling**: SAP credentials and the Ilmu Claw API key are stored in environment variables/secrets manager, never in prompts or logs.
- **Cost/abuse control**: usage-tracking module enforces a per-day/per-month token budget stopper with alerting, checked before each LLM call.
- **Human-in-the-loop gates**: order-to-invoice and customer onboarding both require admin confirmation before anything is written to SAP or sent externally, in v1. Payment follow-up carries the same principle in its strictest form — the agent's drafted entry is never self-confirming; only the accountant's bank reconciliation finalizes it.

## 7. Non-Functional Considerations

- **Resilience**: SAP or WhatsApp API failures should fail safely — the agent should not guess or silently skip a step; it should notify admin/salesperson that something needs manual attention.
- **Observability**: every agent action (lookup, draft, send, escalation) should be logged with enough context to reconstruct what happened, given the audit requirements around pricing and documentation.
- **Retry logic**: transient failures (timeouts, rate limit errors, temporary network issues) should trigger an exponential backoff retry mechanism with configurable max attempts and timeout thresholds. Non-transient errors (401 unauthorized, 403 forbidden, 400 bad request) should fail immediately without retry.
- **Rate limiting**: WhatsApp coexistence numbers have messages-per-second (MPS) limits; the webhook handler should implement an outbound message queue with rate-aware throttling to avoid API rejections. SAP API calls should also respect rate limits and implement appropriate queuing.
- **Backup and disaster recovery**: the audit database should have daily automated backups with retention of at least 90 days. Reference data (price table, glossary, SKU index) should be versioned and have point-in-time restore capability. Backup strategy should include both the database and any file-based storage (document attachments, PDF sources).
- **Admin-takeover window duration**: when the admin manually replies in a conversation, the agent suppresses further auto-action for a configurable window (default: 30 minutes). This window can be reset early if the admin explicitly signals handoff back to the agent (e.g., "AI take over"). The duration should be configurable per deployment to match business needs.

## 8. Future Extension — Multi-Tenant / Resale Architecture

Parked as a future business direction, not part of this build: a central **AI Gateway** service that proxies LLM calls for multiple client deployments (each client's agents customized and hosted on their own VM, per-client usage metered centrally for billing). This SAD's component boundaries (LLM calls isolated from SAP/business logic) are deliberately structured so that extension would mean swapping the LLM-calling code to route through a gateway, without redesigning the agent orchestration or SAP integration layers.
