"""
Turn a validated extraction into an AutoCount DRAFT sales order.

Pipeline position (after email_order_extraction.py):

    extract_order -> postprocess flags -> match_customer -> match_items
        -> build_sales_order_draft()   (builds the payload, lists blockers; sends nothing)
        -> create_draft()              (guarded: flag, duplicate check, draft only)

Rules baked in:
- Only fields in AutoCount's Create_V1 REQUEST model are sent (Debtor, DebtorName, DocumentDate,
  DeliverAddress, Description, Ref/RefDocNo, Note, DetailsLine with Item/UOM/Qty/UnitPrice/Description/
  DeliveryDate). Response-only fields (Id, Number, totals, FurtherDescription, ...) are never sent.
- The request model has no draft flag. The agent relies on the order being created and left for the
  admin; confirm in Swagger whether Create_V1 has a query parameter or a separate operation for drafts.
- An item is "matched" only by exact code or an admin-confirmed mapping. A description match is
  at best "uncertain" (a suggestion) and blocks the draft until the admin confirms it. Confirmed
  mappings are fed back through confirmed_map, so repeat customers get faster.
- create_draft() does nothing unless enabled, never creates a second draft for the same reference,
  and never logs payload content.
"""

import difflib
import logging
import re
import textwrap
from datetime import datetime, timezone
from typing import Callable, Dict, List, Literal, Optional, Protocol, Sequence, Tuple

from pydantic import BaseModel, Field

from email_order_extraction import CustomerMatch, ExtractedOrder, Flag, OrderLine

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Item matching
# --------------------------------------------------------------------------

UOM_SYNONYMS = {
    "BOTTLE": "BTL", "BTLS": "BTL", "CTN": "CARTON", "CTNS": "CARTON", "CARTONS": "CARTON",
    "MT": "TON", "TONNE": "TON", "TONS": "TON", "TONNES": "TON", "PC": "PCS", "PIECE": "PCS",
    "PIECES": "PCS", "JARS": "JAR", "KGS": "KG", "MTR": "METER", "METRE": "METER", "METERS": "METER", "M": "METER",
}


class ItemMatch(BaseModel):
    line_index: int
    status: Literal["matched", "uncertain", "unmatched"]
    item_code: Optional[str] = None      # for "uncertain" this is only a suggestion
    uom: Optional[str] = None
    score: float = 0.0
    method: Literal["code", "confirmed", "description", "none"] = "none"
    note: Optional[str] = None
    candidates: List[Dict[str, object]] = Field(default_factory=list)


def _tokens(text: str) -> List[str]:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()


def apply_glossary(text: str, glossary: Optional[Dict[str, str]]) -> str:
    """Expand shortforms token by token (glossary keys lowercase), e.g. {"brc": "brc mesh"}."""
    if not glossary:
        return text or ""
    return " ".join(glossary.get(t, t) for t in _tokens(text))


def item_key(line: OrderLine) -> str:
    """Key used to remember an admin-confirmed mapping for a customer."""
    code = (line.item_code_raw or "").strip().upper()
    return f"code:{code}" if code else "desc:" + " ".join(_tokens(line.description_raw))


def _description_score(query: str, candidate: str, glossary: Optional[Dict[str, str]]) -> float:
    q, c = _tokens(apply_glossary(query, glossary)), _tokens(apply_glossary(candidate, glossary))
    if not q or not c:
        return 0.0
    cs = set(c)
    credit = 0.0
    for t in q:
        if t in cs:
            credit += 1
        elif not any(ch.isdigit() for ch in t) and difflib.get_close_matches(t, cs, n=1, cutoff=0.8):
            credit += 0.8  # typo tolerance for words, never for sizes/numbers
    ratio = difflib.SequenceMatcher(None, " ".join(q), " ".join(c)).ratio()
    score = 0.7 * (credit / len(q)) + 0.3 * ratio
    numbers = {t for t in q if any(ch.isdigit() for ch in t)}
    if numbers and not numbers <= cs:
        score *= 0.6  # a size or code that the candidate lacks (size 05 vs 06)
    return score


def resolve_uom(unit_raw: Optional[str], uoms: Sequence[str]) -> Tuple[Optional[str], Optional[str]]:
    """Returns (uom, note). note is set when the unit was assumed or could not be resolved."""
    options = {u.upper(): u for u in uoms}
    if unit_raw and unit_raw.strip():
        u = unit_raw.strip().upper()
        u = UOM_SYNONYMS.get(u, u)
        if u in options:
            return options[u], None
    shown = unit_raw.strip() if unit_raw and unit_raw.strip() else "not stated"
    if len(options) == 1:
        only = next(iter(options.values()))
        return only, f"unit '{shown}' not recognised; using the item's only unit '{only}'"
    return None, f"unit '{shown}' not found among {sorted(options.values())}"


def match_items(
    order: ExtractedOrder,
    stock_items: Sequence[dict],
    debtor_code: Optional[str] = None,
    confirmed_map: Optional[Dict[Tuple[Optional[str], str], str]] = None,
    glossary: Optional[Dict[str, str]] = None,
) -> List[ItemMatch]:
    """
    stock_items: dicts with item_code, description, uoms (list[str]). Build from your AutoCount stock API.
    confirmed_map: {(debtor_code, item_key(line)): item_code} saved from admin confirmations.
    """
    by_code = {s["item_code"].strip().upper(): s for s in stock_items}
    results: List[ItemMatch] = []

    for idx, line in enumerate(order.lines):
        code = (line.item_code_raw or "").strip().upper()
        stock, method, score, note = None, "none", 0.0, None
        candidates: List[Dict[str, object]] = []

        confirmed = (confirmed_map or {}).get((debtor_code, item_key(line)))
        if confirmed and confirmed.strip().upper() in by_code:
            stock, method, score = by_code[confirmed.strip().upper()], "confirmed", 1.0
        elif code and code in by_code:
            stock, method, score = by_code[code], "code", 1.0

        if stock:
            status = "matched"
        else:
            ranked = sorted(
                ((_description_score(line.description_raw, s["description"], glossary), s) for s in stock_items),
                key=lambda x: x[0], reverse=True)
            candidates = [{"item_code": s["item_code"], "description": s["description"], "score": round(sc, 3)}
                          for sc, s in ranked[:3]]
            if code:
                note = f"code '{line.item_code_raw}' is not in the stock list"
            if ranked and ranked[0][0] >= 0.6:
                status, stock, score, method = "uncertain", ranked[0][1], ranked[0][0], "description"
            else:
                status = "unmatched"

        uom = None
        if stock:
            uom, uom_note = resolve_uom(line.unit_raw, stock.get("uoms", []))
            note = "; ".join(n for n in (note, uom_note) if n) or None

        results.append(ItemMatch(
            line_index=idx, status=status, item_code=stock["item_code"] if stock else None, uom=uom,
            score=round(score, 3), method=method, note=note, candidates=candidates))
    return results


# --------------------------------------------------------------------------
# Payload
# --------------------------------------------------------------------------

class DraftConfig(BaseModel):
    po_number_field: Literal["Ref", "RefDocNo"] = "Ref"  # which AutoCount field holds the customer's PO no.
    source_tag: str = "AI draft from email"
    max_note_chars: int = 1000
    address_line_max: int = 40                           # check AutoCount's real limit
    price_tolerance: float = 0.005
    row_state: Optional[int] = None                      # set only if the API needs RowState on new lines
    base_currencies: Tuple[str, ...] = ("RM", "MYR")     # anything else is flagged


class DraftBuild(BaseModel):
    payload: dict
    flags: List[Flag] = Field(default_factory=list)
    ready: bool = False  # True = no block flags; the admin still reviews the draft


def split_address(raw: Optional[str], max_lines: int = 4, max_len: int = 40) -> Tuple[List[str], bool]:
    """Pack a free-text address into Address1..4. Returns (lines, truncated)."""
    parts = [p.strip() for p in re.split(r"[,\n]+", raw or "") if p.strip()]
    if parts and parts[-1].lower() == "malaysia":
        parts.pop()
    lines: List[str] = []
    cur = ""
    for part in parts:
        for piece in (textwrap.wrap(part, max_len) or [part]):
            if not cur:
                cur = piece
            elif len(cur) + 2 + len(piece) <= max_len:
                cur += ", " + piece
            else:
                lines.append(cur)
                cur = piece
    if cur:
        lines.append(cur)
    return lines[:max_lines], len(lines) > max_lines


def _iso_datetime(d: str) -> str:
    return f"{d}T00:00:00.000Z"  # 00:00Z is 08:00 in Malaysia: same calendar day


def build_sales_order_draft(
    order: ExtractedOrder,
    match: CustomerMatch,
    item_matches: Sequence[ItemMatch],
    *,
    upstream_flags: Sequence[Flag] = (),
    source_ref: str = "",
    config: Optional[DraftConfig] = None,
    price_lookup: Optional[Callable[[str, str, str], Optional[float]]] = None,
    now: Optional[datetime] = None,
) -> DraftBuild:
    """
    price_lookup(item_code, uom, debtor_code) -> master price or None (optional).
    source_ref: short id for the email (e.g. 'EML-' + first 8 chars of a hash of the message id).
                Used as the reference when the customer gave no PO number, so duplicates are detectable.
    """
    cfg = config or DraftConfig()
    now = now or datetime.now(timezone.utc)
    flags: List[Flag] = []

    def add(code: str, severity: str, message: str) -> None:
        flags.append(Flag(code=code, severity=severity, message=message))

    if any(f.severity == "block" for f in upstream_flags):
        add("upstream_block", "block", "An earlier check blocked this order: admin must handle it manually")
    if match.status != "matched":
        add("customer_not_confirmed", "block", "Customer not confirmed in AutoCount")
    if not order.lines:
        add("no_lines", "block", "No order lines")

    by_index = {m.line_index: m for m in item_matches}
    lines_payload: List[dict] = []
    line_notes: List[str] = []
    for idx, line in enumerate(order.lines):
        label = f"Line {line.line_no or idx + 1}"
        im = by_index.get(idx)
        entry: dict = {"Description": line.description_raw}

        if im is None or im.status != "matched":
            hint = ""
            if im and im.candidates:
                top = im.candidates[0]
                hint = f" (best guess: {top['item_code']} {top['description']})"
            add("item_not_confirmed", "block", f"{label}: item not confirmed{hint}")
        else:
            entry["Item"] = im.item_code
            if im.uom is None:
                add("uom_unresolved", "block", f"{label}: {im.note}")
            else:
                entry["UOM"] = im.uom
                if im.note:
                    add("uom_assumed", "warn", f"{label}: {im.note}")

        if line.quantity is None or line.quantity <= 0:
            add("quantity_invalid", "block", f"{label}: quantity missing or not positive")
        else:
            entry["Qty"] = line.quantity

        master = None
        if price_lookup and entry.get("Item") and entry.get("UOM"):
            try:
                master = price_lookup(entry["Item"], entry["UOM"], match.debtor_code or "")
            except Exception:
                logger.warning("Price lookup failed")
        if line.unit_price is not None:
            entry["UnitPrice"] = line.unit_price
            if master is not None and abs(master - line.unit_price) > cfg.price_tolerance * max(master, 1):
                add("price_differs_from_master", "warn",
                    f"{label}: PO price {line.unit_price:g} differs from AutoCount price {master:g}")
        elif master is not None:
            entry["UnitPrice"] = master
        else:
            add("price_not_set", "warn", f"{label}: no price on the order and none found in AutoCount")

        delivery = line.delivery_date_iso or order.delivery_date_iso
        if delivery:
            entry["DeliveryDate"] = _iso_datetime(delivery)
        else:
            add("no_delivery_date", "warn", f"{label}: no delivery date")
        if line.notes:  # FurtherDescription is response-only, so line notes go in the document Note
            line_notes.append(f"Line {line.line_no or idx + 1}: {line.notes}")
        if cfg.row_state is not None:
            entry["RowState"] = cfg.row_state
        lines_payload.append(entry)

    reference = order.po_number or source_ref
    note_parts = [cfg.source_tag + (f" ({source_ref})" if source_ref else "")]
    if order.payment_terms:
        note_parts.append(f"PO payment terms: {order.payment_terms}")
    if order.reference_numbers:
        note_parts.append("Customer references: " + ", ".join(order.reference_numbers))
    note_parts += [f"Customer requirement: {s}" for s in order.special_instructions]
    note_parts += line_notes

    currency = (order.totals.currency or "").strip().upper()
    if currency and currency not in cfg.base_currencies:
        add("currency_differs", "warn", f"Order is in {currency}: the draft uses AutoCount's default currency")

    payload: dict = {
        "Debtor": match.debtor_code,
        "DebtorName": match.company_name,  # the master record's own name
        "DocumentDate": now.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "Description": f"{cfg.source_tag}: {reference}" if reference else cfg.source_tag,
        "DetailsLine": lines_payload,
    }
    if reference:
        payload[cfg.po_number_field] = reference

    if order.delivery_address_raw:
        addr_lines, truncated = split_address(order.delivery_address_raw, 4, cfg.address_line_max)
        payload["DeliverAddress"] = {f"Address{i + 1}": text for i, text in enumerate(addr_lines)}
        if truncated:
            add("address_truncated", "warn", "Delivery address did not fit in 4 lines; full text is in the Note")
            note_parts.append("Full delivery address: " + order.delivery_address_raw)
    else:
        add("no_delivery_address", "warn", "No delivery address on the order")

    note = "\n".join(note_parts)
    if len(note) > cfg.max_note_chars:
        add("note_truncated", "warn", "Note was shortened: check the customer requirements in the original")
        note = note[:cfg.max_note_chars]
    payload["Note"] = note

    return DraftBuild(payload=payload, flags=flags, ready=not any(f.severity == "block" for f in flags))


# --------------------------------------------------------------------------
# Check what AutoCount calculated against the PO
# --------------------------------------------------------------------------

def verify_created_totals(created: dict, order: ExtractedOrder, tolerance: float = 0.06) -> List[Flag]:
    """
    AutoCount computes tax and totals itself. Compare them with the PO. Tolerance allows
    the 5-sen rounding adjustment. Skips quietly when the PO shows no totals (text orders).
    """
    po_values = [v for v in (order.totals.total, order.totals.subtotal) if v is not None]
    if not po_values:
        return []
    total, net, tax = created.get("Total"), created.get("NetTotal"), created.get("TaxAmount")
    candidates = [v for v in (total, net) if isinstance(v, (int, float))]
    if isinstance(total, (int, float)) and isinstance(tax, (int, float)):
        candidates.append(total + tax)
    if not candidates:
        return [Flag(code="created_totals_unavailable", severity="info",
                     message="AutoCount's response had no totals to compare with the PO")]
    if any(abs(c - p) <= tolerance for c in candidates for p in po_values):
        return []
    return [Flag(code="created_totals_differ", severity="warn",
                 message=(f"AutoCount totals {sorted(set(round(c, 2) for c in candidates))} do not match the PO "
                          f"{sorted(set(po_values))}: check tax codes, prices and quantities"))]


# --------------------------------------------------------------------------
# Guarded creation
# --------------------------------------------------------------------------

class SalesOrderClient(Protocol):
    """Implement with your existing AutoCount REST client."""

    def find_sales_orders(self, debtor: str, ref: str) -> List[dict]: ...

    def create_sales_order(self, payload: dict) -> dict: ...


class DraftResult(BaseModel):
    status: Literal["created", "disabled", "not_ready", "duplicate_found", "error"]
    document_id: Optional[str] = None
    document_number: Optional[str] = None
    detail: str = ""
    flags: List[Flag] = Field(default_factory=list)


def create_draft(
    build: DraftBuild,
    client: SalesOrderClient,
    *,
    enabled: bool,
    po_number_field: str = "Ref",
    order: Optional[ExtractedOrder] = None,
) -> DraftResult:
    """
    Create the draft only when enabled, ready and not already there. Never raises.
    Pass the extracted order to compare AutoCount's returned totals with the PO's.
    """
    if not build.ready:
        return DraftResult(status="not_ready", detail="blocked: admin must complete the order")
    if not enabled:
        return DraftResult(status="disabled", detail="draft writes are switched off (shadow mode)")

    debtor = build.payload.get("Debtor", "")
    ref = build.payload.get(po_number_field, "")
    try:
        if ref:
            existing = client.find_sales_orders(debtor, ref)
            if existing:
                first = existing[0]
                return DraftResult(status="duplicate_found", document_id=first.get("Id"),
                                   document_number=first.get("Number"),
                                   detail="a sales order with this reference already exists for the customer")
        created = client.create_sales_order(build.payload)
        return DraftResult(status="created", document_id=created.get("Id"), document_number=created.get("Number"),
                           flags=verify_created_totals(created, order) if order else [])
    except Exception as exc:
        logger.error(f"Draft creation failed: {type(exc).__name__}")  # never log the payload
        return DraftResult(status="error", detail=f"{type(exc).__name__}")
