"""
SAP Client for Sales Admin AI Agent System.

This module provides the interface to SAP for customer data, stock information,
and document creation (sales orders, invoices, delivery orders).

Two integration methods are supported:
1. OData (S/4HANA) - RESTful API
2. RFC/BAPI (ECC) - Remote Function Call

IMPLEMENTATION REQUIRED:
- Choose one integration method based on your SAP system
- Implement the methods below with actual SAP calls
- Add appropriate dependencies to requirements.txt
- Test SAP connection independently before agent integration
"""

import logging
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod

from config import settings

logger = logging.getLogger(__name__)


class SAPClientInterface(ABC):
    """Abstract base class for SAP client implementations."""

    @abstractmethod
    def get_customer_details(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve customer details from SAP."""
        pass

    @abstractmethod
    def get_stock_info(self, sku: str) -> Optional[Dict[str, Any]]:
        """Retrieve stock information for a product."""
        pass

    @abstractmethod
    def get_customer_addresses(self, customer_id: str) -> List[Dict[str, Any]]:
        """Retrieve all registered addresses for a customer."""
        pass

    @abstractmethod
    def is_trading_house(self, customer_id: str) -> bool:
        """Check if customer is classified as a trading house."""
        pass

    @abstractmethod
    def create_sales_order(self, order_data: Dict[str, Any]) -> Optional[str]:
        """Create a sales order in SAP and return the order number."""
        pass

    @abstractmethod
    def create_invoice(self, order_id: str) -> Optional[str]:
        """Create an invoice for a sales order and return the invoice number."""
        pass

    @abstractmethod
    def create_delivery_order(self, order_id: str) -> Optional[str]:
        """Create a delivery order and return the DO number."""
        pass

    @abstractmethod
    def get_pick_pack_status(self, order_id: str) -> Dict[str, Any]:
        """Get pick/pack status for an order."""
        pass


class ODataSAPClient(SAPClientInterface):
    """
    SAP client using OData (S/4HANA).

    Requires:
    - httpx (already in requirements.txt)
    - SAP OData service endpoint
    - SAP credentials (username/password or OAuth token)
    """

    def __init__(self):
        self.base_url = settings.sap_base_url
        self.odata_path = settings.sap_odata_path
        self.username = settings.sap_username
        self.password = settings.sap_password

        if not all([self.base_url, self.odata_path, self.username, self.password]):
            logger.warning("OData SAP client not fully configured - using mock mode")
            self._mock_mode = True
        else:
            self._mock_mode = False

    def _get_full_url(self, endpoint: str) -> str:
        """Construct full OData URL."""
        return f"{self.base_url}{self.odata_path}/{endpoint}"

    def get_customer_details(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve customer details from SAP via OData.

        TODO: Implement actual OData call
        Example:
            url = self._get_full_url(f"CustomerSet('{customer_id}')")
            response = httpx.get(url, auth=(self.username, self.password))
            return response.json()
        """
        if self._mock_mode:
            logger.warning("Using mock mode for get_customer_details")
            return None

        # TODO: Implement OData call
        raise NotImplementedError("OData implementation required")

    def get_stock_info(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve stock information for a product via OData.

        TODO: Implement actual OData call
        """
        if self._mock_mode:
            logger.warning("Using mock mode for get_stock_info")
            return None

        # TODO: Implement OData call
        raise NotImplementedError("OData implementation required")

    def get_customer_addresses(self, customer_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all registered addresses for a customer via OData.

        TODO: Implement actual OData call
        """
        if self._mock_mode:
            logger.warning("Using mock mode for get_customer_addresses")
            return []

        # TODO: Implement OData call
        raise NotImplementedError("OData implementation required")

    def is_trading_house(self, customer_id: str) -> bool:
        """
        Check if customer is classified as a trading house via OData.

        TODO: Implement actual OData call
        """
        if self._mock_mode:
            logger.warning("Using mock mode for is_trading_house")
            return False

        # TODO: Implement OData call
        raise NotImplementedError("OData implementation required")

    def create_sales_order(self, order_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a sales order in SAP via OData.

        TODO: Implement actual OData POST call
        """
        if self._mock_mode:
            logger.warning("Using mock mode for create_sales_order")
            return None

        # TODO: Implement OData POST call
        raise NotImplementedError("OData implementation required")

    def create_invoice(self, order_id: str) -> Optional[str]:
        """
        Create an invoice for a sales order via OData.

        TODO: Implement actual OData call
        """
        if self._mock_mode:
            logger.warning("Using mock mode for create_invoice")
            return None

        # TODO: Implement OData call
        raise NotImplementedError("OData implementation required")

    def create_delivery_order(self, order_id: str) -> Optional[str]:
        """
        Create a delivery order via OData.

        TODO: Implement actual OData call
        """
        if self._mock_mode:
            logger.warning("Using mock mode for create_delivery_order")
            return None

        # TODO: Implement OData call
        raise NotImplementedError("OData implementation required")

    def get_pick_pack_status(self, order_id: str) -> Dict[str, Any]:
        """
        Get pick/pack status for an order via OData.

        TODO: Implement actual OData call
        """
        if self._mock_mode:
            logger.warning("Using mock mode for get_pick_pack_status")
            return {}

        # TODO: Implement OData call
        raise NotImplementedError("OData implementation required")


class RFCSAPClient(SAPClientInterface):
    """
    SAP client using RFC/BAPI (ECC).

    Requires:
    - pyrfc library (add to requirements.txt: pyrfc>=2.4.0)
    - SAP connection parameters (ASHOST, SYSNR, CLIENT, USER, PASSWORD)
    - SAPNW RFC library installed on the system
    """

    def __init__(self):
        self.ashost = settings.sap_ashost
        self.sysnr = settings.sap_sysnr
        self.client = settings.sap_client
        self.user = settings.sap_user
        self.password = settings.sap_password_rfc

        if not all([self.ashost, self.sysnr, self.client, self.user, self.password]):
            logger.warning("RFC SAP client not fully configured - using mock mode")
            self._mock_mode = True
        else:
            self._mock_mode = False
            # TODO: Initialize pyrfc connection
            # from pyrfc import Connection
            # self.conn = Connection(ashost=self.ashost, sysnr=self.sysnr,
            #                        client=self.client, user=self.user,
            #                        passwd=self.password)

    def get_customer_details(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve customer details from SAP via RFC.

        TODO: Implement actual RFC call using BAPI_CUSTOMER_GETDETAIL
        Example:
            result = self.conn.call('BAPI_CUSTOMER_GETDETAIL',
                                   CUSTOMERNO=customer_id)
            return result
        """
        if self._mock_mode:
            logger.warning("Using mock mode for get_customer_details")
            return None

        # TODO: Implement RFC call
        raise NotImplementedError("RFC implementation required")

    def get_stock_info(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve stock information for a product via RFC.

        TODO: Implement actual RFC call using BAPI_MATERIAL_STOCK_REQ_LIST
        """
        if self._mock_mode:
            logger.warning("Using mock mode for get_stock_info")
            return None

        # TODO: Implement RFC call
        raise NotImplementedError("RFC implementation required")

    def get_customer_addresses(self, customer_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all registered addresses for a customer via RFC.

        TODO: Implement actual RFC call using BAPI_ADDRESS_GETDETAIL
        """
        if self._mock_mode:
            logger.warning("Using mock mode for get_customer_addresses")
            return []

        # TODO: Implement RFC call
        raise NotImplementedError("RFC implementation required")

    def is_trading_house(self, customer_id: str) -> bool:
        """
        Check if customer is classified as a trading house via RFC.

        TODO: Implement actual RFC call to check customer classification
        """
        if self._mock_mode:
            logger.warning("Using mock mode for is_trading_house")
            return False

        # TODO: Implement RFC call
        raise NotImplementedError("RFC implementation required")

    def create_sales_order(self, order_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a sales order in SAP via RFC.

        TODO: Implement actual RFC call using BAPI_SALESORDER_CREATEFROMDAT2
        """
        if self._mock_mode:
            logger.warning("Using mock mode for create_sales_order")
            return None

        # TODO: Implement RFC call
        raise NotImplementedError("RFC implementation required")

    def create_invoice(self, order_id: str) -> Optional[str]:
        """
        Create an invoice for a sales order via RFC.

        TODO: Implement actual RFC call using BAPI_BILLINGDOC_CREATE
        """
        if self._mock_mode:
            logger.warning("Using mock mode for create_invoice")
            return None

        # TODO: Implement RFC call
        raise NotImplementedError("RFC implementation required")

    def create_delivery_order(self, order_id: str) -> Optional[str]:
        """
        Create a delivery order via RFC.

        TODO: Implement actual RFC call using BAPI_DELIVERY_CREATE
        """
        if self._mock_mode:
            logger.warning("Using mock mode for create_delivery_order")
            return None

        # TODO: Implement RFC call
        raise NotImplementedError("RFC implementation required")

    def get_pick_pack_status(self, order_id: str) -> Dict[str, Any]:
        """
        Get pick/pack status for an order via RFC.

        TODO: Implement actual RFC call to check delivery status
        """
        if self._mock_mode:
            logger.warning("Using mock mode for get_pick_pack_status")
            return {}

        # TODO: Implement RFC call
        raise NotImplementedError("RFC implementation required")


# Factory function to create the appropriate SAP client
def get_sap_client() -> SAPClientInterface:
    """
    Factory function to create the appropriate SAP client based on configuration.

    Priority:
    1. If OData credentials are configured, use ODataSAPClient
    2. If RFC credentials are configured, use RFCSAPClient
    3. Otherwise, fall back to MockSAPClient (for testing)
    """
    # Check if OData is configured
    if all([settings.sap_base_url, settings.sap_odata_path,
            settings.sap_username, settings.sap_password]):
        logger.info("Using OData SAP client")
        return ODataSAPClient()

    # Check if RFC is configured
    if all([settings.sap_ashost, settings.sap_sysnr, settings.sap_client,
            settings.sap_user, settings.sap_password_rfc]):
        logger.info("Using RFC SAP client")
        return RFCSAPClient()

    # Fall back to mock client
    logger.warning("No SAP credentials configured - using mock client")
    from mock_sap_client import MockSAPClient
    return MockSAPClient()


# Module-level client instance
sap_client = get_sap_client()
