"""Controlled importer for the AOTG Swagger 2.0 operation catalog.

The caller supplies an already-fetched specification. Fetching is intentionally
kept outside request handling so a remote document cannot alter an agent's tool
catalog while a user message is being processed.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from aotg_knowledge_models import AOTGOperation, AOTGSpecSnapshot, RiskLevel


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


# Risk classification


FINANCIAL_TAGS = {
    "APCreditNote",
    "APInvoice",
    "APPayment",
    "ARCreditNote",
    "ARDebitNote",
    "ARDeposit",
    "ARInvoice",
    "CashBook",
    "CashSale",
    "CreditNote",
    "DebitNote",
    "JournalEntry",
    "Payment",
    "PaymentVoucher",
    "PurchaseInvoice",
    "PurchaseReturn",
    "ReceiptVoucher",
    "SalesInvoice",
}

DESTRUCTIVE_WORDS = {"delete", "cancel", "uncancel", "forfeit", "void"}
READ_WORDS = {"get", "list", "lookup", "search", "outstanding", "result"}


def classify_risk(method: str, path: str, operation: dict[str, Any]) -> RiskLevel:
    """Conservative heuristic. Every imported operation still requires review."""
    operation_id = operation.get("operationId", "")
    summary = operation.get("summary", "")
    searchable = f"{path} {operation_id} {summary}".lower()
    tag = (operation.get("tags") or ["Unknown"])[0]

    if method == "delete" or any(word in searchable for word in DESTRUCTIVE_WORDS):
        return RiskLevel.DESTRUCTIVE
    if method == "get":
        return RiskLevel.READ_ONLY

    # AOTG uses POST for a number of list/filter operations.
    normalized_id = operation_id.lower().replace("_", " ")
    normalized_summary = summary.lower().strip()
    if any(
        normalized_id.startswith(f"{tag.lower()} {word}")
        or normalized_summary.startswith(word)
        for word in READ_WORDS
    ):
        return RiskLevel.READ_ONLY

    if tag in FINANCIAL_TAGS:
        return RiskLevel.FINANCIAL_WRITE
    return RiskLevel.BUSINESS_WRITE


# Swagger reference resolution and input-schema extraction


def resolve_refs(
    node: Any,
    specification: dict[str, Any],
    stack: tuple[str, ...] = (),
    depth: int = 0,
) -> Any:
    """Resolve local definition references without infinitely expanding cycles."""
    if depth > 20:
        return copy.deepcopy(node)
    if isinstance(node, list):
        return [resolve_refs(item, specification, stack, depth + 1) for item in node]
    if not isinstance(node, dict):
        return copy.deepcopy(node)

    reference = node.get("$ref")
    if reference:
        prefix = "#/definitions/"
        if not reference.startswith(prefix) or reference in stack:
            return copy.deepcopy(node)
        name = reference[len(prefix) :]
        target = specification.get("definitions", {}).get(name)
        if target is None:
            return copy.deepcopy(node)
        merged = copy.deepcopy(target)
        merged.update({key: value for key, value in node.items() if key != "$ref"})
        return resolve_refs(merged, specification, stack + (reference,), depth + 1)

    return {
        key: resolve_refs(value, specification, stack, depth + 1)
        for key, value in node.items()
    }


def parameter_catalog(
    operation: dict[str, Any], specification: dict[str, Any]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for parameter in operation.get("parameters", []):
        entry = {
            "name": parameter.get("name"),
            "in": parameter.get("in"),
            "required": bool(parameter.get("required", False)),
            "description": parameter.get("description") or "",
        }
        schema = parameter.get("schema")
        if schema is not None:
            entry["schema"] = resolve_refs(schema, specification)
        else:
            entry["schema"] = {
                key: copy.deepcopy(parameter[key])
                for key in ("type", "format", "enum", "items", "default")
                if key in parameter
            }
        result.append(entry)
    return result


def request_schema(parameters: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep transport locations explicit so the adapter cannot mix inputs."""
    groups: dict[str, dict[str, Any]] = {}
    required_groups: list[str] = []
    for location in ("path", "query", "header", "body"):
        selected = [parameter for parameter in parameters if parameter["in"] == location]
        if not selected:
            continue
        if location == "body" and len(selected) == 1:
            groups[location] = selected[0]["schema"]
            if selected[0]["required"]:
                required_groups.append(location)
            continue
        properties = {parameter["name"]: parameter["schema"] for parameter in selected}
        required = [parameter["name"] for parameter in selected if parameter["required"]]
        group: dict[str, Any] = {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
        }
        if required:
            group["required"] = required
            required_groups.append(location)
        groups[location] = group

    result: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": groups,
    }
    if required_groups:
        result["required"] = required_groups
    return result


def success_schema(operation: dict[str, Any], specification: dict[str, Any]) -> Any:
    for status_code in sorted(operation.get("responses", {})):
        if str(status_code).startswith("2"):
            schema = operation["responses"][status_code].get("schema")
            return resolve_refs(schema, specification) if schema else None
    return None


# Transactional catalog import


def _base_url(specification: dict[str, Any]) -> str:
    scheme = (specification.get("schemes") or ["https"])[0]
    host = specification.get("host", "")
    base_path = specification.get("basePath", "")
    return f"{scheme}://{host}{base_path}".rstrip("/")


def import_catalog(
    session: Session,
    specification: dict[str, Any],
    source_url: str,
) -> AOTGSpecSnapshot:
    """Import a spec as disabled operations; the caller owns commit/rollback.

    Existing reviewed operations are never overwritten. A changed document gets
    a new snapshot whose operations start disabled and require explicit review.
    """
    if specification.get("swagger") != "2.0":
        raise ValueError("Expected an AOTG Swagger 2.0 document")
    if not isinstance(specification.get("paths"), dict):
        raise ValueError("Swagger document has no paths object")

    canonical = json.dumps(
        specification, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    document_sha256 = hashlib.sha256(canonical).hexdigest()

    existing = (
        session.query(AOTGSpecSnapshot)
        .filter(AOTGSpecSnapshot.document_sha256 == document_sha256)
        .one_or_none()
    )
    session.query(AOTGSpecSnapshot).filter(AOTGSpecSnapshot.active.is_(True)).update(
        {AOTGSpecSnapshot.active: False}, synchronize_session=False
    )
    if existing is not None:
        existing.active = True
        session.flush()
        return existing

    operation_count = sum(
        1
        for path_item in specification["paths"].values()
        for method in path_item
        if method.lower() in HTTP_METHODS
    )
    snapshot = AOTGSpecSnapshot(
        source_url=source_url,
        base_url=_base_url(specification),
        document_version=specification.get("info", {}).get("version"),
        swagger_version=specification["swagger"],
        document_sha256=document_sha256,
        operation_count=operation_count,
        active=True,
    )
    session.add(snapshot)
    session.flush()

    for path, path_item in specification["paths"].items():
        shared_parameters = path_item.get("parameters", [])
        for method, operation in path_item.items():
            method_lower = method.lower()
            if method_lower not in HTTP_METHODS:
                continue

            operation_with_parameters = copy.deepcopy(operation)
            operation_with_parameters["parameters"] = [
                *shared_parameters,
                *operation.get("parameters", []),
            ]
            parameters = parameter_catalog(operation_with_parameters, specification)
            tag = (operation.get("tags") or ["Unknown"])[0]
            generated_id = f"{method_lower.upper()} {path}"
            session.add(
                AOTGOperation(
                    spec_snapshot_id=snapshot.id,
                    operation_id=operation.get("operationId") or generated_id,
                    tag=tag,
                    http_method=method_lower.upper(),
                    path=path,
                    summary=operation.get("summary"),
                    description=operation.get("description"),
                    parameters_schema=parameters,
                    request_schema=request_schema(parameters),
                    success_schema=success_schema(operation, specification),
                    risk_level=classify_risk(method_lower, path, operation),
                    enabled_for_agent=False,
                    llm_may_propose=False,
                    execution_verified=False,
                    supports_idempotency=False,
                )
            )

    session.flush()
    return snapshot
