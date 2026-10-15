"""
Pydantic models for AOTG Stock Item operations.

Extracted from aotg_stock.json for Stock & Quote Agent.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class IStockItemUOMEntity(BaseModel):
    """UOM information for a stock item."""
    UOM: Optional[str] = None
    Rate: Optional[float] = None


class StockItemResult(BaseModel):
    """Result from getting a Stock Item."""
    ItemCode: Optional[str] = None
    Description: Optional[str] = None
    UOM: Optional[str] = None
    StockQty: Optional[float] = None
    BaseCost: Optional[float] = None
    StdCost: Optional[float] = None
    StdPrice: Optional[float] = None
    UOMList: Optional[List[IStockItemUOMEntity]] = None


class StockItemListResult(BaseModel):
    """Result from listing Stock Items."""
    ItemCode: Optional[str] = None
    Description: Optional[str] = None
    UOM: Optional[str] = None
    StockQty: Optional[float] = None
    BaseCost: Optional[float] = None
    StdCost: Optional[float] = None
    StdPrice: Optional[float] = None


class CreateStockItemParam(BaseModel):
    """Parameters for creating a Stock Item."""
    ItemCode: Optional[str] = None
    Description: Optional[str] = None
    UOM: Optional[str] = None
    StockQty: Optional[float] = None
    BaseCost: Optional[float] = None
    StdCost: Optional[float] = None
    StdPrice: Optional[float] = None
