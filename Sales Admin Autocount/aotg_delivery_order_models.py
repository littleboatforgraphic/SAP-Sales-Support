"""
Pydantic models for AOTG Delivery Order operations.

Extracted from aotg_delivery_order.json for Shipment Agent.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class AddressEntity(BaseModel):
    """Address information."""
    Contact: Optional[str] = None
    Fax: Optional[str] = None
    Phone: Optional[str] = None
    Address1: Optional[str] = None
    Address2: Optional[str] = None
    Address3: Optional[str] = None
    Address4: Optional[str] = None


class CreateDeliveryOrderLineParam(BaseModel):
    """Line item for Delivery Order creation."""
    Id: Optional[str] = None
    Item: Optional[str] = None
    UOM: Optional[str] = None
    Qty: Optional[float] = None
    UnitPrice: Optional[float] = None
    Description: Optional[str] = None
    Location: Optional[str] = None
    AccNo: Optional[str] = None
    DeliveryDate: Optional[str] = None
    RowState: Optional[int] = None
    Tax: Optional[str] = None
    Discount: Optional[str] = None
    TaxRate: Optional[float] = None
    TaxAmount: Optional[float] = None
    SubTotal: Optional[float] = None
    SubTotalExTax: Optional[float] = None
    TaxableAmount: Optional[float] = None
    DiscountAmount: Optional[float] = None
    SmallestQty: Optional[float] = None
    SmallestUnitPrice: Optional[float] = None
    LocalTaxAmount: Optional[float] = None
    LocalSubTotal: Optional[float] = None
    LocalSubTotalExTax: Optional[float] = None
    LocalTaxableAmount: Optional[float] = None
    FurtherDescription: Optional[str] = None
    LineIndex: Optional[int] = None
    Project: Optional[str] = None
    Dept: Optional[str] = None
    SalesTaxExemptionNo: Optional[str] = None


class CreateDeliveryOrderParam(BaseModel):
    """Parameters for creating a Delivery Order."""
    Id: Optional[str] = None
    Debtor: Optional[str] = None
    DebtorName: Optional[str] = None
    DeliverAddress: Optional[AddressEntity] = None
    InvoiceAddress: Optional[AddressEntity] = None
    Agent: Optional[str] = None
    SalesLocation: Optional[str] = None
    DocumentDate: Optional[str] = None
    CreditTerm: Optional[str] = None
    ShipVia: Optional[str] = None
    ShipInfo: Optional[str] = None
    InclusiveTax: Optional[bool] = None
    Description: Optional[str] = None
    Ref: Optional[str] = None
    RefDocNo: Optional[str] = None
    Note: Optional[str] = None
    Outstanding: Optional[float] = None
    Number: Optional[str] = None
    TaxAmount: Optional[float] = None
    Total: Optional[float] = None
    NetTotal: Optional[float] = None
    IsRoundAdj: Optional[bool] = None
    RoundingMethod: Optional[int] = None
    RoundAdj: Optional[float] = None
    IsCancelled: Optional[bool] = None
    ToDocType: Optional[str] = None
    ToDocKey: Optional[str] = None
    CurrencyCode: Optional[str] = None
    CurrencySymbol: Optional[str] = None
    CurrencyRate: Optional[float] = None
    LocalNetTotal: Optional[float] = None
    LocalTaxAmount: Optional[float] = None
    UnPostToGL: Optional[bool] = None
    UnPostToStock: Optional[bool] = None
    DetailsLine: Optional[List[CreateDeliveryOrderLineParam]] = None


class DeliveryOrderResult(BaseModel):
    """Result from Delivery Order creation."""
    Id: Optional[str] = None
    Number: Optional[str] = None
    Debtor: Optional[str] = None
    Total: Optional[float] = None
