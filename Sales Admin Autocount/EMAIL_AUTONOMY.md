# Email Agent Autonomy Framework

## Overview

The email agent supports three autonomy phases that can be configured via settings:

1. **Shadow Mode** - Agent drafts, admin handles manually (measure accuracy)
2. **Assisted Mode** - Admin approves with one click, agent executes
3. **Selective Autonomy** - Agent auto-submits safe orders

## Configuration

### Autonomy Mode

Set in `.env`:
```bash
EMAIL_AUTONOMY_MODE=shadow  # Options: shadow, assisted, selective_autonomy
```

### Selective Autonomy Criteria

```bash
# Maximum order amount for auto-submit (RM)
EMAIL_AUTO_SUBMIT_MAX_AMOUNT=10000.0

# Only allow auto-submit for repeat customers
EMAIL_AUTO_SUBMIT_REPEAT_CUSTOMER=true

# Allow auto-submit for trading houses
EMAIL_AUTO_SUBMIT_TRADING_HOUSE_ALLOWED=false
```

## Autonomy Modes

### Phase 1: Shadow Mode

**Purpose**: Measure agent accuracy while admin handles emails manually.

**Behavior**:
- Agent extracts order and creates draft in AutoCount
- Agent prepares reply but doesn't send it
- Admin reviews draft and handles email manually
- Admin reports their action (submit/modify/reject)
- System compares agent draft with admin action
- Accuracy metrics are calculated and logged

**Admin Workflow**:
1. Agent creates draft in AutoCount
2. Admin reviews draft in AutoCount
3. Admin decides to submit, modify, or reject
4. Admin reports action via API:
   ```bash
   POST /api/v1/admin/report-admin-action
   {
     "user_id": "123456789",
     "draft_ref": "msg_id",
     "action": "submit",
     "admin_doc_number": "INV-2026-00123"
   }
   ```
5. System calculates accuracy score

**Accuracy Metrics**:
- Perfect match (1.0): Agent doc number = Admin doc number
- Partial match (0.5): Both created but different docs
- No match (0.0): Admin submitted but agent didn't draft, or admin rejected

**Use Case**: Initial deployment to build trust and measure performance.

### Phase 2: Assisted Mode

**Purpose**: Admin approves with one click, agent executes.

**Behavior**:
- Agent extracts order and creates draft in AutoCount
- Agent prepares reply but doesn't send it
- Admin reviews draft in admin panel
- Admin clicks "Approve & Submit" button
- Agent submits the draft in AutoCount
- Agent sends acknowledgement email to client

**Admin Workflow**:
1. Agent creates draft in AutoCount
2. Admin reviews draft in admin panel
3. Admin clicks "Approve & Submit"
4. Agent submits draft in AutoCount
5. Agent sends acknowledgement to client

**Use Case**: Building trust with guided approval before full autonomy.

### Phase 3: Selective Autonomy

**Purpose**: Agent auto-submits safe orders without human intervention.

**Behavior**:
- Agent extracts order and creates draft in AutoCount
- Agent checks autonomy criteria
- If criteria met: Agent submits draft in AutoCount automatically
- If criteria not met: Draft goes to admin queue for review
- Agent sends acknowledgement to client

**Autonomy Criteria**:
All must be true for auto-submit:
- Customer is matched (not uncertain or no_match)
- Customer is a repeat customer (has previous orders)
- Order amount ≤ threshold (default: RM 10,000)
- Customer is not a trading house (unless allowed)
- No block flags
- High extraction confidence

**Admin Workflow**:
1. Agent processes email
2. For safe orders: Auto-submitted, admin notified
3. For unsafe orders: Draft in queue, admin reviews and submits

**Use Case**: Full autonomy for low-risk, repeat customers.

## Autonomy Criteria Details

### Order Amount Threshold

Orders above this threshold always require admin approval:
```bash
EMAIL_AUTO_SUBMIT_MAX_AMOUNT=10000.0  # RM 10,000
```

### Repeat Customer Only

Only customers with previous orders can be auto-submitted:
```bash
EMAIL_AUTO_SUBMIT_REPEAT_CUSTOMER=true
```

The system checks the audit log for previous successful orders from the same customer.

### Trading House Exclusion

Trading houses are excluded from auto-submit by default:
```bash
EMAIL_AUTO_SUBMIT_TRADING_HOUSE_ALLOWED=false
```

Trading houses require extra verification due to reselling risks.

## API Endpoints

### Report Admin Action (Shadow Mode)

```bash
POST /api/v1/admin/report-admin-action
```

**Request Body**:
```json
{
  "user_id": "123456789",
  "draft_ref": "msg_id",
  "action": "submit",
  "admin_doc_number": "INV-2026-00123"
}
```

**Actions**:
- `submit` - Admin submitted the order
- `modify` - Admin modified the draft before submitting
- `reject` - Admin rejected the order

**Response**:
```json
{
  "draft_ref": "msg_id",
  "agent_doc_number": "INV-2026-00123",
  "admin_action": "submit",
  "admin_doc_number": "INV-2026-00123",
  "doc_numbers_match": true,
  "accuracy_score": 1.0
}
```

### View Drafts with Autonomy Info

```bash
GET /api/v1/admin/drafts?user_id=123456789
```

**Response includes**:
- `autonomy_mode` - Mode in effect when draft was created
- `autonomy_decision` - "auto_submit" or "require_approval"
- `autonomy_reason` - Why decision was made

## Audit Trail

All autonomy decisions are logged in the audit log:

```json
{
  "entity_type": "email_po",
  "entity_id": "msg_id",
  "action": "autonomy_decision",
  "details": {
    "decision": "auto_submit",
    "reason": "Meets all criteria",
    "mode": "selective_autonomy",
    "timestamp": "2026-10-13T10:00:00Z"
  }
}
```

Shadow mode accuracy measurements are also logged:

```json
{
  "entity_type": "email_po",
  "entity_id": "msg_id",
  "action": "accuracy_measurement",
  "details": {
    "agent_draft_created": true,
    "agent_doc_number": "INV-2026-00123",
    "admin_action": "submit",
    "admin_doc_number": "INV-2026-00123",
    "doc_numbers_match": true,
    "accuracy_score": 1.0
  }
}
```

## Migration Between Phases

### Shadow → Assisted

1. Change autonomy mode:
   ```bash
   EMAIL_AUTONOMY_MODE=assisted
   ```

2. Add approval UI to admin panel
3. Update admin workflow to use one-click approval

### Assisted → Selective Autonomy

1. Change autonomy mode:
   ```bash
   EMAIL_AUTONOMY_MODE=selective_autonomy
   ```

2. Configure autonomy criteria
3. Monitor auto-submitted orders
4. Adjust thresholds based on performance

## Monitoring

### Key Metrics

**Shadow Mode**:
- Accuracy score over time
- Agent draft vs admin submission match rate
- Rejection rate (how often admin rejects agent draft)

**Assisted Mode**:
- Approval rate (how often admin approves)
- Modification rate (how often admin modifies before approval)
- Processing time (time from email to approval)

**Selective Autonomy**:
- Auto-submit rate (percentage of orders auto-submitted)
- Admin queue rate (percentage requiring review)
- Error rate (auto-submit failures)

### Alerts

- Low accuracy score (< 0.7) in shadow mode
- High rejection rate (> 30%) in assisted mode
- High error rate (> 5%) in selective autonomy
- Unusual pattern (sudden drop in auto-submit rate)

## Example Scenarios

### Shadow Mode Example

**Email**: PO-2026-001 from ABC Trading, RM 5,000

**Agent Action**:
- Creates AR Invoice draft #INV-2026-00123
- Notifies admin

**Admin Action**:
- Reviews draft in AutoCount
- Submits it as #INV-2026-00123 (same as agent)
- Reports action via API

**Result**: Accuracy score = 1.0 (perfect match)

### Assisted Mode Example

**Email**: PO-2026-002 from XYZ Construction, RM 8,000

**Agent Action**:
- Creates AR Invoice draft #INV-2026-00124
- Notifies admin with approval link

**Admin Action**:
- Clicks "Approve & Submit" in admin panel
- Agent submits #INV-2026-00124
- Agent sends acknowledgement to client

### Selective Autonomy Example

**Email**: PO-2026-003 from ABC Trading (repeat customer), RM 3,000

**Agent Action**:
- Checks criteria: Repeat ✓, Amount ✓, Not trading house ✓
- Creates AR Invoice draft #INV-2026-00125
- Auto-submits in AutoCount
- Sends acknowledgement to client
- Notifies admin of auto-submit

**Email**: PO-2026-004 from New Customer Ltd, RM 15,000

**Agent Action**:
- Checks criteria: New customer ✗
- Creates AR Invoice draft #INV-2026-00126
- Does NOT auto-submit (fails criteria)
- Adds to admin queue
- Notifies admin for review

## Best Practices

### Shadow Mode
- Run for at least 100 orders before moving to assisted mode
- Target accuracy score > 0.8 before progression
- Review rejected drafts to understand patterns
- Adjust extraction prompts based on common errors

### Assisted Mode
- Monitor modification rate - high rate indicates extraction issues
- Target approval rate > 90% before moving to selective autonomy
- Track processing time - should be < 5 minutes
- Ensure admin panel is user-friendly

### Selective Autonomy
- Start with conservative thresholds (e.g., RM 5,000)
- Monitor auto-submit rate (target: 30-50% initially)
- Review auto-submitted orders for errors
- Gradually increase thresholds as confidence grows
- Keep high-value orders (> RM 50,000) in admin queue

## Troubleshooting

### Issue: Low accuracy in shadow mode
- Check extraction prompts - are they clear?
- Review rejected drafts - what patterns?
- Verify customer matching accuracy
- Check PDF extraction quality

### Issue: High modification rate in assisted mode
- Review what admins are modifying
- Common modifications indicate extraction issues
- Update extraction logic for common patterns
- Improve data validation

### Issue: Auto-submit errors in selective autonomy
- Check AOTG API connection
- Verify draft data structure
- Review auto-submit criteria - too lenient?
- Check error logs for specific failures

### Issue: Too many orders in admin queue
- Lower autonomy thresholds temporarily
- Review why orders fail criteria
- Improve customer matching
- Adjust trading house detection

## Future Enhancements

- **Dynamic thresholds**: Adjust thresholds based on accuracy
- **Learning**: Learn from admin modifications to improve extraction
- **Customer-specific policies**: Different rules per customer
- **Time-based autonomy**: Increase autonomy over time with good performance
- **Escalation**: Auto-escalate stuck orders to admin
- **Analytics dashboard**: Visualize autonomy metrics over time
