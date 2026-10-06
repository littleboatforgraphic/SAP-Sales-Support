"""
Mock SAP client for testing without real SAP connection.
This simulates SAP responses for development and testing purposes.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import json


class MockSAPClient:
    """Mock SAP client that returns sample data for testing."""

    def __init__(self):
        # Mock customer data
        self.customers = {
            "CUST001": {
                "customer_id": "CUST001",
                "name": "ABC Trading Sdn Bhd",
                "is_trading_house": True,
                "delivery_addresses": [
                    "123, Jalan Industri, 40000 Shah Alam, Selangor",
                    "456, Jalan Perdagangan, 50000 Kuala Lumpur"
                ]
            },
            "CUST002": {
                "customer_id": "CUST002",
                "name": "XYZ Construction Sdn Bhd",
                "is_trading_house": False,
                "delivery_addresses": [
                    "789, Jalan Bangunan, 60000 Kuala Lumpur"
                ]
            },
            "CUST003": {
                "customer_id": "CUST003",
                "name": "BuildWell Contractors",
                "is_trading_house": False,
                "delivery_addresses": [
                    "321, Jalan Projek, 56000 Cheras, Kuala Lumpur"
                ]
            }
        }

        # Mock stock data
        self.stock = {
            "WM-001": 150,
            "WM-002": 200,
            "WM-003": 75,
            "BRC-A142": 300,
            "BRC-A193": 100,
            "WELD-5050": 0  # Out of stock
        }

    def get_stock(self, sku: str) -> Optional[int]:
        """Get stock quantity for a SKU."""
        return self.stock.get(sku)

    def get_customer_details(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Get customer details including classification and addresses."""
        return self.customers.get(customer_id)

    def is_trading_house(self, customer_id: str) -> bool:
        """Check if customer is a trading house."""
        customer = self.customers.get(customer_id)
        if customer:
            return customer.get("is_trading_house", False)
        return False

    def get_customer_addresses(self, customer_id: str) -> List[str]:
        """Get registered delivery addresses for a customer."""
        customer = self.customers.get(customer_id)
        if customer:
            return customer.get("delivery_addresses", [])
        return []

    def find_customer(self, name: str) -> Optional[Dict[str, Any]]:
        """Find customer by name (simple match)."""
        for cust_id, customer in self.customers.items():
            if name.lower() in customer["name"].lower():
                return customer
        return None

    def create_sales_order(self, order_data: Dict[str, Any]) -> str:
        """Create a sales order (mock)."""
        order_ref = f"SO-{datetime.now().strftime('%Y%m%d')}-{len(self.customers) + 1}"
        print(f"[MOCK SAP] Created sales order: {order_ref}")
        return order_ref

    def create_invoice(self, order_ref: str) -> str:
        """Create an invoice (mock)."""
        invoice_ref = f"INV-{datetime.now().strftime('%Y%m%d')}-{order_ref.split('-')[-1]}"
        print(f"[MOCK SAP] Created invoice: {invoice_ref}")
        return invoice_ref

    def create_delivery_order(self, order_ref: str) -> str:
        """Create a delivery order (mock)."""
        do_ref = f"DO-{datetime.now().strftime('%Y%m%d')}-{order_ref.split('-')[-1]}"
        print(f"[MOCK SAP] Created delivery order: {do_ref}")
        return do_ref

    def get_pick_pack_status(self, order_ref: str) -> str:
        """Get pick/pack status for an order (mock)."""
        return "ready"  # Always ready for testing
