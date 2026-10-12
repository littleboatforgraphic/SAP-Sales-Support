"""
Simple AOTG catalog query agent for Telegram.

This agent allows users to query the AOTG operations catalog via Telegram.
It provides read-only access to the catalog information for testing and exploration.
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from aotg_knowledge_models import (
    AOTGOperation,
    AOTGSpecSnapshot,
    RiskLevel,
    AgentCommand,
    OperationPolicy,
)
from database import StaffAllowlistEntry

logger = logging.getLogger(__name__)


class AOTGQueryAgent:
    """Agent for querying AOTG operations catalog."""

    def __init__(self, db: Session):
        self.db = db

    def get_user_role(self, telegram_user_id: str) -> Optional[str]:
        """Get the user's role from the staff allowlist."""
        staff = (
            self.db.query(StaffAllowlistEntry)
            .filter(
                StaffAllowlistEntry.telegram_user_id == telegram_user_id,
                StaffAllowlistEntry.active == True,
            )
            .first()
        )
        return staff.role.value if staff else None

    def list_enabled_operations(self, user_role: Optional[str] = None) -> str:
        """List all enabled operations for the user's role."""
        query = self.db.query(AOTGOperation).filter(
            AOTGOperation.enabled_for_agent == True
        )

        operations = query.order_by(AOTGOperation.tag, AOTGOperation.http_method).all()

        if not operations:
            return "No AOTG operations are currently enabled for agent use."

        # Group by tag
        by_tag: Dict[str, List[AOTGOperation]] = {}
        for op in operations:
            tag = op.tag
            if tag not in by_tag:
                by_tag[tag] = []
            by_tag[tag].append(op)

        result = []
        result.append(f"Available AOTG Operations ({len(operations)}):\n")

        for tag, ops in sorted(by_tag.items()):
            result.append(f"\n[{tag}]")
            for op in ops:
                risk_emoji = self._risk_emoji(op.risk_level)
                result.append(
                    f"  {risk_emoji} {op.http_method} {op.path}"
                )
                if op.summary:
                    result.append(f"      {op.summary}")

        result.append("\nRisk Legend:")
        result.append("  🟢 READ_ONLY - Safe to execute")
        result.append("  🟡 BUSINESS_WRITE - Requires confirmation")
        result.append("  🟠 FINANCIAL_WRITE - Requires approval")
        result.append("  🔴 DESTRUCTIVE - Not enabled")

        return "\n".join(result)

    def get_operation_details(self, operation_id: str) -> str:
        """Get detailed information about a specific operation."""
        operation = (
            self.db.query(AOTGOperation)
            .filter(AOTGOperation.operation_id == operation_id)
            .first()
        )

        if not operation:
            return f"Operation not found: {operation_id}"

        result = []
        result.append(f"Operation: {operation.operation_id}")
        result.append(f"Tag: {operation.tag}")
        result.append(f"Method: {operation.http_method}")
        result.append(f"Path: {operation.path}")
        result.append(f"Risk Level: {operation.risk_level.value}")

        if operation.summary:
            result.append(f"\nSummary:\n{operation.summary}")

        if operation.description:
            result.append(f"\nDescription:\n{operation.description}")

        result.append(f"\nEnabled for Agent: {'Yes' if operation.enabled_for_agent else 'No'}")
        result.append(f"LLM May Propose: {'Yes' if operation.llm_may_propose else 'No'}")
        result.append(f"Execution Verified: {'Yes' if operation.execution_verified else 'No'}")

        if operation.parameters_schema:
            result.append(f"\nParameters ({len(operation.parameters_schema)}):")
            for param in operation.parameters_schema:
                required = " [required]" if param.get("required") else ""
                result.append(f"  - {param['name']}: {param.get('in')}{required}")
                if param.get("description"):
                    result.append(f"    {param['description']}")

        return "\n".join(result)

    def search_operations(self, query: str) -> str:
        """Search operations by tag, path, or summary."""
        search_pattern = f"%{query}%"

        operations = (
            self.db.query(AOTGOperation)
            .filter(
                AOTGOperation.enabled_for_agent == True,
                (
                    AOTGOperation.tag.ilike(search_pattern)
                    | AOTGOperation.path.ilike(search_pattern)
                    | AOTGOperation.summary.ilike(search_pattern)
                    | AOTGOperation.description.ilike(search_pattern)
                ),
            )
            .order_by(AOTGOperation.tag, AOTGOperation.http_method)
            .limit(20)
            .all()
        )

        if not operations:
            return f"No operations found matching: {query}"

        result = []
        result.append(f"Operations matching '{query}' ({len(operations)}):\n")

        for op in operations:
            risk_emoji = self._risk_emoji(op.risk_level)
            result.append(f"{risk_emoji} {op.http_method} {op.path}")
            result.append(f"  Tag: {op.tag}")
            if op.summary:
                result.append(f"  {op.summary}")
            result.append("")

        return "\n".join(result)

    def list_by_tag(self, tag: str) -> str:
        """List operations filtered by tag."""
        operations = (
            self.db.query(AOTGOperation)
            .filter(
                AOTGOperation.enabled_for_agent == True,
                AOTGOperation.tag == tag,
            )
            .order_by(AOTGOperation.http_method, AOTGOperation.path)
            .all()
        )

        if not operations:
            return f"No enabled operations found for tag: {tag}"

        result = []
        result.append(f"Operations in [{tag}] ({len(operations)}):\n")

        for op in operations:
            risk_emoji = self._risk_emoji(op.risk_level)
            result.append(f"{risk_emoji} {op.http_method} {op.path}")
            if op.summary:
                result.append(f"  {op.summary}")

        return "\n".join(result)

    def get_catalog_summary(self) -> str:
        """Get a summary of the loaded AOTG catalog."""
        snapshot = (
            self.db.query(AOTGSpecSnapshot)
            .filter(AOTGSpecSnapshot.active == True)
            .first()
        )

        if not snapshot:
            return "No active AOTG catalog loaded."

        total_ops = (
            self.db.query(AOTGOperation)
            .filter(AOTGOperation.spec_snapshot_id == snapshot.id)
            .count()
        )

        enabled_ops = (
            self.db.query(AOTGOperation)
            .filter(
                AOTGOperation.spec_snapshot_id == snapshot.id,
                AOTGOperation.enabled_for_agent == True,
            )
            .count()
        )

        # Count by risk level
        risk_counts = {}
        for risk in RiskLevel:
            count = (
                self.db.query(AOTGOperation)
                .filter(
                    AOTGOperation.spec_snapshot_id == snapshot.id,
                    AOTGOperation.risk_level == risk,
                )
                .count()
            )
            risk_counts[risk.value] = count

        result = []
        result.append("AOTG Catalog Summary")
        result.append("=" * 40)
        result.append(f"Base URL: {snapshot.base_url}")
        result.append(f"Document Version: {snapshot.document_version}")
        result.append(f"Swagger Version: {snapshot.swagger_version}")
        result.append(f"Total Operations: {total_ops}")
        result.append(f"Enabled for Agent: {enabled_ops}")
        result.append(f"Document SHA256: {snapshot.document_sha256[:16]}...")
        result.append("\nOperations by Risk Level:")
        for risk, count in risk_counts.items():
            result.append(f"  {risk}: {count}")

        return "\n".join(result)

    def _risk_emoji(self, risk_level: RiskLevel) -> str:
        """Get emoji for risk level."""
        emojis = {
            RiskLevel.READ_ONLY: "🟢",
            RiskLevel.BUSINESS_WRITE: "🟡",
            RiskLevel.FINANCIAL_WRITE: "🟠",
            RiskLevel.DESTRUCTIVE: "🔴",
        }
        return emojis.get(risk_level, "⚪")

    def handle_message(self, message: str, user_id: str) -> str:
        """
        Handle a user message and return the response.

        Commands:
        - /catalog - Show catalog summary
        - /list - List all enabled operations
        - /list <tag> - List operations by tag
        - /search <query> - Search operations
        - /details <operation_id> - Show operation details
        """
        message = message.strip()

        if message == "/catalog":
            return self.get_catalog_summary()
        elif message == "/list":
            return self.list_enabled_operations()
        elif message.startswith("/list "):
            tag = message[6:].strip()
            return self.list_by_tag(tag)
        elif message.startswith("/search "):
            query = message[8:].strip()
            return self.search_operations(query)
        elif message.startswith("/details "):
            operation_id = message[9:].strip()
            return self.get_operation_details(operation_id)
        elif message == "/help":
            return self._get_help()
        else:
            return self._get_help()

    def _get_help(self) -> str:
        """Get help message."""
        return """AOTG Catalog Query Commands:

/catalog - Show catalog summary
/list - List all enabled operations
/list <tag> - List operations by tag (e.g., /list Debtor)
/search <query> - Search operations (e.g., /search invoice)
/details <operation_id> - Show operation details
/help - Show this help message

Example:
  /list Debtor
  /search sales order
  /details POST /api/public/v1/SalesOrder
"""
