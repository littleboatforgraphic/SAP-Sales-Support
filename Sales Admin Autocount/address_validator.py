"""
Address validation module for delivery address verification.
Compares PO delivery addresses against registered AutoCount customer addresses
with fraud prevention logic based on customer classification (trading house vs non-trading house).
"""
from typing import Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database import AddressValidationResult
from mock_autocount_client import MockAutoCountClient  # Will be replaced with real AutoCount client
import json
import re


class AddressValidator:
    """
    Validates delivery addresses against AutoCount customer master data.
    Uses token-overlap similarity scoring for robust matching.
    """

    def __init__(self, session: Session, autocount_client):
        self.session = session
        self.autocount_client = autocount_client

    def normalize_address(self, address: str) -> str:
        """
        Normalize address for comparison.
        Removes punctuation, normalizes whitespace, converts to lowercase.
        """
        normalized = address.lower().strip()
        normalized = re.sub(r'[^\w\s]', '', normalized)  # Remove punctuation
        normalized = re.sub(r'\s+', ' ', normalized)  # Normalize whitespace
        return normalized

    def calculate_similarity(self, addr1: str, addr2: str) -> float:
        """
        Calculate similarity between two addresses using token overlap.
        Returns a score between 0 and 1.
        """
        tokens1 = set(self.normalize_address(addr1).split())
        tokens2 = set(self.normalize_address(addr2).split())

        if not tokens1 or not tokens2:
            return 0.0

        # Jaccard similarity: intersection / union
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        return intersection / union if union > 0 else 0.0

    def validate_delivery_address(
        self,
        po_address: str,
        customer_id: str
    ) -> AddressValidationResult:
        """
        Validate PO delivery address against AutoCount customer master data.

        Args:
            po_address: Delivery address from the PO
            customer_id: AutoCount Debtor Code

        Returns:
            AddressValidationResult with validation details
        """
        # Get customer classification and registered addresses from AutoCount
        customer_data = self.autocount_client.get_customer_details(customer_id)
        if not customer_data:
            raise ValueError(f"Customer {customer_id} not found")

        is_trading_house = self.autocount_client.is_trading_house(customer_id)
        registered_addresses = self.autocount_client.get_customer_addresses(customer_id)

        # Calculate similarity with each registered address
        similarities = []
        for reg_addr in registered_addresses:
            similarity = self.calculate_similarity(po_address, reg_addr)
            similarities.append({
                "address": reg_addr,
                "similarity": similarity
            })

        # Find the best match
        best_match = max(similarities, key=lambda x: x["similarity"]) if similarities else None
        match_found = best_match and best_match["similarity"] >= 0.8  # 80% similarity threshold

        if match_found:
            validation_level = "match"
            requires_admin_approval = False
        elif is_trading_house:
            # Trading house: proceed with caution, admin double-confirmation
            validation_level = "trading_house_mismatch"
            requires_admin_approval = True
        else:
            # Non-trading house: high-risk, escalate to admin
            validation_level = "high_risk_mismatch"
            requires_admin_approval = True

        # Create database record
        result_db = AddressValidationResult(
            order_reference="",  # Will be set when called from order processing
            customer_id=customer_id,
            po_delivery_address=po_address,
            registered_addresses=json.dumps(registered_addresses),
            is_trading_house=is_trading_house,
            match_found=match_found,
            validation_level=validation_level,
            requires_admin_approval=requires_admin_approval,
            created_at=datetime.now(timezone.utc)
        )

        self.session.add(result_db)
        self.session.commit()

        return {
            "customer_id": customer_id,
            "po_delivery_address": po_address,
            "registered_addresses": registered_addresses,
            "is_trading_house": is_trading_house,
            "match_found": match_found,
            "best_similarity": best_match["similarity"] if best_match else 0.0,
            "validation_level": validation_level,
            "requires_admin_approval": requires_admin_approval
        }

    def get_validation_history(self, customer_id: str, limit: int = 50) -> List[AddressValidationResult]:
        """Get address validation history for a customer."""
        return self.session.query(AddressValidationResult).filter(
            AddressValidationResult.customer_id == customer_id
        ).order_by(AddressValidationResult.created_at.desc()).limit(limit).all()
