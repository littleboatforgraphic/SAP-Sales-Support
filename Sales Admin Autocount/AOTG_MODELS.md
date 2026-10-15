# AOTG API Data Models - Feature-Specific Split

## Overview

The large `Autocount_API_Definition.json` (312KB) has been split into smaller, feature-specific JSON files and converted to Pydantic models for type-safe API integration.

## Files Created

### 1. Feature-Specific JSON Files (in `docs/`)

- **`aotg_sales_invoice.json`** (21KB) - Sales Order and AR Invoice operations
  - 13 paths, 21 definitions
  - Used by: Order-to-Invoice Agent

- **`aotg_delivery_order.json`** (15KB) - Delivery Order operations
  - 9 paths, 13 definitions
  - Used by: Shipment Agent

- **`aotg_customer.json`** (12KB) - Debtor/Customer operations
  - 3 paths, 12 definitions
  - Used by: Customer Onboarding Agent, Order-to-Invoice Agent

- **`aotg_stock.json`** (12KB) - Stock Item operations
  - 5 paths, 8 definitions
  - Used by: Stock & Quote Agent

### 2. Pydantic Model Files (in root directory)

- **`aotg_sales_invoice_models.py`** - Type-safe models for Sales Order and AR Invoice
  - `CreateSalesOrderParam` - Sales Order creation parameters
  - `CreateARInvoiceParam` - AR Invoice creation parameters
  - `AddressEntity` - Address information
  - `SalesOrderResult`, `ARInvoiceResult` - API response models

- **`aotg_delivery_order_models.py`** - Type-safe models for Delivery Order
  - `CreateDeliveryOrderParam` - Delivery Order creation parameters
  - `CreateDeliveryOrderLineParam` - Line item parameters
  - `DeliveryOrderResult` - API response model

- **`aotg_customer_models.py`** - Type-safe models for Customer/Debtor
  - `DebtorCreateEntity` - Customer creation parameters
  - `DebtorGetResultEntity` - Customer retrieval result
  - `DebtorListResultEntity` - Customer list result
  - `DebtorBranchEntity` - Branch information
  - `AddressEntity` - Address information

- **`aotg_stock_models.py`** - Type-safe models for Stock
  - `StockItemResult` - Stock item details
  - `StockItemListResult` - Stock item list
  - `CreateStockItemParam` - Stock item creation parameters
  - `IStockItemUOMEntity` - UOM information

## Updated Files

### 1. `autocount_client.py`

**Changes:**
- Added imports for Pydantic models from the feature-specific model files
- Updated `AutoCountClientInterface` abstract methods to use typed parameters:
  - `create_sales_order(order_data: CreateSalesOrderParam)`
  - `create_invoice(invoice_data: CreateARInvoiceParam)`
  - `create_delivery_order(do_data: CreateDeliveryOrderParam)`
- Updated `AOTGClient` implementation:
  - Simplified methods to use `model_dump(exclude_none=True)` instead of manual dict mapping
  - Changed synchronous methods to async (await pattern for AOTG API calls)
  - Removed complex manual field mapping (now handled by Pydantic models)

**Benefits:**
- Type safety at compile time
- IDE autocomplete for all fields
- Validation of data structure before API calls
- Cleaner, more maintainable code

### 2. `mock_autocount_client.py`

**Changes:**
- Added imports for Pydantic models
- Updated method signatures to match the interface:
  - `create_sales_order(order_data: CreateSalesOrderParam)`
  - `create_invoice(invoice_data: CreateARInvoiceParam)`
  - `create_delivery_order(do_data: CreateDeliveryOrderParam)`

**Benefits:**
- Consistent interface between mock and real client
- Type-safe mock implementations

## Usage Examples

### Creating a Sales Order

```python
from aotg_sales_invoice_models import CreateSalesOrderParam, CreateSalesOrderLineParam, AddressEntity
from autocount_client import AOTGClient

client = AOTGClient()

# Create sales order with type-safe model
order = CreateSalesOrderParam(
    Debtor="300-A001",
    DebtorName="ABC Trading Sdn Bhd",
    DocumentDate="2026-10-13",
    CreditTerm="30",
    DeliverAddress=AddressEntity(
        Contact="Mr. Tan",
        Phone="02111373",
        Address1="123, Jalan Industri",
        Address2="40000 Shah Alam",
        Address3="Selangor",
        Address4="50000 Malaysia"
    ),
    DetailsLine=[
        CreateSalesOrderLineParam(
            Item="WM-001",
            UOM="UNIT",
            Qty=100,
            UnitPrice=15.50,
            Description="Wire Mesh 1x1"
        )
    ]
)

# Create order (async)
order_no = await client.create_sales_order(order)
print(f"Created order: {order_no}")
```

### Creating an AR Invoice

```python
from aotg_sales_invoice_models import CreateARInvoiceParam, CreateARInvoiceLineParam

invoice = CreateARInvoiceParam(
    Debtor="300-A001",
    DebtorName="ABC Trading Sdn Bhd",
    DocumentDate="2026-10-13",
    CreditTerm="30",
    DetailsLine=[
        CreateARInvoiceLineParam(
            AccNo="300-A001",
            Description="Wire Mesh 1x1",
            Tax="SST",
            Amount=1550.00
        )
    ]
)

invoice_no = await client.create_invoice(invoice)
print(f"Created invoice: {invoice_no}")
```

### Creating a Delivery Order

```python
from aotg_delivery_order_models import CreateDeliveryOrderParam, CreateDeliveryOrderLineParam

do = CreateDeliveryOrderParam(
    Debtor="300-A001",
    DebtorName="ABC Trading Sdn Bhd",
    DocumentDate="2026-10-13",
    ShipVia="Own Transport",
    DetailsLine=[
        CreateDeliveryOrderLineParam(
            Item="WM-001",
            UOM="UNIT",
            Qty=100,
            UnitPrice=15.50,
            Description="Wire Mesh 1x1"
        )
    ]
)

do_no = await client.create_delivery_order(do)
print(f"Created delivery order: {do_no}")
```

## Benefits of This Approach

1. **Type Safety**: Pydantic models validate data at runtime and provide IDE autocomplete
2. **Smaller Files**: Each feature-specific JSON is 10-20KB instead of 312KB
3. **Faster Loading**: Only load the models you need for each agent
4. **Clear Separation**: Each agent uses only its relevant models
5. **Easier Maintenance**: Changes to one feature don't affect others
6. **Better Error Handling**: Pydantic validation catches data errors before API calls
7. **Documentation**: Type hints serve as inline documentation

## Migration Notes

If you have existing code using the old dict-based approach:

**Before:**
```python
order_data = {
    "customer_id": "300-A001",
    "customer_name": "ABC Trading",
    "items": [...]
}
doc_no = client.create_sales_order(order_data)
```

**After:**
```python
order = CreateSalesOrderParam(
    Debtor="300-A001",
    DebtorName="ABC Trading",
    DetailsLine=[...]
)
doc_no = await client.create_sales_order(order)
```

## Original JSON Reference

The full `Autocount_API_Definition.json` (312KB) has been moved to `docs/` for reference. All feature-specific JSON files are also in `docs/`.

If you need to add more endpoints:

1. Find the endpoint in `docs/Autocount_API_Definition.json`
2. Use `split_aotg_api.py` to extract it to a feature-specific JSON
3. Manually add the Pydantic model to the appropriate model file
4. Update the relevant agent to use the new model
