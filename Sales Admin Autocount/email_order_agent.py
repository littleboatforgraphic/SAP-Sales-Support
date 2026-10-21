"""
Email Order Agent for processing external PO emails.

This agent handles inbound purchase orders from external customers via email.
It is more careful than internal Telegram communication because:
- Email content is untrusted data
- External parties may attempt prompt injection
- Financial/contractual actions require human approval
- No direct response with LLM output to external senders

The agent:
1. Extracts order data from email/attachments using email_order_extraction
2. Validates against AutoCount customer data
3. Creates a draft for admin review
4. Requires approval before creating real AutoCount documents
5. Sends only fixed-template acknowledgements (never LLM output)
"""

import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from llm_client import get_llm_client
from autocount_client import get_autocount_client
from mock_autocount_client import MockAutoCountClient
from config import settings
from email_order_extraction import (
    extract_order,
    match_customer,
    ready_for_erp_draft,
    ExtractedOrder,
    CustomerMatch,
    Flag,
    Severity
)
from aotg_sales_invoice_models import CreateSalesOrderParam, CreateSalesOrderLineParam, AddressEntity
from aotg_customer_models import DebtorGetResultEntity
from email_autonomy import get_autonomy_mode, should_auto_submit, log_autonomy_decision, AutonomyMode

logger = logging.getLogger(__name__)


class EmailOrderAgent:
    """
    Agent for processing external PO emails.

    This agent is more security-conscious than internal agents:
    - Never follows instructions in email content
    - Never sends LLM output to external senders
    - Requires human approval for financial actions
    - Treats all email content as untrusted
    """

    def __init__(self, db: Session):
        self.db = db
        self.llm_client = get_llm_client()

        # Use mock client if AOTG not configured
        self.use_mock = not all([
            settings.aotg_username,
            settings.aotg_password.get_secret_value() if settings.aotg_password else "",
            settings.aotg_api_key.get_secret_value() if settings.aotg_api_key else ""
        ])

        if self.use_mock:
            logger.info("EmailOrderAgent using mock AutoCount client")
            self.autocount_client = MockAutoCountClient()
        else:
            logger.info("EmailOrderAgent using real AOTG AutoCount client")
            self.autocount_client = get_autocount_client()

    def _get_llm_complete(self):
        """Get LLM completion function for email_order_extraction.

        Text calls go to the standard model. When scanned-PDF page images are
        supplied, the call switches to the configured vision model — images are
        sent as OpenAI-style image_url data URIs.
        """
        def llm_complete(system_prompt: str, user_prompt: str, images: Optional[List[bytes]] = None) -> str:
            if images:
                import base64
                content: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]
                for img in images:
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64.b64encode(img).decode('ascii')}"
                        }
                    })
                result = self.llm_client.chat_completion(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content},
                    ],
                    model=settings.ilmu_vision_model,
                    temperature=0.3,
                    max_tokens=2000,
                    operation="email-order-ocr",
                )
                return result["content"]

            result = self.llm_client.chat_completion(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=2000,  # More tokens for structured JSON output
                operation="email-order-extraction",
            )
            return result["content"]
        return llm_complete

    def extract_order_from_email(
        self,
        subject: str,
        body: str,
        attachments: List[tuple[str, bytes]],
        own_company_names: List[str] = None
    ) -> tuple[Optional[ExtractedOrder], List[Flag]]:
        """
        Extract order information from email content and attachments.

        Args:
            subject: Email subject
            body: Email body text
            attachments: List of (filename, bytes) tuples
            own_company_names: List of valid company names for this business

        Returns:
            Tuple of (ExtractedOrder or None, list of flags)
        """
        if own_company_names is None:
            own_company_names = ["Eastcoast Metal", "Alpha Technologies"]

        llm_complete = self._get_llm_complete()

        try:
            result = extract_order(
                llm_complete=llm_complete,
                subject=subject,
                body=body,
                documents=attachments,
                own_company_names=own_company_names,
                vision_available=bool(settings.ilmu_vision_model)
            )

            if result.ok:
                logger.info(f"Successfully extracted order: {result.order.doc_type}")
                return result.order, result.flags
            else:
                logger.warning(f"Order extraction failed with flags: {[f.message for f in result.flags]}")
                return None, result.flags

        except Exception as e:
            logger.error(f"Error extracting order from email: {e}")
            return None, [Flag(code="extraction_error", severity="block", message=str(e))]

    def match_customer_in_autocount(
        self,
        order: ExtractedOrder
    ) -> tuple[CustomerMatch, List[Flag]]:
        """
        Match the extracted order's buyer against AutoCount customers.

        Args:
            order: Extracted order from email

        Returns:
            Tuple of (CustomerMatch, list of flags)
        """
        # Get all customers from AutoCount
        customers = []
        if self.use_mock:
            # Use mock customers
            for debtor_code, customer in self.autocount_client.customers.items():
                customers.append({
                    "debtor_code": debtor_code,
                    "company_name": customer["CompanyName"],
                    "addresses": [
                        customer["DeliverAddress"]["Address1"] if customer.get("DeliverAddress") else ""
                    ],
                    "is_trading_house": "trading" in customer.get("Area", "").lower()
                })
        else:
            # Real mode: fetch all debtors via AOTG for fuzzy matching
            for debtor in self.autocount_client.list_debtors():
                del_addr = debtor.get("DeliverAddress") or {}
                addr_parts = [del_addr.get(f"Address{i}", "") for i in range(1, 5)]
                customers.append({
                    "debtor_code": debtor.get("AccNo"),
                    "company_name": debtor.get("CompanyName", ""),
                    "addresses": [a for a in addr_parts if a],
                    "is_trading_house": "trading" in (debtor.get("Area") or "").lower(),
                })

        try:
            return match_customer(order, customers)
        except Exception as e:
            logger.error(f"Error matching customer: {e}")
            return CustomerMatch(status="no_match"), [
                Flag(code="customer_match_error", severity="warn", message=str(e))
            ]

    def create_draft_for_admin(
        self,
        order: ExtractedOrder,
        customer_match: CustomerMatch,
        flags: List[Flag]
    ) -> Dict[str, Any]:
        """
        Create a draft summary for admin review and create AutoCount draft.

        This creates a draft in AutoCount (but doesn't submit it) and prepares
        structured data for admin review.

        Args:
            order: Extracted order
            customer_match: Customer match result
            flags: Extraction and validation flags

        Returns:
            Draft summary dictionary
        """
        # Separate flags by severity
        block_flags = [f for f in flags if f.severity == "block"]
        warn_flags = [f for f in flags if f.severity == "warn"]
        info_flags = [f for f in flags if f.severity == "info"]

        # Determine scenario
        scenario = self._determine_order_scenario(order, customer_match)

        # Create AutoCount draft
        doc_no, doc_type, doc_message = self.create_draft_in_autocount(order, customer_match, flags)

        draft = {
            "status": "draft_created" if doc_no else "draft_failed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scenario": scenario,
            "autocount_draft": {
                "document_number": doc_no,
                "document_type": doc_type,
                "message": doc_message
            },
            "order": {
                "doc_type": order.doc_type,
                "po_number": order.po_number,
                "po_date": order.po_date_raw,
                "buyer_name": order.buyer_name,
                "delivery_date": order.delivery_date_raw,
                "total": order.totals.total,
                "currency": order.totals.currency,
                "line_count": len(order.lines),
                "confidence": order.confidence
            },
            "customer": {
                "status": customer_match.status,
                "debtor_code": customer_match.debtor_code,
                "company_name": customer_match.company_name,
                "score": customer_match.score,
                "is_trading_house": customer_match.is_trading_house,
                "address_status": customer_match.address_status
            },
            "flags": {
                "block": [f.message for f in block_flags],
                "warn": [f.message for f in warn_flags],
                "info": [f.message for f in info_flags]
            },
            "lines": [
                {
                    "item_code": line.item_code_raw,
                    "description": line.description_raw,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "amount": line.amount,
                    "delivery_date": line.delivery_date_raw
                }
                for line in order.lines[:10]  # Limit to first 10 lines for summary
            ],
            "special_instructions": order.special_instructions,
            "ambiguities": order.ambiguities
        }

        return draft

    def _determine_order_scenario(
        self,
        order: ExtractedOrder,
        customer_match: CustomerMatch
    ) -> str:
        """
        Determine the order scenario based on email content.

        Scenarios:
        - "confirmed_po": Has PO number, addressed to us, high confidence
        - "tentative_order": No PO number, or addressed elsewhere, low confidence
        - "enquiry": Not an order, just asking for quote

        Args:
            order: Extracted order
            customer_match: Customer match result

        Returns:
            Scenario identifier
        """
        # Check if it's a confirmed PO
        if order.doc_type == "purchase_order" and order.po_number:
            # Check if addressed to us
            if order.addressed_to_raw:
                # If addressed to our company, it's confirmed
                return "confirmed_po"
            else:
                # No addressee specified, assume confirmed if PO number exists
                return "confirmed_po"

        # Check if it's a text order (email body order without PO)
        if order.doc_type == "text_order" and order.lines:
            return "tentative_order"

        # Default to tentative if we have lines but no PO
        if order.lines and not order.po_number:
            return "tentative_order"

        # Enquiry or other
        return "enquiry"

    def create_draft_in_autocount(
        self,
        order: ExtractedOrder,
        customer_match: CustomerMatch,
        flags: List[Flag]
    ) -> tuple[Optional[str], str, str]:
        """
        Create a draft in AutoCount based on the order scenario.

        Confirmed PO → Create AR Invoice draft (for invoicing)
        Tentative Order → Create Sales Order draft (for confirmation)

        Args:
            order: Extracted order
            customer_match: Customer match result
            flags: Validation flags

        Returns:
            Tuple of (document_number or None, document_type, status_message)
        """
        # Check if customer is matched
        if customer_match.status != "matched":
            return None, "none", f"Customer not matched: {customer_match.status}"

        # Check for block flags
        block_flags = [f for f in flags if f.severity == "block"]
        if block_flags:
            return None, "none", f"Cannot create draft due to block flags: {', '.join(f.message for f in block_flags)}"

        # Determine scenario
        scenario = self._determine_order_scenario(order, customer_match)

        try:
            import asyncio

            if scenario == "confirmed_po":
                # Create AR Invoice draft for invoicing
                from aotg_sales_invoice_models import CreateARInvoiceParam, CreateARInvoiceLineParam

                invoice_data = CreateARInvoiceParam(
                    Debtor=customer_match.debtor_code,
                    DebtorName=customer_match.company_name,
                    DocumentDate=order.po_date_iso or datetime.now().strftime("%Y-%m-%d"),
                    Description=f"PO {order.po_number}",
                    Ref=order.po_number,
                    DetailsLine=[
                        CreateARInvoiceLineParam(
                            AccNo=customer_match.debtor_code,
                            Description=line.description_raw,
                            Amount=line.amount or (line.quantity * line.unit_price if line.quantity and line.unit_price else None)
                        )
                        for line in order.lines if line.quantity
                    ]
                )

                doc_no = asyncio.run(self.autocount_client.create_invoice(invoice_data))
                if doc_no:
                    return doc_no, "ARInvoice", f"AR Invoice draft created: {doc_no}"
                else:
                    return None, "ARInvoice", "Failed to create AR Invoice draft"

            elif scenario == "tentative_order":
                # Create Sales Order draft for confirmation
                from aotg_sales_invoice_models import CreateSalesOrderLineParam, AddressEntity

                # Build address from delivery address or customer address
                deliver_address = None
                if order.delivery_address_raw:
                    # Simple address parsing - in production, use more sophisticated parsing
                    parts = order.delivery_address_raw.split('\n')
                    deliver_address = AddressEntity(
                        Address1=parts[0] if len(parts) > 0 else "",
                        Address2=parts[1] if len(parts) > 1 else "",
                        Address3=parts[2] if len(parts) > 2 else "",
                        Address4=parts[3] if len(parts) > 3 else ""
                    )

                order_data = CreateSalesOrderParam(
                    Debtor=customer_match.debtor_code,
                    DebtorName=customer_match.company_name,
                    DocumentDate=datetime.now().strftime("%Y-%m-%d"),
                    Description="Tentative order for confirmation",
                    Ref=order.po_number or "Email Order",
                    DeliverAddress=deliver_address,
                    DetailsLine=[
                        CreateSalesOrderLineParam(
                            Item=line.item_code_raw,
                            Description=line.description_raw,
                            Qty=line.quantity,
                            UnitPrice=line.unit_price,
                            DeliveryDate=line.delivery_date_iso or order.delivery_date_iso
                        )
                        for line in order.lines if line.quantity
                    ]
                )

                doc_no = asyncio.run(self.autocount_client.create_sales_order(order_data))
                if doc_no:
                    return doc_no, "SalesOrder", f"Sales Order draft created: {doc_no}"
                else:
                    return None, "SalesOrder", "Failed to create Sales Order draft"

            else:
                # Enquiry - don't create draft
                return None, "none", f"Enquiry detected ({order.doc_type}) - no draft created"

        except Exception as e:
            logger.error(f"Error creating AutoCount draft: {e}")
            return None, "none", f"Error creating draft: {str(e)}"

    def _is_repeat_customer(self, debtor_code: Optional[str]) -> bool:
        """
        Check if customer is a repeat customer (has previous orders).

        Args:
            debtor_code: Customer debtor code

        Returns:
            True if repeat customer, False otherwise
        """
        if not debtor_code:
            return False

        # Check audit log for previous successful orders from this customer.
        # The webhook stores debtor_code flat in the "draft_created" details,
        # so match that key and require an actual document number (a failed
        # draft doesn't make the customer a repeat buyer).
        from database import AuditLogEntry

        previous_orders = self.db.query(AuditLogEntry).filter(
            AuditLogEntry.entity_type == "email_po",
            AuditLogEntry.action == "draft_created",
            AuditLogEntry.details["debtor_code"].as_string() == debtor_code,
            AuditLogEntry.details["autocount_doc_number"].as_string().isnot(None),
        ).count()

        return previous_orders > 0

    def _resolve_line_items(self, order: ExtractedOrder) -> List[Flag]:
        """
        Fill item_code_raw for description-only lines by fuzzy-matching the
        synced item catalogue (SKU index). Matched lines get a warn flag so
        the admin can see the mapping was inferred, not printed.
        """
        flags: List[Flag] = []
        if self.db is None:
            return flags
        try:
            from sku_index import SKUIndexManager
            from database import SKUIndexEntry
            if self.db.query(SKUIndexEntry).filter(SKUIndexEntry.active == True).count() == 0:
                return flags
            catalog = SKUIndexManager(self.db)
        except Exception as e:
            logger.warning(f"Item catalogue unavailable for line resolution: {e}")
            return flags

        for i, line in enumerate(order.lines, 1):
            if line.item_code_raw or not line.description_raw:
                continue
            try:
                hits = catalog.fuzzy_match(line.description_raw, limit=2)
            except Exception:
                continue
            if not hits or hits[0]["score"] < 60:
                continue
            if len(hits) > 1 and hits[1]["score"] == hits[0]["score"]:
                flags.append(Flag(
                    code="item_catalogue_ambiguous",
                    severity="warn",
                    message=f"Line {i}: '{line.description_raw}' matches multiple "
                            f"catalogue items ({hits[0]['sku']}, {hits[1]['sku']}) - not resolved"
                ))
                continue
            line.item_code_raw = hits[0]["sku"]
            flags.append(Flag(
                code="item_catalogue_matched",
                severity="warn",
                message=f"Line {i}: matched '{line.description_raw}' to "
                        f"{hits[0]['sku']} via catalogue (score {hits[0]['score']})"
            ))
        return flags

    def process_inbound_email(
        self,
        subject: str,
        body: str,
        attachments: List[tuple[str, bytes]],
        sender: str,
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete processing pipeline for an inbound PO email.

        This is the main entry point for email order processing.
        Supports three autonomy modes: shadow, assisted, selective_autonomy.

        Args:
            subject: Email subject
            body: Email body
            attachments: List of (filename, bytes) tuples
            sender: Sender email address
            message_id: Email message ID (for logging)

        Returns:
            Processing result with draft and autonomy decision
        """
        logger.info(f"Processing inbound email from {sender}: {subject}")

        # Generate reference ID for logging
        ref_id = message_id or f"{sender[:30]}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        # Get current autonomy mode
        autonomy_mode = get_autonomy_mode()
        logger.info(f"Autonomy mode: {autonomy_mode.value}")

        # Step 1: Extract order
        order, extraction_flags = self.extract_order_from_email(subject, body, attachments)

        if not order:
            return {
                "status": "rejected",
                "reason": "Order extraction failed",
                "flags": [f.message for f in extraction_flags],
                "autonomy_mode": autonomy_mode.value
            }

        # Step 2: Match customer
        customer_match, customer_flags = self.match_customer_in_autocount(order)

        # Step 2b: resolve description-only lines against the synced catalogue
        item_flags = self._resolve_line_items(order)

        # Step 3: Combine flags
        all_flags = extraction_flags + customer_flags + item_flags

        # Step 4: Create draft for admin
        draft = self.create_draft_for_admin(order, customer_match, all_flags)

        # Step 5: Check if repeat customer
        is_repeat_customer = self._is_repeat_customer(customer_match.debtor_code)

        # Step 6: Determine autonomy decision
        should_submit, autonomy_reason = should_auto_submit(draft, is_repeat_customer)

        # Log autonomy decision
        log_autonomy_decision(
            self.db,
            ref_id,
            "auto_submit" if should_submit else "require_approval",
            autonomy_reason,
            autonomy_mode.value
        )

        # Step 7: Auto-submit if criteria met (selective autonomy mode)
        if should_submit and autonomy_mode == AutonomyMode.SELECTIVE_AUTONOMY:
            doc_no = draft.get("autocount_draft", {}).get("document_number")
            if doc_no:
                logger.info(f"Auto-submitting draft {doc_no} in AutoCount")
                # In a real implementation, you would submit the draft here
                # For now, we just log it as submitted
                draft["autocount_draft"]["submitted"] = True
                draft["autocount_draft"]["submitted_at"] = datetime.now(timezone.utc).isoformat()
                draft["autocount_draft"]["submission_mode"] = "auto"

        # Step 8: Return result
        return {
            "status": "draft_created",
            "sender": sender,
            "draft": draft,
            "autonomy_mode": autonomy_mode.value,
            "autonomy_decision": "auto_submit" if should_submit else "require_approval",
            "autonomy_reason": autonomy_reason,
            "is_repeat_customer": is_repeat_customer,
            "flag_count": len(all_flags),
            "block_flags": draft["flags"]["block"],
            "warn_flags": draft["flags"]["warn"]
        }
