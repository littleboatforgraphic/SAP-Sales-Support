"""
AutoCount Client for Sales Admin AI Agent System.

This module provides the interface to AutoCount via AOTG API for customer data,
invoice creation, sales order, delivery order, and SQL Server queries for stock information.

Integration Methods:
1. AOTG API (Cloud Bridge) - RESTful API for Debtor, AR Invoice, Sales Order, Delivery Order operations
2. Direct SQL Server queries - For stock/inventory balance information (READ ONLY)
"""

import logging
import asyncio
import time
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
import httpx
import pyodbc
import json

from config import settings

logger = logging.getLogger(__name__)


class AutoCountClientInterface(ABC):
    """Abstract base class for AutoCount client implementations."""

    @abstractmethod
    def get_customer_details(self, debtor_code: str) -> Optional[Dict[str, Any]]:
        """Retrieve customer (Debtor) details from AutoCount."""
        pass

    @abstractmethod
    def get_stock_info(self, item_code: str) -> Optional[Dict[str, Any]]:
        """Retrieve stock information for a product."""
        pass

    @abstractmethod
    def get_customer_addresses(self, debtor_code: str) -> List[Dict[str, Any]]:
        """Retrieve all registered addresses for a customer."""
        pass

    @abstractmethod
    def is_trading_house(self, debtor_code: str) -> bool:
        """Check if customer is classified as a trading house."""
        pass

    @abstractmethod
    def create_sales_order(self, order_data: Dict[str, Any]) -> Optional[str]:
        """Create a sales order in AutoCount and return the order number."""
        pass

    @abstractmethod
    def create_invoice(self, order_data: Dict[str, Any]) -> Optional[str]:
        """Create an invoice in AutoCount and return the invoice number."""
        pass

    @abstractmethod
    def create_delivery_order(self, order_data: Dict[str, Any]) -> Optional[str]:
        """Create a delivery order and return the DO number."""
        pass

    @abstractmethod
    def get_pick_pack_status(self, order_id: str) -> Dict[str, Any]:
        """Get pick/pack status for an order."""
        pass


class AOTGAuthenticator:
    """Handles AOTG API authentication with token caching."""

    def __init__(self):
        self.base_url = settings.aotg_base_url
        self.username = settings.aotg_username
        self.password = settings.aotg_password.get_secret_value() if settings.aotg_password else ""
        self.api_key = settings.aotg_api_key.get_secret_value() if settings.aotg_api_key else ""
        self._access_token = None
        self._token_expiry = None

    def authenticate(self) -> str:
        """
        Authenticate with AOTG API and get access token.
        Returns the access token.
        """
        if self._is_token_valid():
            return self._access_token

        url = f"{self.base_url}/api/public/v1/TokenAuth/Authenticate"
        payload = {
            "UserName": self.username,
            "Password": self.password,
            "ApiKey": self.api_key
        }

        try:
            response = httpx.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            self._access_token = data.get("AccessToken")
            expire_timestamp = data.get("ExpireTimestamp")

            # Convert timestamp to datetime (AOTG uses .NET ticks)
            if expire_timestamp:
                # .NET ticks are 100-nanosecond intervals since 01/01/0001
                # Convert to Unix timestamp
                unix_timestamp = (expire_timestamp - 621355968000000000) / 10000000
                self._token_expiry = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)

            logger.info("Successfully authenticated with AOTG API")
            return self._access_token

        except Exception as e:
            logger.error(f"AOTG authentication failed: {e}")
            raise

    def _is_token_valid(self) -> bool:
        """Check if cached token is still valid."""
        if not self._access_token or not self._token_expiry:
            return False

        # Add 5-minute buffer before expiry
        return datetime.now(timezone.utc) < (self._token_expiry - timedelta(minutes=5))

    def get_cached_token(self) -> str:
        """Get cached token if valid, otherwise authenticate."""
        return self.authenticate()


class AOTGClient(AutoCountClientInterface):
    """
    AutoCount client using AOTG API (Cloud Bridge).

    Handles:
    - Debtor (Customer) operations
    - AR Invoice operations
    - Stock Item operations
    - Async request pattern (submit → poll → result)
    """

    def __init__(self):
        self.auth = AOTGAuthenticator()
        self.base_url = settings.aotg_base_url

        # Check if AOTG is configured
        pwd = settings.aotg_password.get_secret_value() if settings.aotg_password else ""
        key = settings.aotg_api_key.get_secret_value() if settings.aotg_api_key else ""
        if not all([settings.aotg_username, pwd, key]):
            logger.warning("AOTG client not fully configured - using mock mode")
            self._mock_mode = True
        else:
            self._mock_mode = False

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authorization token."""
        return {
            "SOTC_AUTH": self.auth.get_cached_token(),
            "Content-Type": "application/json"
        }

    async def _submit_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, str]:
        """
        Submit a request to AOTG API.
        Returns dict with 'Id' and 'Name' for polling.
        """
        if self._mock_mode:
            logger.warning("Using mock mode for submit_request")
            return {"Id": "mock-id", "Name": "MockRequest"}

        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        try:
            response = httpx.post(url, json=data, headers=headers, timeout=30.0)
            response.raise_for_status()
            result = response.json()
            logger.info(f"Submitted request: {result.get('Name')} with Id: {result.get('Id')}")
            return result
        except Exception as e:
            logger.error(f"Failed to submit request to {endpoint}: {e}")
            raise

    async def _poll_status(self, request_id: str, request_name: str, max_wait_seconds: int = 60) -> str:
        """
        Poll request status until completed.
        Returns "Completed" or raises exception on timeout.
        """
        if self._mock_mode:
            return "Completed"

        url = f"{self.base_url}/api/public/v1/Result/{request_id}"
        headers = self._get_headers()

        start_time = time.time()
        while time.time() - start_time < max_wait_seconds:
            try:
                response = httpx.get(url, headers=headers, timeout=30.0)
                response.raise_for_status()
                result = response.json()
                status = result.get("Status")

                if status == "Completed":
                    logger.info(f"Request {request_name} completed")
                    return "Completed"
                elif status == "Failed":
                    logger.error(f"Request {request_name} failed")
                    raise Exception(f"Request {request_name} failed")

                # Still InQueue, wait and retry
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Error polling status: {e}")
                raise

        raise TimeoutError(f"Request {request_name} timed out after {max_wait_seconds} seconds")

    async def _get_result(self, request_id: str, request_name: str) -> Dict[str, Any]:
        """
        Get the result of a completed request.
        Returns the actual data.
        """
        if self._mock_mode:
            return {}

        url = f"{self.base_url}/api/public/v1/Result/{request_id}/{request_name}"
        headers = self._get_headers()

        try:
            response = httpx.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            result = response.json()

            # ResultJson contains the actual data as a JSON string
            result_json = result.get("ResultJson")
            if result_json:
                return json.loads(result_json)

            return result
        except Exception as e:
            logger.error(f"Failed to get result for {request_name}: {e}")
            raise

    async def _execute_async_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the full async request pattern: submit → poll → result.
        """
        # Step 1: Submit request
        submit_result = await self._submit_request(endpoint, data)
        request_id = submit_result.get("Id")
        request_name = submit_result.get("Name")

        # Step 2: Poll status
        await self._poll_status(request_id, request_name)

        # Step 3: Get result
        result = await self._get_result(request_id, request_name)
        return result

    def get_customer_details(self, debtor_code: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve customer (Debtor) details from AutoCount via AOTG.
        Uses Debtor Lookup to find customer by code.
        """
        if self._mock_mode:
            logger.warning("Using mock mode for get_customer_details")
            return None

        try:
            # Use Debtor Lookup to find customer
            url = f"{self.base_url}/api/public/v1/Lookup/DebtorLookup"
            headers = self._get_headers()
            params = {"$filter": f"AccNo eq '{debtor_code}'", "$top": 1}

            response = httpx.get(url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            results = response.json()

            if results and len(results) > 0:
                return results[0]

            return None

        except Exception as e:
            logger.error(f"Failed to get customer details for {debtor_code}: {e}")
            return None

    def get_stock_info(self, item_code: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve stock information via direct SQL query to AutoCount database.
        This bypasses AOTG API as it doesn't provide stock balance endpoints.
        READ ONLY - uses SELECT queries only to preserve AutoCount accounting validations.
        """
        pwd = settings.autocount_sql_password.get_secret_value() if settings.autocount_sql_password else ""
        if not all([settings.autocount_sql_server, settings.autocount_sql_database,
                   settings.autocount_sql_username, pwd]):
            logger.warning("SQL Server not configured for stock queries")
            return None

        try:
            conn_str = (
                f"DRIVER={settings.autocount_sql_driver};"
                f"SERVER={settings.autocount_sql_server};"
                f"DATABASE={settings.autocount_sql_database};"
                f"UID={settings.autocount_sql_username};"
                f"PWD={pwd}"
            )

            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()

            # Query stock item - table name may vary, common is StockItem or Item
            # This is a placeholder - actual schema needs to be verified
            cursor.execute("""
                SELECT ItemCode, Description, QtyOnHand
                FROM StockItem
                WHERE ItemCode = ?
            """, item_code)

            row = cursor.fetchone()
            conn.close()

            if row:
                return {
                    "item_code": row.ItemCode,
                    "description": row.Description,
                    "quantity": row.QtyOnHand
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get stock info for {item_code}: {e}")
            return None

    def get_customer_addresses(self, debtor_code: str) -> List[Dict[str, Any]]:
        """
        Retrieve all registered addresses for a customer.
        Returns InvoiceAddress, DeliverAddress, and BranchList addresses.
        """
        customer = self.get_customer_details(debtor_code)
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

    def is_trading_house(self, debtor_code: str) -> bool:
        """
        Check if customer is classified as a trading house.
        AutoCount doesn't have a native "trading house" field.
        This implementation uses Area or PriceCategory as a proxy.
        Customization may be needed based on actual business rules.
        """
        customer = self.get_customer_details(debtor_code)
        if not customer:
            return False

        # Option 1: Use Area field
        area = customer.get("Area", "").lower()
        if "trading" in area or "trader" in area:
            return True

        # Option 2: Use PriceCategory field
        price_category = customer.get("PriceCategory", "").lower()
        if "trading" in price_category or "trader" in price_category:
            return True

        # Option 3: Add custom logic or UDF field
        # This should be customized based on actual business requirements

        return False

    def create_sales_order(self, order_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a sales order in AutoCount via AOTG API.
        Returns the order number.
        """
        if self._mock_mode:
            logger.warning("Using mock mode for create_sales_order")
            return None

        try:
            # Map order data to AOTG SalesOrder structure
            so_data = {
                "Debtor": order_data.get("customer_id"),
                "DebtorName": order_data.get("customer_name", ""),
                "DeliverAddress": order_data.get("delivery_address", {}),
                "InvoiceAddress": order_data.get("invoice_address", {}),
                "Agent": order_data.get("salesperson", ""),
                "SalesLocation": order_data.get("sales_location", "HQ"),
                "DocumentDate": order_data.get("date", datetime.now(timezone.utc).isoformat()),
                "CreditTerm": order_data.get("credit_term", ""),
                "ShipVia": order_data.get("ship_via", ""),
                "ShipInfo": order_data.get("ship_info", ""),
                "InclusiveTax": order_data.get("inclusive_tax", False),
                "Description": order_data.get("description", ""),
                "Ref": order_data.get("ref", ""),
                "RefDocNo": order_data.get("ref_doc_no", ""),
                "Note": order_data.get("note", ""),
                "CurrencyCode": order_data.get("currency_code", "MYR"),
                "CurrencyRate": order_data.get("currency_rate", 1),
                "DetailsLine": []
            }

            # Map items to DetailsLine
            for item in order_data.get("items", []):
                detail_line = {
                    "Item": item.get("item_code"),
                    "UOM": item.get("uom", "UNIT"),
                    "Qty": item.get("quantity", 0),
                    "UnitPrice": item.get("unit_price", 0),
                    "Description": item.get("description", ""),
                    "Location": item.get("location", "HQ"),
                    "AccNo": item.get("acc_no", ""),
                    "DeliveryDate": item.get("delivery_date", datetime.now(timezone.utc).isoformat()),
                    "RowState": 0,
                    "Tax": item.get("tax", ""),
                    "Discount": item.get("discount", ""),
                    "Project": item.get("project", ""),
                    "Dept": item.get("department", "")
                }
                so_data["DetailsLine"].append(detail_line)

            # Execute async request
            result = asyncio.run(self._execute_async_request("/api/public/v1/SalesOrder", so_data))

            # Extract document number from result
            doc_no = result.get("Number")
            logger.info(f"Created Sales Order: {doc_no}")
            return doc_no

        except Exception as e:
            logger.error(f"Failed to create sales order: {e}")
            return None

    def create_invoice(self, order_data: Dict[str, Any]) -> Optional[str]:
        """
        Create an AR Invoice in AutoCount via AOTG API.
        Returns the invoice number.
        """
        if self._mock_mode:
            logger.warning("Using mock mode for create_invoice")
            return None

        try:
            # Map order data to AOTG AR Invoice structure
            invoice_data = {
                "DebtorCode": order_data.get("customer_id"),
                "Description": order_data.get("description", ""),
                "DocDate": order_data.get("date", datetime.now().strftime("%Y-%m-%d")),
                "DocNo": order_data.get("doc_no", ""),  # Optional: let AutoCount auto-generate
                "JournalType": "SALES",
                "RefNo2": order_data.get("ref_no2", ""),
                "InclusiveTax": order_data.get("inclusive_tax", False),
                "Agent": order_data.get("salesperson", ""),
                "CreditTerm": order_data.get("credit_term", ""),
                "CurrencyCode": order_data.get("currency_code", "MYR"),
                "DetailsLine": []
            }

            # Map items to DetailsLine (AR Invoice uses AccNo, Description, Tax, Amount)
            for item in order_data.get("items", []):
                detail_line = {
                    "LineState": 1,  # Indicates new line
                    "AccNo": item.get("acc_no", ""),
                    "Description": item.get("description", ""),
                    "Tax": item.get("tax", ""),
                    "Amount": item.get("amount", 0)
                }
                invoice_data["DetailsLine"].append(detail_line)

            # Execute async request
            result = asyncio.run(self._execute_async_request("/api/public/v1/ARInvoice/CreateARInvoice", invoice_data))

            # Extract document number from result
            doc_no = result.get("DocNo")
            logger.info(f"Created AR Invoice: {doc_no}")
            return doc_no

        except Exception as e:
            logger.error(f"Failed to create invoice: {e}")
            return None

    def create_delivery_order(self, order_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a delivery order in AutoCount via AOTG API.
        Returns the DO number.
        """
        if self._mock_mode:
            logger.warning("Using mock mode for create_delivery_order")
            return None

        try:
            # Map order data to AOTG DeliveryOrder structure
            do_data = {
                "Debtor": order_data.get("customer_id"),
                "DebtorName": order_data.get("customer_name", ""),
                "DeliverAddress": order_data.get("delivery_address", {}),
                "InvoiceAddress": order_data.get("invoice_address", {}),
                "Agent": order_data.get("salesperson", ""),
                "SalesLocation": order_data.get("sales_location", "HQ"),
                "DocumentDate": order_data.get("date", datetime.now(timezone.utc).isoformat()),
                "CreditTerm": order_data.get("credit_term", ""),
                "ShipVia": order_data.get("ship_via", ""),
                "ShipInfo": order_data.get("ship_info", ""),
                "InclusiveTax": order_data.get("inclusive_tax", False),
                "Description": order_data.get("description", ""),
                "Ref": order_data.get("ref", ""),
                "RefDocNo": order_data.get("ref_doc_no", ""),
                "Note": order_data.get("note", ""),
                "CurrencyCode": order_data.get("currency_code", "MYR"),
                "CurrencyRate": order_data.get("currency_rate", 1),
                "UnPostToGL": order_data.get("un_post_to_gl", False),
                "UnPostToStock": order_data.get("un_post_to_stock", False),
                "DetailsLine": []
            }

            # Map items to DetailsLine
            for item in order_data.get("items", []):
                detail_line = {
                    "Item": item.get("item_code"),
                    "UOM": item.get("uom", "UNIT"),
                    "Qty": item.get("quantity", 0),
                    "UnitPrice": item.get("unit_price", 0),
                    "Description": item.get("description", ""),
                    "Location": item.get("location", "HQ"),
                    "AccNo": item.get("acc_no", ""),
                    "DeliveryDate": item.get("delivery_date", datetime.now(timezone.utc).isoformat()),
                    "RowState": 0,
                    "Tax": item.get("tax", ""),
                    "Discount": item.get("discount", ""),
                    "Project": item.get("project", ""),
                    "Dept": item.get("department", "")
                }
                do_data["DetailsLine"].append(detail_line)

            # Execute async request
            result = asyncio.run(self._execute_async_request("/api/public/v1/DeliveryOrder", do_data))

            # Extract document number from result
            doc_no = result.get("Number")
            logger.info(f"Created Delivery Order: {doc_no}")
            return doc_no

        except Exception as e:
            logger.error(f"Failed to create delivery order: {e}")
            return None

    def get_pick_pack_status(self, order_id: str) -> Dict[str, Any]:
        """
        Get pick/pack status for an order.
        Uses DeliveryOrder endpoint to retrieve status.
        """
        if self._mock_mode:
            logger.warning("Using mock mode for get_pick_pack_status")
            return {"status": "ready", "message": "Mock: Order is ready for packing"}

        try:
            # Get Delivery Order by document number
            url = f"{self.base_url}/api/public/v1/DeliveryOrder/{order_id}"
            headers = self._get_headers()

            response = httpx.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            result = response.json()

            # Extract status information
            return {
                "order_id": order_id,
                "status": result.get("Number", "unknown"),
                "total": result.get("Total", 0),
                "outstanding": result.get("Outstanding", 0),
                "is_cancelled": result.get("IsCancelled", False)
            }

        except Exception as e:
            logger.error(f"Failed to get pick/pack status for {order_id}: {e}")
            return {"status": "error", "message": str(e)}


# Factory function to create the appropriate AutoCount client
def get_autocount_client() -> AutoCountClientInterface:
    """
    Factory function to create the AutoCount client.

    Priority:
    1. If AOTG credentials are configured, use AOTGClient
    2. Otherwise, fall back to MockAutoCountClient (for testing)
    """
    # Check if AOTG is configured
    pwd = settings.aotg_password.get_secret_value() if settings.aotg_password else ""
    key = settings.aotg_api_key.get_secret_value() if settings.aotg_api_key else ""
    if all([settings.aotg_username, pwd, key]):
        logger.info("Using AOTG AutoCount client")
        return AOTGClient()

    # Fall back to mock client
    logger.warning("No AOTG credentials configured - using mock client")
    from mock_autocount_client import MockAutoCountClient
    return MockAutoCountClient()


# Module-level client instance
autocount_client = get_autocount_client()
