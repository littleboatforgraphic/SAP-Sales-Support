"""
Mock AutoCount client for testing without real AutoCount connection.
This simulates AutoCount responses for development and testing purposes.
Uses Autocount data structure (Debtor with AccNo, InvoiceAddress, DeliverAddress, BranchList).
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import json

from aotg_sales_invoice_models import CreateSalesOrderParam, CreateARInvoiceParam
from aotg_delivery_order_models import CreateDeliveryOrderParam


class MockAutoCountClient:
    """Mock AutoCount client that returns sample data for testing."""

    def __init__(self):
        # Mock debtor (customer) data using Autocount structure
        self.customers = {
            "300-A001": {
                "AccNo": "300-A001",
                "CompanyName": "ABC Trading Sdn Bhd",
                "Area": "Trading",
                "EmailAddress": "orders@abctrading.example",
                "InvoiceAddress": {
                    "Contact": "Mr. Tan",
                    "Phone": "02111373",
                    "Address1": "123, Jalan Industri",
                    "Address2": "40000 Shah Alam",
                    "Address3": "Selangor",
                    "Address4": "50000 Malaysia"
                },
                "DeliverAddress": {
                    "Contact": "Mr. Tan",
                    "Phone": "02111373",
                    "Address1": "123, Jalan Industri",
                    "Address2": "40000 Shah Alam",
                    "Address3": "Selangor",
                    "Address4": "50000 Malaysia"
                },
                "BranchList": [
                    {
                        "IsActive": True,
                        "Code": "B001",
                        "Name": "Branch A",
                        "Address1": "456, Jalan Perdagangan",
                        "Address2": "50000 Kuala Lumpur",
                        "Address3": "Kuala Lumpur",
                        "Address4": "50000 Malaysia"
                    }
                ]
            },
            "300-A002": {
                "AccNo": "300-A002",
                "CompanyName": "XYZ Construction Sdn Bhd",
                "Area": "Construction",
                "EmailAddress": "purchasing@xyzconstruction.example",
                "InvoiceAddress": {
                    "Contact": "Mr. Lee",
                    "Phone": "03-12345678",
                    "Address1": "789, Jalan Bangunan",
                    "Address2": "60000 Kuala Lumpur",
                    "Address3": "Kuala Lumpur",
                    "Address4": "50000 Malaysia"
                },
                "DeliverAddress": {
                    "Contact": "Mr. Lee",
                    "Phone": "03-12345678",
                    "Address1": "789, Jalan Bangunan",
                    "Address2": "60000 Kuala Lumpur",
                    "Address3": "Kuala Lumpur",
                    "Address4": "50000 Malaysia"
                },
                "BranchList": []
            },
            "300-A003": {
                "AccNo": "300-A003",
                "CompanyName": "BuildWell Contractors",
                "Area": "Construction",
                "EmailAddress": "admin@buildwell.example",
                "InvoiceAddress": {
                    "Contact": "Ms. Sarah",
                    "Phone": "03-87654321",
                    "Address1": "321, Jalan Projek",
                    "Address2": "56000 Cheras",
                    "Address3": "Kuala Lumpur",
                    "Address4": "50000 Malaysia"
                },
                "DeliverAddress": {
                    "Contact": "Ms. Sarah",
                    "Phone": "03-87654321",
                    "Address1": "321, Jalan Projek",
                    "Address2": "56000 Cheras",
                    "Address3": "Kuala Lumpur",
                    "Address4": "50000 Malaysia"
                },
                "BranchList": []
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

        # Catalogue details used by list_stock_items (the SKU-index sync source)
        self.item_details = {
            "WM-001": {"description": "Welded Wire Mesh 6mm x 6mm x 2.4m x 1.2m", "uom": "PCS", "std_price": 45.00},
            "WM-002": {"description": "Welded Wire Mesh 8mm x 8mm x 2.4m x 1.2m", "uom": "PCS", "std_price": 52.00},
            "WM-003": {"description": "Galvanized Wire Mesh 6mm x 6mm x 2.4m x 1.2m", "uom": "PCS", "std_price": 68.00},
            "BRC-A142": {"description": "BRC Mesh A142 10mm x 10mm x 2.4m x 1.2m", "uom": "PCS", "std_price": 85.00},
            "BRC-A193": {"description": "BRC Mesh A193 12mm x 12mm x 2.4m x 1.2m", "uom": "PCS", "std_price": 95.00},
            "WELD-5050": {"description": "Weldmesh 5mm x 5mm x 2.4m x 1.2m", "uom": "PCS", "std_price": 38.00},
        }

        # Mock order data - keyed by UPPERCASE ref. Seeded orders exist so
        # status enquiries can be tested; orders created via
        # create_sales_order() are stored here too.
        self.orders = {
            "SO-20261014-4": {
                "ref": "SO-20261014-4",
                "debtor_code": "300-A001",
                "debtor_name": "ABC Trading Sdn Bhd",
                "status": "ready for packing",
            },
            "SO-20261010-1": {
                "ref": "SO-20261010-1",
                "debtor_code": "300-A002",
                "debtor_name": "XYZ Construction Sdn Bhd",
                "status": "delivered",
            },
            "INV-20261012-2": {
                "ref": "INV-20261012-2",
                "debtor_code": "300-A001",
                "debtor_name": "ABC Trading Sdn Bhd",
                "status": "invoiced, payment pending",
            },
        }

    def get_stock_info(self, item_code: str) -> Optional[Dict[str, Any]]:
        """Get stock information for an item code."""
        quantity = self.stock.get(item_code)
        if quantity is not None:
            return {
                "item_code": item_code,
                "description": f"Mock Item {item_code}",
                "quantity": quantity
            }
        return None

    def get_stock(self, item_code: str) -> Optional[int]:
        """Get stock quantity for an item code (for backward compatibility)."""
        return self.stock.get(item_code)

    def list_stock_items(self, keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Mock of AOTG POST /StockItem/GetList - the source for the local
        SKU-index catalogue sync. Optional keyword filters code/description.
        """
        rows = []
        for code, qty in self.stock.items():
            d = self.item_details.get(code, {})
            row = {
                "ItemCode": code,
                "Description": d.get("description") or f"Mock Item {code}",
                "UOM": d.get("uom", "PCS"),
                "StockQty": float(qty),
                "StdPrice": d.get("std_price"),
            }
            kw = (keyword or "").strip().lower()
            if kw and kw not in code.lower() and kw not in row["Description"].lower():
                continue
            rows.append(row)
        return rows

    def list_debtors(self) -> List[Dict[str, Any]]:
        """List all debtors, shaped like AOTG's DebtorListResultEntity."""
        return [
            {"AccNo": code, "CompanyName": c["CompanyName"],
             "EmailAddress": c.get("EmailAddress"),
             "Area": c.get("Area", ""), "DeliverAddress": c.get("DeliverAddress")}
            for code, c in self.customers.items()
        ]

    def get_customer_details(self, debtor_code: str) -> Optional[Dict[str, Any]]:
        """Get customer (Debtor) details including classification and addresses."""
        return self.customers.get(debtor_code)

    def is_trading_house(self, debtor_code: str) -> bool:
        """Check if customer is classified as a trading house."""
        customer = self.customers.get(debtor_code)
        if customer:
            # Use Area field as proxy for trading house classification
            area = customer.get("Area", "").lower()
            return "trading" in area
        return False

    def get_customer_addresses(self, debtor_code: str) -> List[str]:
        """Get registered addresses for a customer (as strings for backward compatibility)."""
        customer = self.customers.get(debtor_code)
        if not customer:
            return []

        addresses = []

        # Add invoice address
        if customer.get("InvoiceAddress"):
            inv_addr = customer["InvoiceAddress"]
            addresses.append(f"{inv_addr.get('Address1', '')}, {inv_addr.get('Address2', '')}, {inv_addr.get('Address3', '')}, {inv_addr.get('Address4', '')}")

        # Add delivery address
        if customer.get("DeliverAddress"):
            del_addr = customer["DeliverAddress"]
            addresses.append(f"{del_addr.get('Address1', '')}, {del_addr.get('Address2', '')}, {del_addr.get('Address3', '')}, {del_addr.get('Address4', '')}")

        # Add branch addresses
        branch_list = customer.get("BranchList", [])
        if branch_list:
            for branch in branch_list:
                if branch.get("IsActive"):
                    addresses.append(f"{branch.get('Address1', '')}, {branch.get('Address2', '')}, {branch.get('Address3', '')}, {branch.get('Address4', '')}")

        return addresses

    def get_customer_addresses_detailed(self, debtor_code: str) -> List[Dict[str, Any]]:
        """Get registered addresses for a customer (detailed format with Autocount structure)."""
        customer = self.customers.get(debtor_code)
        if not customer:
            return []

        addresses = []

        # Add invoice address
        if customer.get("InvoiceAddress"):
            inv_addr = customer["InvoiceAddress"]
            addresses.append({
                "type": "invoice",
                "contact": inv_addr.get("Contact", ""),
                "phone": inv_addr.get("Phone", ""),
                "address": f"{inv_addr.get('Address1', '')}, {inv_addr.get('Address2', '')}, {inv_addr.get('Address3', '')}, {inv_addr.get('Address4', '')}"
            })

        # Add delivery address
        if customer.get("DeliverAddress"):
            del_addr = customer["DeliverAddress"]
            addresses.append({
                "type": "delivery",
                "contact": del_addr.get("Contact", ""),
                "phone": del_addr.get("Phone", ""),
                "address": f"{del_addr.get('Address1', '')}, {del_addr.get('Address2', '')}, {del_addr.get('Address3', '')}, {del_addr.get('Address4', '')}"
            })

        # Add branch addresses
        branch_list = customer.get("BranchList", [])
        if branch_list:
            for branch in branch_list:
                if branch.get("IsActive"):
                    addresses.append({
                        "type": "branch",
                        "branch_code": branch.get("Code", ""),
                        "branch_name": branch.get("Name", ""),
                        "address": f"{branch.get('Address1', '')}, {branch.get('Address2', '')}, {branch.get('Address3', '')}, {branch.get('Address4', '')}"
                    })

        return addresses

    def find_customer(self, name: str) -> Optional[Dict[str, Any]]:
        """Find customer by name (simple match)."""
        for debtor_code, customer in self.customers.items():
            if name.lower() in customer["CompanyName"].lower():
                return customer
        return None

    async def create_sales_order(self, order_data: CreateSalesOrderParam) -> Optional[str]:
        """Create a sales order (mock)."""
        order_ref = f"SO-{datetime.now().strftime('%Y%m%d')}-{len(self.orders) + 1}"
        print(f"[MOCK AUTOCOUNT] Created sales order: {order_ref}")
        print(f"[MOCK AUTOCOUNT] Payload: {order_data.model_dump(exclude_none=True)}")
        self.orders[order_ref] = {
            "ref": order_ref,
            "debtor_code": getattr(order_data, "Debtor", None),
            "debtor_name": getattr(order_data, "DebtorName", None),
            "status": "open",
        }
        return order_ref

    async def create_invoice(self, invoice_data: CreateARInvoiceParam) -> Optional[str]:
        """Create an invoice (mock)."""
        invoice_ref = f"INV-{datetime.now().strftime('%Y%m%d')}-{len(self.customers) + 1}"
        print(f"[MOCK AUTOCOUNT] Created invoice: {invoice_ref}")
        print(f"[MOCK AUTOCOUNT] Payload: {invoice_data.model_dump(exclude_none=True)}")
        return invoice_ref

    async def create_delivery_order(self, do_data: CreateDeliveryOrderParam) -> Optional[str]:
        """Create a delivery order (mock)."""
        do_ref = f"DO-{datetime.now().strftime('%Y%m%d')}-{len(self.customers) + 1}"
        print(f"[MOCK AUTOCOUNT] Created delivery order: {do_ref}")
        print(f"[MOCK AUTOCOUNT] Payload: {do_data.model_dump(exclude_none=True)}")
        return do_ref

    def get_order_status(self, order_ref: str) -> Optional[Dict[str, Any]]:
        """
        Get an order/invoice/delivery document with its owning debtor.
        Returns None when the reference does not exist.
        """
        if not order_ref:
            return None
        return self.orders.get(str(order_ref).strip().upper())

    def get_pick_pack_status(self, order_id: str) -> Dict[str, Any]:
        """Get pick/pack status for an order (mock)."""
        order = self.get_order_status(order_id)
        if order:
            return {"status": order["status"],
                    "debtor_code": order["debtor_code"],
                    "message": f"Order {order['ref']}: {order['status']}"}
        return {"status": "unknown", "message": "Order not found"}
