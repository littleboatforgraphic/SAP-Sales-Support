"""
Pydantic models for AOTG Customer/Debtor operations.

Extracted from aotg_customer.json for Customer Onboarding and Order-to-Invoice Agents.
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


class DebtorBranchEntity(BaseModel):
    """Branch information for a debtor."""
    IsActive: Optional[bool] = None
    Code: Optional[str] = None
    Name: Optional[str] = None
    Address1: Optional[str] = None
    Address2: Optional[str] = None
    Address3: Optional[str] = None
    Address4: Optional[str] = None


class DebtorCreateEntity(BaseModel):
    """Parameters for creating a Debtor (customer)."""
    AccNo: Optional[str] = None
    CompanyName: Optional[str] = None
    RegisterNo: Optional[str] = None
    Description: Optional[str] = None
    Telephone: Optional[str] = None
    Fax: Optional[str] = None
    Email: Optional[str] = None
    Area: Optional[str] = None
    Salesperson: Optional[str] = None
    CreditTerm: Optional[str] = None
    CreditLimit: Optional[float] = None
    DeliveryAddress: Optional[AddressEntity] = None
    InvoiceAddress: Optional[AddressEntity] = None
    BranchList: Optional[List[DebtorBranchEntity]] = None


class DebtorGetResultEntity(BaseModel):
    """Result from getting a Debtor."""
    AccNo: Optional[str] = None
    CompanyName: Optional[str] = None
    RegisterNo: Optional[str] = None
    Description: Optional[str] = None
    Telephone: Optional[str] = None
    Fax: Optional[str] = None
    Email: Optional[str] = None
    Area: Optional[str] = None
    Salesperson: Optional[str] = None
    CreditTerm: Optional[str] = None
    CreditLimit: Optional[float] = None
    DeliveryAddress: Optional[AddressEntity] = None
    InvoiceAddress: Optional[AddressEntity] = None
    BranchList: Optional[List[DebtorBranchEntity]] = None


class DebtorListResultEntity(BaseModel):
    """Result from listing Debtors."""
    AccNo: Optional[str] = None
    CompanyName: Optional[str] = None
    RegisterNo: Optional[str] = None
    Description: Optional[str] = None
    Telephone: Optional[str] = None
    Fax: Optional[str] = None
    Email: Optional[str] = None
    Area: Optional[str] = None
    Salesperson: Optional[str] = None
    CreditTerm: Optional[str] = None
    CreditLimit: Optional[float] = None
