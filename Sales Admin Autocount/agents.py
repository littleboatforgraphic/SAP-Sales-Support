"""
Base agent class for all Sales Admin AI agents.

This provides common functionality for all agents defined in the PRD:
- Stock & Quote Agent
- Order-to-Invoice Agent
- Shipment Agent
- Customer Onboarding Agent
- Payment Follow-up Agent
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from llm_client import get_llm_client
from autocount_client import get_autocount_client
from mock_autocount_client import MockAutoCountClient
from config import settings

# Import AOTG Pydantic models for type-safe API calls
from aotg_sales_invoice_models import CreateSalesOrderParam, CreateARInvoiceParam
from aotg_delivery_order_models import CreateDeliveryOrderParam
from aotg_customer_models import DebtorCreateEntity
from aotg_stock_models import StockItemResult

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for all Sales Admin AI agents."""

    def __init__(self, db: Session):
        self.db = db
        self.llm_client = get_llm_client()
        
        # Use mock client if AOTG not configured, otherwise use real AOTG
        self.use_mock = not all([
            settings.aotg_username,
            settings.aotg_password.get_secret_value() if settings.aotg_password else "",
            settings.aotg_api_key.get_secret_value() if settings.aotg_api_key else ""
        ])
        
        if self.use_mock:
            logger.info("Using mock AutoCount client for testing")
            self.autocount_client = MockAutoCountClient()
        else:
            logger.info("Using real AOTG AutoCount client")
            self.autocount_client = get_autocount_client()

    def get_system_prompt(self) -> str:
        """Get the system prompt for this agent. Override in subclasses."""
        return "You are a helpful sales assistant."

    def get_data_context(self) -> str:
        """Get the data context for the LLM. Override in subclasses."""
        return ""

    def process_with_llm(self, user_message: str) -> str:
        """
        Process a user message using the LLM with relevant data context.
        
        Args:
            user_message: The user's natural language query
            
        Returns:
            The LLM's response
        """
        system_prompt = self.get_system_prompt()
        data_context = self.get_data_context()
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{data_context}\n\nUser question: {user_message}"}
        ]
        
        try:
            result = self.llm_client.chat_completion(
                messages,
                temperature=0.3,  # Lower temperature for more deterministic responses
                max_tokens=150,  # Limit to ~150 tokens for ~200 characters
                operation=f"agent:{type(self).__name__}",
            )
            return result["content"]
        except Exception as e:
            logger.error(f"LLM processing error: {e}")
            return f"Sorry, I encountered an error processing your request: {str(e)}"

    def handle_message(self, message: str, user_id: str) -> str:
        """
        Handle a user message. Override in subclasses.
        
        Args:
            message: The user's message
            user_id: The user's identifier
            
        Returns:
            The agent's response
        """
        raise NotImplementedError("Subclasses must implement handle_message")


class StockQuoteAgent(BaseAgent):
    """Stock & Quote Agent - Agent #1 from PRD."""

    def get_system_prompt(self) -> str:
        return """You are a Stock & Quote assistant. Be concise.

Rules:
- Answer ONLY about stock and pricing
- Keep responses under 200 characters
- Use **bold** ONLY for: "Out of stock", "In stock", critical warnings
- Use plain text for everything else
- If no price data, say "Price not available"
- Never make up information"""

    def get_data_context(self) -> str:
        context = []
        
        # Get stock data
        if self.use_mock:
            for item_code, quantity in self.autocount_client.stock.items():
                status = "In stock" if quantity > 0 else "Out of stock"
                context.append(f"{item_code}: {quantity} ({status})")
        else:
            context.append("(Stock from AOTG)")
        
        # Add price table data
        from database import PriceReferenceEntry
        prices = self.db.query(PriceReferenceEntry).filter(
            PriceReferenceEntry.effective_to.is_(None)
        ).limit(10).all()
        
        if prices:
            context.append("\nPrices:")
            for price in prices:
                # Format date without time
                date_str = price.effective_from.strftime("%Y-%m-%d") if price.effective_from else "N/A"
                context.append(f"{price.sku}: {price.price} (from {date_str})")
        
        return "\n".join(context)

    def handle_message(self, message: str, user_id: str) -> str:
        """Handle stock and quote inquiries."""
        return self.process_with_llm(message)


class OrderToInvoiceAgent(BaseAgent):
    """Order-to-Invoice Agent - Agent #2 from PRD."""

    def get_system_prompt(self) -> str:
        return """You are an Order & Invoice assistant. Be concise.

Rules:
- Answer about customers, orders, and invoices
- Keep responses under 200 characters
- Use **bold** ONLY for: "Yes", "No", critical alerts, important names
- Use plain text for everything else
- Never make up information"""

    def get_data_context(self) -> str:
        context = []
        
        # Get customer data
        if self.use_mock:
            for debtor_code, customer in self.autocount_client.customers.items():
                is_trading = self.autocount_client.is_trading_house(debtor_code)
                context.append(f"{debtor_code}: {customer['CompanyName']}")
                context.append(f"  Contact: {customer['InvoiceAddress'].get('Contact', '')}")
                context.append(f"  Phone: {customer['InvoiceAddress'].get('Phone', '')}")
                context.append(f"  Trading: {'Yes' if is_trading else 'No'}")
        
        return "\n".join(context)

    def handle_message(self, message: str, user_id: str) -> str:
        """Handle order and invoice processing."""
        return self.process_with_llm(message)


class ShipmentAgent(BaseAgent):
    """Shipment Agent - Agent #3 from PRD."""

    def get_system_prompt(self) -> str:
        return """You are a Shipment assistant. Be concise.

Rules:
- Answer about shipments and delivery
- Keep responses under 200 characters
- Use **bold** ONLY for: critical status, alerts, "Ready", "Delayed"
- Use plain text for everything else
- Never make up information"""

    def get_data_context(self) -> str:
        return "SHIPMENT: (Implement with AOTG)"

    def handle_message(self, message: str, user_id: str) -> str:
        """Handle shipment inquiries."""
        return self.process_with_llm(message)


class CustomerOnboardingAgent(BaseAgent):
    """Customer Onboarding Agent - Agent #4 from PRD."""

    def get_system_prompt(self) -> str:
        return """You are a Customer Onboarding assistant. Be concise.

Rules:
- Answer about customer onboarding
- Keep responses under 200 characters
- Use **bold** ONLY for: "Duplicate", "New", critical alerts
- Use plain text for everything else
- Never make up information"""

    def get_data_context(self) -> str:
        context = []
        if self.use_mock:
            for debtor_code, customer in self.autocount_client.customers.items():
                context.append(f"{debtor_code}: {customer['CompanyName']}")
        return "\n".join(context)

    def handle_message(self, message: str, user_id: str) -> str:
        """Handle customer onboarding."""
        return self.process_with_llm(message)


class PaymentFollowupAgent(BaseAgent):
    """Payment Follow-up Agent - Agent #5 from PRD."""

    def get_system_prompt(self) -> str:
        return """You are a Payment assistant. Be concise.

Rules:
- Answer about payments and receipts
- Keep responses under 200 characters
- Use **bold** ONLY for: "Confirmed", "Pending", "Failed", critical alerts
- Use plain text for everything else
- Never make up information"""

    def get_data_context(self) -> str:
        return "PAYMENT: (Implement with document processing)"

    def handle_message(self, message: str, user_id: str) -> str:
        """Handle payment follow-up."""
        return self.process_with_llm(message)
