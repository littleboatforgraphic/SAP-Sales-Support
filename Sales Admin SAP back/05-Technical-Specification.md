# Technical Specification
## AI Agent System for Office Admin & Sales Workflow — Wire Mesh Manufacturing

**Status:** Draft for review
**Version:** 0.1

---

## 1. Technology Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python | Chosen over n8n for control, testability, and to keep confidential data off third-party platforms |
| Web/webhook framework | FastAPI | Receives WhatsApp webhook events, exposes internal endpoints |
| SAP connectivity | `requests`/`httpx` (OData) **or** `pyrfc` (BAPI/RFC) | Depends on SAP version — pending confirmation |
| LLM | Ilmu Claw API (OpenAI-compatible via `openai` Python SDK) | Used only for extraction/drafting/judgment steps |
| Scheduling | `APScheduler` or cron | Polling tasks (e.g. shipment status) |
| Database | Postgres (production) / SQLite (pilot) | Order versions, price/glossary history, usage log, staff allowlist |
| Messaging | Meta WhatsApp Cloud API (direct) | Coexistence-enabled; no third-party BSP inbox product |
| Email (outgoing) | SMTP or a transactional email service | Customer-facing document delivery |
| Email (incoming) | IMAP/POP3 (`imaplib`, `poplib`) | PO detection and attachment extraction |
| PDF/document extraction | Ilmu Claw API (if supported) or alternative PDF processing | SSM documents, customer POs, company detail PDFs |

## 2. Module / File Structure

```
sap_client.py          # get_stock(), get_price_table(), create_sales_order(),
                        # create_invoice(), get_pick_pack_status(), create_delivery_order(),
                        # find_customer(), create_customer() [if API write is permitted],
                        # draft_payment_entry(), get_customer_addresses(),
                        # is_trading_house(customer_id)

glossary.py             # lookup(term) -> canonical SAP value | None
                        # propose_entry(term, canonical_value) -> pending approval
                        # approve_entry() / reject_entry() [admin-facing]

sku_index.py             # sync_from_sap() [scheduled], fuzzy_match(query) -> top candidates

price_table.py            # get_current_price(sku) — reads only, admin maintains via separate process

whatsapp_webhook.py        # FastAPI route: receives Meta Cloud API events
                        # - staff_allowlist.check(sender)
                        # - trigger.detect(message)
                        # - admin_takeover.check(conversation_id)

email_monitor.py          # IMAP/POP3 connection to monitor inbox for POs
                        # - connect_imap(), connect_pop3()
                        # - poll_emails(), detect_po_attachments()
                        # - extract_po_attachment()

trigger.py                # detect(message) -> "explicit" | "keyword" | None

address_validator.py      # validate_delivery_address(po_address, customer_id)
                        # - get_registered_addresses(customer_id)
                        # - is_trading_house(customer_id)
                        # - compare_addresses() -> match_result

llm_client.py             # get_llm_client(), chat_completion(), extract_text_from_pdf(),
                        # draft_message() - wrapper for Ilmu Claw API

agents/
  stock_quote_agent.py      # draft_quote()
  order_invoice_agent.py     # capture_from_chat(), capture_from_po_pdf(), draft_order(),
                            # cross_check_price(), validate_delivery_address(),
                            # version_edit(), on_admin_approve()
                            # handle_non_po_order() -> generate_so_for_signature()
  shipment_agent.py          # confirm_delivery_timing(), draft_delivery_order()
  onboarding_agent.py         # extract_from_pdf(), duplicate_check(), draft_customer_record()
  payment_agent.py             # extract_from_payment_pdf(), draft_sap_entry(),
                              # notify_accountant_for_reconciliation()

notifier.py               # send_whatsapp(to, message, attachment=None)
                        # send_email(to, cc, subject, body, attachment)

usage_tracker.py           # record_usage(), check_budget() — per-day/per-month stopper + alert

audit_log.py               # log_version(), log_price_used(), log_document_sent(), log_glossary_change(),
                        # log_address_validation()

scheduler.py               # periodic jobs: sku_index.sync_from_sap(), shipment status polling,
                        # email_monitor.poll_emails()

main.py                    # FastAPI app entrypoint
```

## 3. Data Models (illustrative — adjust field names to match SAP conventions)

```python
class StaffAllowlistEntry:
    phone_number: str
    name: str
    role: str          # "admin" | "salesperson" | "accountant"
    active: bool
    added_at: datetime
    added_by: str      # admin identifier who added this entry

class GlossaryEntry:
    term: str                  # as typed by salesperson, any language/shortform
    canonical_value: str        # matching SAP SKU/field value
    category: str               # "product_spec" | "unit" | "business_term" | "customer_specific"
    status: str                  # "pending" | "approved" | "rejected"
    created_from_conversation: str  # conversation ID for traceability
    usage_count: int             # number of times this term has been used, for prioritization
    last_used_at: datetime | None
    created_at: datetime
    approved_by: str | None       # admin identifier who approved/rejected
    approved_at: datetime | None

class SKUIndexEntry:
    sku: str
    description: str
    spec_attributes: dict
    last_synced_at: datetime
    active: bool                 # for soft-deleting discontinued products

class PriceReferenceEntry:
    sku: str
    price: float
    updated_by: str          # admin identifier
    updated_at: datetime
    effective_from: datetime   # for historical price tracking
    effective_to: datetime | None  # null if current price

class OrderRecord:
    reference: str            # e.g. "SO-2031"
    version: int              # incremented on every edit, never overwritten
    customer_id: str          # SAP customer number for reporting/audit
    customer_name: str        # denormalized for convenience
    items: list[dict]         # sku, qty, price_used, description
    total_amount: float        # calculated from items
    status: str                # "draft" | "pending_admin" | "approved" | "sent" | "cancelled"
    salesperson_thread_id: str
    salesperson_id: str       # staff identifier from allowlist
    created_at: datetime
    updated_at: datetime
    approved_by: str | None    # admin identifier who approved
    approved_at: datetime | None
    sent_via_whatsapp_at: datetime | None
    sent_via_email_at: datetime | None
    parent_version: int | None  # for version chain tracking
    edit_reason: str | None    # description of why edit was made

class UsageLogEntry:
    date: date
    input_tokens: int
    output_tokens: int
    cost_usd: float
    agent_name: str            # which agent made the call
    operation_type: str        # "extraction" | "drafting" | "interpretation"

class PaymentDraftEntry:
    reference: str              # e.g. "PMT-0456"
    source_pdf_ref: str          # traceability back to the forwarded document
    extracted_amount: float
    extracted_date: date
    extracted_payer_ref: str
    extracted_payer_name: str | None
    status: str                   # "drafted" | "reconciled_confirmed" | "rejected"
    confirmed_by: str | None       # accountant identifier, set only on confirmation
    confirmed_at: datetime | None
    created_at: datetime
    notes: str | None             # accountant's reconciliation notes

class ConversationState:
    conversation_id: str         # WhatsApp conversation identifier
    participant_phone: str      # salesperson's phone number
    active_agent: str | None     # currently engaged agent name
    last_agent_action_at: datetime | None
    admin_takeover_active: bool
    admin_takeover_started_at: datetime | None
    admin_takeover_ends_at: datetime | None
    pending_confirmation: dict | None  # awaiting YES/NO response
    created_at: datetime
    updated_at: datetime

class AuditLogEntry:
    id: str                     # unique log entry ID
    timestamp: datetime
    entity_type: str            # "order" | "glossary" | "payment" | "customer"
    entity_reference: str       # reference to the affected entity
    action: str                 # "created" | "updated" | "approved" | "sent" | "escalated"
    actor: str                  # system or staff identifier
    actor_type: str             # "agent" | "admin" | "salesperson" | "accountant"
    details: dict               # structured context (e.g., price_used, document_type)
    related_conversation_id: str | None

class AddressValidationResult:
    order_reference: str        # reference to the order being validated
    customer_id: str            # SAP customer ID
    po_delivery_address: str    # address extracted from PO
    registered_addresses: list[str]  # addresses from SAP customer master
    is_trading_house: bool      # customer classification from SAP
    match_found: bool           # whether PO address matches any registered address
    validation_level: str       # "match" | "trading_house_mismatch" | "high_risk_mismatch"
    requires_admin_approval: bool
    created_at: datetime
```

## 4. Trigger Detection Logic (pseudocode)

```python
def detect(message: str) -> str | None:
    normalized = message.strip().lower()

    if normalized.startswith(("ai", "agent", "ai agent")):
        return "explicit"

    for keyword in KEYWORD_LIST:  # sourced from glossary, kept specific to avoid false positives
        if keyword in normalized:
            return "keyword"

    return None
```

- `KEYWORD_LIST` should be reviewed to exclude words that double as ordinary conversation (e.g. a bare "order" is riskier than "sales order" or "new acc").
- On `"explicit"`, send the brief acknowledgement variant. On `"keyword"`, send the "noticed this looks like…" acknowledgement variant (see UI Specifications, Section 3).

## 5. Address Validation Logic (pseudocode)

```python
def validate_delivery_address(po_address: str, customer_id: str) -> AddressValidationResult:
    """Validate PO delivery address against SAP customer master data."""

    # Get customer classification and registered addresses from SAP
    customer_data = sap_client.get_customer_details(customer_id)
    is_trading_house = customer_data.get("is_trading_house", False)
    registered_addresses = customer_data.get("delivery_addresses", [])

    # Normalize and compare addresses
    po_normalized = normalize_address(po_address)
    registered_normalized = [normalize_address(addr) for addr in registered_addresses]

    # Check for match
    match_found = any(po_normalized == addr for addr in registered_normalized)

    if match_found:
        validation_level = "match"
        requires_admin_approval = False
    elif is_trading_house:
        # Trading house: proceed with caution, admin double-confirmation
        validation_level = "trading_house_mismatch"
        requires_admin_approval = True
    else:
        # Non-trading house: high-risk, escalate to admin
        validation_level = "high_risk_mismatch"
        requires_admin_approval = True

    return AddressValidationResult(
        order_reference="",
        customer_id=customer_id,
        po_delivery_address=po_address,
        registered_addresses=registered_addresses,
        is_trading_house=is_trading_house,
        match_found=match_found,
        validation_level=validation_level,
        requires_admin_approval=requires_admin_approval,
        created_at=datetime.now(timezone.utc)
    )

def normalize_address(address: str) -> str:
    """Normalize address for comparison (case-insensitive, remove punctuation)."""
    import re
    normalized = address.lower().strip()
    normalized = re.sub(r'[^\w\s]', '', normalized)  # Remove punctuation
    normalized = re.sub(r'\s+', ' ', normalized)  # Normalize whitespace
    return normalized
```

## 6. Email Monitoring Logic (pseudocode)

```python
class EmailMonitor:
    """Monitors email inbox for incoming customer POs."""

    def __init__(self, config: EmailConfig):
        self.imap_server = config.imap_server
        self.imap_port = config.imap_port
        self.username = config.username
        self.password = config.password
        self.folder = config.folder or "INBOX"
        self.po_sender_allowlist = config.po_sender_allowlist
        self.po_keywords = config.po_keywords or ["PO", "Purchase Order", "Order"]

    def connect(self):
        """Establish IMAP connection."""
        import imaplib
        self.mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
        self.mail.login(self.username, self.password)
        self.mail.select(self.folder)

    def poll_emails(self) -> list[dict]:
        """Poll for new emails and extract PO attachments."""
        result, data = self.mail.search(None, "UNSEEN")
        email_ids = data[0].split()

        detected_pos = []

        for email_id in email_ids:
            result, data = self.mail.fetch(email_id, "(RFC822)")
            raw_email = data[0][1]
            email_message = email.message_from_bytes(raw_email)

            # Check if sender is on allowlist
            sender = email_message["From"]
            if not self.is_allowed_sender(sender):
                continue

            # Check subject for PO keywords
            subject = email_message["Subject"]
            if not self.contains_po_keywords(subject):
                continue

            # Extract PO attachments
            attachments = self.extract_attachments(email_message)
            for attachment in attachments:
                if attachment["filename"].lower().endswith(".pdf"):
                    detected_pos.append({
                        "email_id": email_id,
                        "sender": sender,
                        "subject": subject,
                        "attachment": attachment,
                        "received_at": datetime.now(timezone.utc)
                    })

        return detected_pos

    def is_allowed_sender(self, sender: str) -> bool:
        """Check if sender email is on the PO allowlist."""
        return any(allowed in sender for allowed in self.po_sender_allowlist)

    def contains_po_keywords(self, subject: str) -> bool:
        """Check if subject contains PO-related keywords."""
        subject_lower = subject.lower()
        return any(keyword.lower() in subject_lower for keyword in self.po_keywords)

    def extract_attachments(self, email_message) -> list[dict]:
        """Extract PDF attachments from email."""
        attachments = []
        for part in email_message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue

            filename = part.get_filename()
            if filename and filename.lower().endswith(".pdf"):
                attachments.append({
                    "filename": filename,
                    "content": part.get_payload(decode=True)
                })

        return attachments
```

## 5. Confirmation-Echo Pattern (pseudocode)

```python
def draft_and_confirm(agent_output: dict, thread_id: str) -> None:
    summary = build_human_readable_summary(agent_output)
    send_whatsapp(thread_id, summary + "\nReply YES to confirm, or tell me what to change.")
    # agent does not proceed to the next step (SAP write, send) until an explicit
    # confirmation is received in a follow-up message
```

## 7. Edit / Versioning Logic

```python
def apply_edit(reference: str, edit_instruction: str) -> OrderRecord:
    current = get_latest_version(reference)
    updated = interpret_edit(current, edit_instruction)  # LLM call, scoped narrowly
    new_version = save_new_version(reference, updated)    # never overwrites current
    route_to_admin_approval(new_version)                   # re-enters approval flow
    return new_version
```

## 8. Error Handling & Escalation Rules

| Condition | Behavior |
|---|---|
| SAP call fails/times out | Do not guess or skip; notify salesperson/admin that a manual check is needed |
| No confident SKU match | Present top 2–3 candidates; escalate to admin if still unresolved |
| PO-stated price ≠ price table | Explicit flag, no silent resolution |
| PO delivery address ≠ registered (trading house) | Flag with caution message; proceed with admin double-confirmation |
| PO delivery address ≠ registered (non-trading house) | Flag as high-risk; escalate to admin for fraud prevention before proceeding |
| Order without PO | Generate SAP sales order for customer signature; do not proceed with DO/invoicing until signed order returned |
| Admin does not respond within a defined window | Reminder ping; escalate further if still unactioned |
| Scanned/low-quality PDF | Always requires admin confirmation before any SAP write |
| Unauthorized sender | Drop/log; no agent processing |
| Admin manually replies in a conversation | Agent suppresses further auto-action on that thread for a defined window |
| Payment PDF extracted | Always creates a `PaymentDraftEntry` with status `"drafted"` — never auto-sets `"reconciled_confirmed"`; only the accountant's explicit confirmation after bank reconciliation can do that |

## 9. WhatsApp Integration Specifics

- **Coexistence**: enables the admin's existing WhatsApp Business app and the agent's API access to share one phone number; set up via Meta's Embedded Signup flow directly (avoiding a paid Business Solution Provider inbox product, per project constraints).
- **Webhook payload handling**: every inbound and outbound (including admin-sent) message is delivered to the webhook; the handler is responsible for allowlist checks, trigger detection, and takeover detection as described in Section 4 and the SAD.
- **Throughput**: coexistence-enabled numbers carry a messages-per-second cap depending on setup — expected to be well above this business's volume, but worth confirming during setup.

## 10. Environment & Deployment

- Configuration (SAP credentials, Ilmu Claw API key, WhatsApp tokens, email IMAP credentials, database connection string) via environment variables or a secrets manager — never hardcoded or logged.
- Deployed on business-controlled infrastructure (cloud VM or on-prem), per the confidentiality constraint in the Scope Document.
- Recommended: containerize with Docker for consistency between environments, though not required for a pilot.

### Ilmu Claw API Configuration
```bash
ILMU_API_KEY=your_ilmu_api_key_here
ILMU_BASE_URL=https://api.ilmu.ai/v1
ILMU_MODEL=ilmu-mini-v3.3
```

### Email Configuration (for PO monitoring)
```bash
EMAIL_IMAP_SERVER=imap.example.com
EMAIL_IMAP_PORT=993
EMAIL_USERNAME=po-monitor@example.com
EMAIL_PASSWORD=email_password
EMAIL_FOLDER=INBOX
EMAIL_PO_SENDER_ALLOWLIST=customer1@example.com,customer2@example.com
EMAIL_PO_KEYWORDS=PO,Purchase Order,Order
```

## 11. Conversation State Management

### 11.1 Multi-Turn Interaction Pattern

The system must track conversation state across multiple messages within a WhatsApp thread to support:

- **Confirmation flows**: Agent sends a draft → salesperson replies YES/NO → agent proceeds
- **Clarification loops**: Agent asks "Did you mean X, Y, or Z?" → salesperson chooses → agent resolves
- **Edit sequences**: Salesperson requests edit → agent drafts version 2 → admin approves → agent sends

### 11.2 State Machine for Conversations

```python
class ConversationStateMachine:
    """Manages state transitions for a single conversation."""

    def handle_message(message: str, sender: str):
        current_state = get_conversation_state(conversation_id)

        if current_state.pending_confirmation:
            # User is responding to a confirmation
            if is_affirmative(message):
                proceed_with_action(current_state.pending_confirmation)
                clear_pending_confirmation()
            elif is_negative(message):
                cancel_pending_action()
                clear_pending_confirmation()
            else:
                # Treat as edit instruction or new request
                handle_edit_or_new_request(message)

        elif current_state.active_agent:
            # Agent is engaged, process within that agent's context
            current_state.active_agent.handle_message(message)

        elif detect_trigger(message):
            # New trigger detected, start agent flow
            dispatch_to_agent(message)

        else:
            # No trigger, normal conversation (ignore)
            pass
```

### 11.3 Admin Takeover Detection

```python
def detect_admin_takeover(message: WhatsAppMessage):
    """Detect when admin manually replies in a conversation."""
    if message.sender not in admin_allowlist:
        return False

    conversation = get_conversation_state(message.conversation_id)

    if conversation.active_agent and not conversation.admin_takeover_active:
        # Admin is taking over a conversation the agent was handling
        conversation.admin_takeover_active = True
        conversation.admin_takeover_started_at = now()
        conversation.admin_takeover_ends_at = now() + timedelta(minutes=30)
        conversation.active_agent = None  # disengage agent
        save_conversation_state(conversation)

        # Optional: send subtle notification to salesperson
        if notify_on_takeover_enabled:
            send_system_message(message.conversation_id,
                "Admin is now handling this conversation. Type 'AI take over' to hand back.")

    elif conversation.admin_takeover_active:
        # Admin continues typing in takeover mode
        if auto_extend_on_takeover:
            conversation.admin_takeover_ends_at = now() + timedelta(minutes=30)
            save_conversation_state(conversation)

    return True
```

### 11.4 Handoff Back to Agent

```python
def detect_handoff_to_agent(message: WhatsAppMessage):
    """Detect when admin or salesperson hands control back to the agent."""
    if message.content.lower() in handoff_phrases:
        conversation = get_conversation_state(message.conversation_id)
        conversation.admin_takeover_active = False
        conversation.admin_takeover_ends_at = None
        # Re-engage the last active agent or trigger detection on next message
        save_conversation_state(conversation)
        return True
    return False
```

### 11.5 Pending Confirmation Storage

```python
class PendingConfirmation:
    """Stores confirmation-echo context awaiting user response."""
    conversation_id: str
    confirmation_type: str        # "quote" | "order" | "delivery_timing" | "edit"
    draft_data: dict              # the structured data awaiting confirmation
    original_message: str         # what triggered this confirmation
    expires_at: datetime          # timeout if user doesn't respond
    created_at: datetime

def set_pending_confirmation(conversation_id: str, confirmation_type: str, draft_data: dict):
    """Store confirmation context and set timeout."""
    confirmation = PendingConfirmation(
        conversation_id=conversation_id,
        confirmation_type=confirmation_type,
        draft_data=draft_data,
        original_message=last_message,
        expires_at=now() + timedelta(hours=24),  # 24-hour timeout
        created_at=now()
    )
    save_pending_confirmation(confirmation)

def check_confirmation_timeout():
    """Clean up expired confirmations and notify if needed."""
    expired = get_expired_confirmations()
    for confirmation in expired:
        if confirmation.confirmation_type in ["order", "edit"]:
            # High-value confirmations: notify admin that this was abandoned
            notify_admin(f"Confirmation expired for {confirmation.confirmation_type} in conversation {confirmation.conversation_id}")
        delete_pending_confirmation(confirmation.id)
```

## 11. Testing Considerations

- Validate glossary/language handling against a sample of real historical WhatsApp chats before go-live.
- Test PDF extraction against real (anonymized) SSM documents and customer POs, including at least one scanned example to confirm the extra-caution path behaves correctly.
- Test the trigger keyword list against ordinary, non-business conversation to check for false positives before rollout.
- Test the SAP integration against a sandbox/test SAP instance before connecting to production data.
- Test conversation state management with multi-turn scenarios: confirmation flows, clarification loops, and edit sequences.
- Test admin takeover detection and handoff back to agent with real conversation patterns.
- Test retry logic by simulating transient failures (timeouts, rate limits) and verifying backoff behavior.
- Test rate limiting by sending burst traffic and verifying queue throttling works correctly.
- Test backup and recovery procedures by performing a test restore from a backup.

## 12. Retry Logic and Error Handling

### 11.1 Retry Strategy

```python
class RetryConfig:
    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True          # add randomness to avoid thundering herd

def should_retry(error: Exception, attempt: int) -> bool:
    """Determine if an error is retryable."""
    if attempt >= RetryConfig.max_attempts:
        return False

    # Retry on transient errors
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True

    # Retry on rate limit errors (HTTP 429)
    if hasattr(error, 'status_code'):
        retryable_statuses = [408, 429, 500, 502, 503, 504]
        return error.status_code in retryable_statuses

    # Do not retry on client errors (4xx except 429) or auth errors
    return False
```

### 11.2 Error Handling Rules

| Error Type | Behavior | Notification |
|---|---|---|
| SAP timeout | Retry with exponential backoff (max 3 attempts) | Notify admin/salesperson if all retries fail |
| SAP rate limit (429) | Retry with respect to Retry-After header or exponential backoff | Log warning, continue retrying |
| SAP auth error (401/403) | Fail immediately, do not retry | Alert admin immediately (credential issue) |
| SAP not found (404) | Fail immediately, do not retry | Escalate to admin for investigation |
| WhatsApp timeout | Retry with exponential backoff (max 3 attempts) | Log warning, continue retrying |
| WhatsApp rate limit (429) | Implement queue-based throttling, respect MPS limits | Log warning, queue messages |
| WhatsApp auth error (401/403) | Fail immediately, do not retry | Alert admin immediately (token issue) |
| Database connection error | Retry with exponential backoff (max 5 attempts) | Alert admin if persistent |
| LLM API timeout | Retry with exponential backoff (max 2 attempts) | Escalate to admin if all retries fail |
| LLM rate limit (429) | Implement queue-based throttling | Log warning, queue requests |

## 13. Rate Limiting and Throttling

### 12.1 WhatsApp Message Queue

```python
class WhatsAppMessageQueue:
    max_mps: int = 50            # messages per second limit (adjust based on Meta's coexistence tier)
    burst_window_seconds: int = 10
    burst_limit: int = 200       # max messages in burst window

    async def send_with_throttling(to: str, message: str, attachment: str | None):
        """Queue message and respect rate limits."""
        await self.acquire_permit()
        await self.whatsapp_client.send_message(to, message, attachment)
```

### 12.2 SAP API Rate Limiting

```python
class SAPRateLimiter:
    max_concurrent_requests: int = 10
    requests_per_second: int = 20
    circuit_breaker_threshold: int = 5  # consecutive failures before opening circuit
    circuit_breaker_timeout_seconds: int = 60

    async def execute_sap_call(func, *args, **kwargs):
        """Execute SAP call with rate limiting and circuit breaker."""
        await self.acquire_permit()
        if self.circuit_open:
            raise CircuitBreakerOpenError("SAP API temporarily unavailable")
        try:
            result = await func(*args, **kwargs)
            self.reset_failure_count()
            return result
        except Exception as e:
            self.increment_failure_count()
            raise
```

## 14. Backup and Disaster Recovery

### 13.1 Database Backup Strategy

- **Daily automated backups** at 2:00 AM local time
- **Retention period**: 90 days (configurable)
- **Backup types**:
  - Full backup: Sundays
  - Incremental backup: Monday-Saturday
- **Storage**: Separate storage volume from primary database, with replication to offsite location if available
- **Backup verification**: Automated integrity check after each backup completion

### 13.2 Reference Data Versioning

- Price table, glossary, and SKU index should have version history tables
- Point-in-time restore capability: `restore_price_table(as_of_date)`
- Before any bulk update (e.g., price table update by admin), automatic snapshot creation

### 13.3 File-Based Storage Backup

- Document attachments (PDFs, invoices) stored with versioning
- Backup includes:
  - Original uploaded documents (POs, SSM registrations, payment PDFs)
  - Generated documents (SAP invoices, delivery orders)
  - Backup retention matches database retention (90 days)

### 13.4 Recovery Procedures

| Scenario | Recovery Time Objective (RTO) | Recovery Point Objective (RPO) |
|---|---|---|
| Database corruption | 4 hours | 24 hours (from last good backup) |
| Server failure | 2 hours | 1 hour (from replicated storage) |
| Accidental data deletion | 1 hour | Point-in-time (before deletion) |
| Ransomware attack | 24 hours | From offline backup (last known clean) |

## 15. Admin-Takeover Window Configuration

### 14.1 Default Configuration

```python
class AdminTakeoverConfig:
    default_window_minutes: int = 30
    max_window_minutes: int = 1440  # 24 hours maximum
    auto_extend_on_activity: bool = True   # extend window if admin continues typing
    handoff_phrases: list[str] = [
        "AI take over",
        "Agent take over",
        "You handle this"
    ]
```

### 14.2 Window Behavior

- When admin manually replies in a conversation, `admin_takeover_active` is set to `True`
- `admin_takeover_ends_at` is set to `now + default_window_minutes`
- If `auto_extend_on_activity` is enabled, any admin reply within the window extends it by `default_window_minutes`
- Salesperson or admin can explicitly hand back control using handoff phrases
- Window expires automatically at `admin_takeover_ends_at`
- Configurable per deployment in environment variables or settings table

### 14.3 Notification to Salesperson

When admin takes over, a subtle system message can be sent (optional):
> "Admin is now handling this conversation. Type 'AI take over' to hand back to the agent."

This notification is configurable and can be disabled if preferred.

## 15. Open Technical Questions

- SAP version and whether OData or RFC/BAPI is the available interface.
- Whether SAP permits API writes for customer master data, or whether onboarding's final step must stay a manual SAP GUI action.
- Exact per-day/per-month token budget figures for the usage stopper.
- Final keyword trigger list (English + Malay + shortforms), to be refined from real chat samples.
- WhatsApp coexistence tier and exact MPS limits for the deployed region.
- Backup storage location and infrastructure (cloud storage vs. on-prem NAS).
- Database choice confirmation for production (Postgres vs. other SQL database).
- Ilmu Claw actual pricing for ilmu-mini-v3.3 model (update INPUT_PRICE_PER_M and OUTPUT_PRICE_PER_M in usage_tracker.py).
- Ilmu Claw PDF processing capabilities (whether it supports file uploads directly or requires text conversion).
