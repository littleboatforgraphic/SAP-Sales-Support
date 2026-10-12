# Product Requirements Document (PRD)
## AI Agent System for Office Admin & Sales Workflow — Wire Mesh Manufacturing

**Status:** Draft for review
**Version:** 0.1

---

## 1. Overview

The business manufactures wire mesh steel products and runs its production, warehouse, and sales operations through SAP, tracking inventory end to end. Office admins currently handle every stage of the sales cycle manually for each salesperson: checking stock, documenting sales, issuing invoices, arranging shipment, communicating price changes, and following up on payment.

This product introduces a set of AI agents that take over the repetitive, well-defined parts of that workflow, while keeping admins and salespeople in control of judgment calls, exceptions, and anything involving money or commitments to a client.

## 2. Problem Statement

One admin can currently support only a small number of salespeople, because most of their time goes into repetitive lookups and manual documentation rather than judgment-based work. Wire mesh pricing also floats with the steel market, so admins must manually track and communicate price context on every order. As the business grows, this ratio doesn't scale without adding headcount.

## 3. Goals & Objectives

- Increase the number of salespeople one admin can support, by automating repetitive lookup, documentation, and reminder tasks.
- Keep a human decision-maker (admin, later salesperson) in the loop for anything that commits the company financially or contractually.
- Preserve data confidentiality — no business or customer data is processed by third-party workflow platforms.
- Build a system that tolerates real-world daily communication (mixed English/Malay, shortforms, PDFs, inconsistent phrasing) without silently making costly mistakes.

## 4. Users / Personas

| Persona | Role in the system |
|---|---|
| **Office Admin** | Approves agent drafts, resolves exceptions, maintains the price table and glossary, does final SAP writes for new customer accounts, watches live conversations via WhatsApp coexistence |
| **Salesperson** | Initiates all customer-facing inquiries and order confirmations via WhatsApp; receives quotes, invoices, and shipment updates; forwards customer POs and PDFs |
| **Customer** (indirect) | Provides POs, company registration PDFs, and receives invoices via email; does not interact with the agents directly |

## 5. Scope of Agents (v1)

| # | Agent | Trigger | Admin involvement |
|---|---|---|---|
| 1 | **Stock & Quote Agent** | Salesperson inquiry (explicit prefix or keyword) | None by default; escalates on stock shortfall or non-standard spec |
| 2 | **Order-to-Invoice Agent** | Salesperson confirms order, or forwards a customer PO (PDF) | Approves each draft initially; planned to shift to salesperson-direct once stable |
| 3 | **Shipment Agent** | Triggered after invoice approval | Confirms delivery timing with salesperson before generating Delivery Order; exceptions escalate to admin |
| 4 | **Customer Onboarding Agent** | New customer PDF/SSM document received | Admin always does the final SAP write |
| 5 | **Payment Follow-up Agent** | Payment transaction PDF forwarded by salesperson/account admin | Agent drafts the SAP entry only; accountant always confirms after reconciling with bank records |

Price maintenance is **not** an automated agent — the admin updates a shared price reference table manually, since steel-indexed pricing changes only every few months. Agents read from this table; none of them calculate or monitor it.

## 6. Functional Requirements

### 6.1 Stock & Quote Agent
- Detects a trigger (explicit `AI:` / `Agent:` prefix, or keyword fallback).
- Sends a brief acknowledgement identifying what it understood, before completing the lookup.
- Queries SAP stock for the requested SKU (resolved via the glossary/SKU-matching layer — see Technical Specification).
- Reads current price from the admin-maintained price reference table.
- Drafts a quote message back to the salesperson.
- Escalates to admin on: stock shortfall, non-standard spec, or unresolved SKU term.

### 6.2 Order-to-Invoice Agent
- Accepts input from three paths: chat-confirmed order, customer PO received via email, or customer PO forwarded via WhatsApp (PDF).
- Extracts structured order data (items, quantities, prices, delivery terms, delivery address) from PO PDFs.
- **Delivery address validation**: Compares PO delivery address against registered delivery addresses in SAP customer master data.
  - If customer is classified as a **trading house**: Trading houses frequently use different/new delivery addresses. Agent proceeds with caution and flags to admin for double-confirmation.
  - If customer is **not a trading house**: Any delivery address that differs from registered addresses is flagged as high-risk and escalated to admin for fraud prevention.
- Cross-checks any PO-stated price against the current price table and flags mismatches rather than silently choosing one.
- Matches item descriptions to SAP SKUs via the glossary/fuzzy-match layer; asks for confirmation on low-confidence or unresolved terms.
- **Orders without PO**: For orders initiated without a formal PO, the agent retrieves the sales order format from SAP and issues it to the customer for confirmation and signature before proceeding with Delivery Order and invoicing.
- Drafts the SAP sales order and invoice (documents are generated by SAP itself — the agent fetches and attaches them, it does not generate them).
- Requires admin approval before sending (v1). Planned: once stable, admin approval is removed and the agent sends directly to the salesperson.
- On approval, sends the SO/invoice/quotation documents via WhatsApp to the salesperson, and via email to the customer (customer-provided address, with CC list), primarily for e-invoice documentation purposes.
- Treats every customer-requested edit as a **new version** of the record (e.g. `SO-2031-v2`), never overwriting — older versions are retained for reference and re-enter the same approval flow.

### 6.3 Shipment Agent
- Triggers after invoice approval.
- Checks SAP warehouse pick/pack status.
- **Confirms delivery timing with the salesperson before generating the Delivery Order** — different clients have different delivery timelines, so this cannot be assumed.
- Prepares the Delivery Order and shipment notice (in-house driver or 3PL).
- Escalates partial shipments or packing exceptions to admin.

### 6.4 Customer Onboarding Agent
- Triggered when a new customer's company details (PDF, often an SSM registration document) are received.
- Extracts structured fields: company name, registration number, address, contact details, bank details if present.
- Checks for a likely duplicate against existing SAP customers before proceeding.
- Presents the extracted draft alongside the source PDF for admin review.
- **Admin always performs the final write into SAP** — this is not automated, given the higher risk of errors in master data versus transactional data.

### 6.5 Payment Follow-up Agent
- Triggered when a salesperson or account admin forwards a payment transaction file (PDF) to the agent.
- Extracts the payment details (amount, date, reference, payer) from the document.
- Drafts the corresponding entry in SAP — this is a **draft only**; the agent never confirms or clears a payment on its own.
- The accountant reconciles the draft against the actual bank records and performs the final confirmation. This keeps the one genuinely risky step (treating a document as proof of payment) a human judgment call, while removing the manual data-entry work.
- Treated with the same extra caution as other document-extraction agents: a scanned or low-quality payment PDF should be flagged rather than assumed accurate.

### 6.6 Cross-cutting requirements (apply to all agents)
- **Confirmation-echo**: before finalizing any action with financial or contractual weight, the agent restates what it understood in plain language and waits for confirmation.
- **Low-confidence handling**: on vague or low-confidence input (including language/shortform ambiguity), the agent confirms with the salesperson *and* flags to admin as a precaution.
- **Glossary-driven term resolution**: a living glossary maps shortforms/business terms (English and Malay) to canonical SAP values; unresolved terms trigger a clarifying question and, once confirmed, become new glossary entries pending admin approval.
- **Trigger detection**: agent acts on an explicit prefix (`AI` / `Agent` / `AI agent`) or a fallback keyword match (e.g. "Order", "New Acc", "Quotation", "Invoice"); every keyword-triggered pickup is acknowledged so the salesperson knows the agent engaged.
- **Staff-only access**: only company staff (numbers on an allowlist) can trigger or interact with agent features via WhatsApp. Email is a read-only channel for incoming customer POs; agents do not respond to customer emails directly.
- **Customer classification**: SAP customer master data includes a classification flag indicating whether the customer is a trading house. This classification drives address validation behavior (see Section 6.2).

## 7. Non-Functional Requirements

- **Confidentiality**: all agent logic runs on infrastructure the business controls (pure Python, no third-party workflow platform processes business data). See Software Architecture Document.
- **Auditability**: every price used, document sent, and edit made is logged with a version history.
- **Cost control**: a token-usage stopper tracks and caps LLM usage per period, with alerting before a hard threshold is hit.
- **Language robustness**: system must tolerate mixed English/Malay input and common shortforms; ambiguity defaults to asking, not guessing.
- **Communication channel**: WhatsApp (coexistence model — admin's WhatsApp Business app and the agent's API share the same number) for salesperson interaction, plus email for both incoming customer POs and customer-facing invoice documentation. Email is read-only for incoming POs; agents do not send emails to customers except for invoice/quotation documents after admin approval.

## 8. Success Metrics

*(To be finalized with the business — suggested starting metrics below)*
- Number of salespeople supported per admin, before vs. after.
- Reduction in admin time spent per inquiry-to-invoice cycle.
- Rate of agent drafts approved without edits (a proxy for extraction/quote accuracy).
- Number of glossary/SKU exceptions per week (should trend down over time).

## 9. Out of Scope (v1)

- Automated price monitoring/calculation (stays a manual admin-maintained table).
- Automated payment reconciliation/matching against bank records — this stays a manual accountant task; the agent only assists by drafting the SAP entry from a submitted payment PDF (see Section 6.5).
- Central multi-tenant hosting or reselling to other companies (parked as a future business consideration; see the separately sketched gateway framework).
- A native WhatsApp group chat with the agent as a participant (not supported by the WhatsApp Business API).

## 10. Assumptions & Dependencies

- SAP exposes a usable API surface (OData or RFC) for stock, sales order/invoice creation, and customer master data — **pending confirmation of SAP version and connection method**.
- WhatsApp coexistence is available and supportable via Meta's Cloud API directly, without requiring a paid Business Solution Provider platform.
- PDFs received (SSM documents, customer POs) are generally digitally generated rather than scanned; scanned/photographed documents are treated with extra caution, similar to the manual-only handling already decided for bank transfer slips.

## 11. Open Items

- SAP version and connection method (OData vs. RFC/BAPI).
- Final keyword trigger list and its Malay/shortform equivalents.
- Specific token/cost budget thresholds for the usage stopper.
- Whether SAP allows API writes for customer master data, or whether the admin's final step must be done in the SAP GUI directly.
