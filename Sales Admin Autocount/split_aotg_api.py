"""
Split the large AOTG API definition into feature-specific JSON files.
"""
import json
from typing import Dict, Any, Set


def extract_definition_refs(schema: Any, definitions: Dict[str, Any], collected: Set[str]) -> None:
    """Recursively collect all $ref definitions."""
    if isinstance(schema, dict):
        if '$ref' in schema:
            ref = schema['$ref'].replace('#/definitions/', '')
            if ref not in collected:
                collected.add(ref)
                if ref in definitions:
                    extract_definition_refs(definitions[ref], definitions, collected)
        for value in schema.values():
            extract_definition_refs(value, definitions, collected)
    elif isinstance(schema, list):
        for item in schema:
            extract_definition_refs(item, definitions, collected)


def extract_feature_json(
    full_data: Dict[str, Any],
    feature_name: str,
    path_keywords: list[str],
    output_file: str
) -> None:
    """Extract paths and definitions for a specific feature."""
    
    # Find matching paths
    matching_paths = {}
    for path, details in full_data['paths'].items():
        if any(keyword in path for keyword in path_keywords):
            matching_paths[path] = details
    
    if not matching_paths:
        print(f"No paths found for {feature_name}")
        return
    
    # Collect all referenced definitions
    definitions = full_data.get('definitions', {})
    collected_refs = set()
    
    for path_details in matching_paths.values():
        # Check both POST parameters and responses
        for operation in path_details.values():
            if isinstance(operation, dict):
                if 'parameters' in operation:
                    for param in operation['parameters']:
                        if 'schema' in param:
                            extract_definition_refs(param['schema'], definitions, collected_refs)
                if 'responses' in operation:
                    for response in operation['responses'].values():
                        if 'schema' in response:
                            extract_definition_refs(response['schema'], definitions, collected_refs)
    
    # Build the feature-specific JSON
    feature_data = {
        'swagger': full_data['swagger'],
        'info': full_data['info'],
        'host': full_data['host'],
        'schemes': full_data['schemes'],
        'paths': matching_paths,
        'definitions': {
            ref: definitions[ref]
            for ref in collected_refs
            if ref in definitions
        }
    }
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(feature_data, f, indent=2, ensure_ascii=False)
    
    print(f"Created {output_file}")
    print(f"  Paths: {len(matching_paths)}")
    print(f"  Definitions: {len(collected_refs)}")
    print(f"  Size: {len(json.dumps(feature_data))} bytes")


def main():
    """Split the AOTG API definition into feature-specific files."""
    
    # Load the full JSON
    with open('Autocount_API_Definition.json', 'r', encoding='utf-8') as f:
        full_data = json.load(f)
    
    print("Splitting AOTG API definition into feature-specific files...")
    print()
    
    # Extract Sales Order & Invoice (for Order-to-Invoice Agent)
    extract_feature_json(
        full_data,
        'Sales & Invoice',
        ['SalesOrder', 'ARInvoice'],
        'aotg_sales_invoice.json'
    )
    
    # Extract Delivery Order (for Shipment Agent)
    extract_feature_json(
        full_data,
        'Delivery Order',
        ['DeliveryOrder'],
        'aotg_delivery_order.json'
    )
    
    # Extract Debtor/Customer (for Customer Onboarding & Order-to-Invoice)
    extract_feature_json(
        full_data,
        'Customer',
        ['Debtor'],
        'aotg_customer.json'
    )
    
    # Extract Stock (for Stock & Quote Agent)
    extract_feature_json(
        full_data,
        'Stock',
        ['StockItem', 'StockBalance'],
        'aotg_stock.json'
    )
    
    print()
    print("Done! Created 4 feature-specific JSON files:")
    print("  - aotg_sales_invoice.json")
    print("  - aotg_delivery_order.json")
    print("  - aotg_customer.json")
    print("  - aotg_stock.json")


if __name__ == "__main__":
    main()
