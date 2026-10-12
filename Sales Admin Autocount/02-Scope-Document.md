# Scope Document
## AI Agent System for Office Admin & Sales Workflow — Wire Mesh Manufacturing

**Status:** Draft for review
**Version:** 0.1

---

## 1. Purpose

This document defines what is and is not included in this project, so that build effort, review, and expectations stay aligned as the system moves from design into implementation.

## 2. In-Scope

### Phase 1 — Foundation + highest-frequency agent
- SAP connectivity layer (`sap_client`) — exact interface pending SAP version/connection details.
- Staff-only access control (phone number allowlist) for the WhatsApp channel.
- Trigger detection (explicit prefix + keyword fallback) and acknowledgement messaging.
- Glossary/shortform reference table (initial seed set + growth process).
- SKU lookup/fuzzy-match layer against a SAP-synced product index.
- Token usage tracker with a budget stopper and alerting.
- **Stock & Quote Agent** — end to end.

### Phase 2 — Transactional documentation
- **Order-to-Invoice Agent**: chat-based and PO-PDF-based order capture (POs received via email or WhatsApp), price cross-check, admin approval flow, document delivery (WhatsApp to salesperson, email to customer with CC), versioned edit handling.
- **Email integration**: IMAP/POP3 connection to monitor incoming emails for customer POs; email is read-only for PO detection, agents do not send emails to customers except for approved documents.
- **Delivery address validation**: Automatic comparison of PO delivery address against SAP customer master data with customer classification logic (trading house vs non-trading house).
- **Non-PO order flow**: For orders without formal PO, agent retrieves SAP sales order format and issues to customer for confirmation/signature before proceeding with DO and invoicing.

### Phase 3 — Shipment
- **Shipment Agent**: pick/pack status check, salesperson delivery-timing confirmation, Delivery Order generation, 3PL/in-house shipment notice.

### Phase 4 — Customer onboarding
- **Customer Onboarding Agent**: PDF/SSM extraction, duplicate check, admin-reviewed draft, admin-executed SAP write.

### Phase 5 — Payment entry drafting
- **Payment Follow-up Agent**: extracts details from a payment transaction PDF forwarded by the salesperson/account admin and drafts the corresponding SAP entry. The accountant always performs the final confirmation after reconciling against actual bank records — this agent only removes manual data entry, not the reconciliation judgment call.

### Cross-cutting (spans all phases)
- WhatsApp coexistence setup (shared number between admin's app and the agent's API).
- Email monitoring setup (IMAP/POP3 connection for incoming customer POs).
- Confirmation-echo pattern on every financially/contractually meaningful action.
- Audit logging (price used, documents sent, versions, glossary changes, address validation flags).

## 3. Out of Scope

- **Automated price monitoring** — pricing stays a manually maintained reference table; no agent calculates or watches steel index movements.
- **Automated payment reconciliation/matching against bank records** — stays a fully manual accountant process; the agent only drafts the SAP entry from a submitted payment PDF (see Phase 5), it never confirms or clears a payment itself.
- **Central multi-tenant hosting / reselling to other companies** — parked as a future business direction with its own separately scoped architecture (gateway framework); not part of this build.
- **A shared WhatsApp group chat with the agent as a member** — not supported by the WhatsApp Business API; the coexistence model plus trigger detection is the accepted substitute.
- **A paid WhatsApp Solution Provider / inbox platform** — the design deliberately avoids this for cost and workflow-complexity reasons, in favor of a self-built webhook and keyword-trigger filter directly against Meta's Cloud API.

## 4. Deliverables

- Working Python service(s) implementing the five in-scope agents.
- SAP integration module, once connection details are confirmed.
- Glossary and SKU-index data stores, with an admin-usable maintenance process.
- WhatsApp webhook handler with trigger detection and staff allowlist.
- Email monitoring module (IMAP/POP3) for incoming customer PO detection.
- Delivery address validation logic with customer classification support.
- Usage-tracking/budget-stopper module.
- This document set (PRD, Scope, UI Specifications, SAD, Technical Specification) as the reference baseline.

## 5. Constraints

- **Pure Python implementation** — no third-party workflow/automation platform (e.g. n8n) is used, due to the confidentiality risk of routing business data through a third-party platform.
- **Self-hosted** — the service runs on infrastructure the business controls, not a SaaS platform.
- **No dedicated WhatsApp inbox/BSP product** — coexistence is implemented via Meta's Cloud API directly.
- **Email is read-only for PO detection** — agents do not send emails to customers directly except for approved invoice/quotation documents; email integration is for monitoring incoming POs only.
- SAP master-data writes (new customer accounts) may need to remain a manual admin action in SAP itself, depending on what the SAP setup's API permits.
- **Customer classification data** — SAP customer master data must include or be extended to include a trading house classification flag for address validation logic.

## 6. Assumptions

- The business will provide SAP version and connection details before Phase 1 implementation begins.
- Historical WhatsApp chat samples will be made available (anonymized as needed) to validate language handling and seed the glossary.
- The admin role continues to exist throughout all phases; scope items describing an eventual reduction in admin involvement (e.g. order-to-invoice going salesperson-direct) are a post-launch maturity step, not a v1 deliverable.

## 7. Roles & Responsibilities

| Role | Responsibilities |
|---|---|
| **Admin** | Approves drafts, resolves exceptions, maintains price table and glossary entries, performs final SAP writes for new customers, available on the shared WhatsApp number via coexistence |
| **Salesperson / Account admin** | Initiates all inquiries/orders via WhatsApp, forwards customer PDFs/POs, confirms delivery timing, forwards payment transaction PDFs |
| **Accountant** | Reconciles the agent-drafted payment entry against actual bank records and performs the final confirmation |
| **Developer/IT (build side)** | Implements agents, SAP integration, WhatsApp webhook, maintains infrastructure and budget controls |
| **SAP/Basis contact** | Confirms SAP version, exposes/authorizes the API interface needed, advises on master-data write permissions |

## 8. Change Control

Any addition to agent scope, trigger behavior, or automation level (e.g. removing the admin approval gate) should be logged as a scope change and reflected in this document and the PRD before being built, given the financial and data-confidentiality sensitivity of this system.
