"""Local Tool Dispatcher & Schema-Governed Tool Contracts (ADR-0042, ADR-0043).

Strictly PII-protected, deterministic, zero-token parameter validation and clarification engine.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field, TypeAdapter
import re
import json
import structlog

from app.adapters.base import PiiSanitizedSlotMap
from app.contexts.compliance.services import sanitize_nigerian_pii_detailed
from app.contexts.knowledge.offering_schemas import compute_offering_id

_SLOT_MAP_VALIDATOR = TypeAdapter(PiiSanitizedSlotMap)

logger = structlog.get_logger(__name__)


def mask_phone_for_logs(phone: str) -> str:
    """Masks phone number for NDPA 2023 compliance in structured logs."""
    if not phone or len(phone) < 7:
        return "[REDACTED_PHONE]"
    return f"{phone[:4]}****{phone[-3:]}"


class ToolStatus(str, Enum):
    """Execution status of a local tool evaluation."""
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    CONVERGED = "CONVERGED"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    REJECTED = "REJECTED"


class ToolClarificationPrompt(BaseModel):
    """Structured clarification payload for Meta WhatsApp Egress."""
    prompt_text: str
    buttons: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="List of button dicts: [{'id': 'SET_SLOT:sku:DANGOTE_50KG', 'title': 'Dangote 50kg (₦84k)'}]"
    )
    missing_param: str
    candidate_options: Optional[List[Dict[str, Any]]] = None


class ToolEvaluationResult(BaseModel):
    """Result of evaluating slots against a LocalToolContract."""
    status: ToolStatus
    tool_name: str
    clarification: Optional[ToolClarificationPrompt] = None
    bound_slots: Dict[str, Any] = Field(default_factory=dict)
    missing_slots: List[str] = Field(default_factory=list)
    calculated_total_kobo: Optional[int] = None
    breakdown: Optional[Dict[str, Any]] = None
    action: Optional[str] = None


class LocalToolContract(BaseModel):
    """Typed parameter schema and validation invariants for a local tool."""
    tool_name: str
    intent: str
    required_params: List[str]
    optional_params: List[str] = Field(default_factory=list)


class LocalTool(ABC):
    """Abstract base class for in-process local tools."""

    def __init__(self, contract: LocalToolContract):
        self.contract = contract

    @abstractmethod
    async def evaluate(
        self,
        slots: Dict[str, Any],
        catalog_manifest: Optional[str] = None,
        stock_checker: Optional[Any] = None,
        **kwargs: Any,
    ) -> ToolEvaluationResult:
        """Evaluates slot parameters, detects gaps/ambiguities, and validates convergence."""
        pass


# -----------------------------------------------------------------------------
# DEFAULT IN-MEMORY CATALOG FOR TEST/DEMO ENVIRONMENTS
# -----------------------------------------------------------------------------
DEFAULT_COMMODITY_CATALOG = [
    {
        "sku": "SUGAR_DANGOTE_50KG",
        "name": "Dangote Sugar 50kg",
        "category": "sugar",
        "unit": "bag",
        "weight": "50kg",
        "price_naira": 84000,
        "price_kobo": 8400000,
        "in_stock": True,
        "stock_quantity": 45,
    },
    {
        "sku": "SUGAR_BUA_50KG",
        "name": "BUA Sugar 50kg",
        "category": "sugar",
        "unit": "bag",
        "weight": "50kg",
        "price_naira": 82000,
        "price_kobo": 8200000,
        "in_stock": True,
        "stock_quantity": 30,
    },
    {
        "sku": "SUGAR_ST_LOUIS_500G",
        "name": "St. Louis Sugar Cube (500g Pack)",
        "category": "sugar",
        "unit": "pack",
        "weight": "500g",
        "price_naira": 1800,
        "price_kobo": 180000,
        "in_stock": True,
        "stock_quantity": 120,
    },
    {
        "sku": "RICE_MAMA_GOLD_50KG",
        "name": "Mama Gold Rice 50kg",
        "category": "rice",
        "unit": "bag",
        "weight": "50kg",
        "price_naira": 78000,
        "price_kobo": 7800000,
        "in_stock": True,
        "stock_quantity": 25,
    },
    {
        "sku": "RICE_MAMA_GOLD_25KG",
        "name": "Mama Gold Rice 25kg",
        "category": "rice",
        "unit": "bag",
        "weight": "25kg",
        "price_naira": 41000,
        "price_kobo": 4100000,
        "in_stock": True,
        "stock_quantity": 40,
    },
    {
        "sku": "RICE_ROYAL_STALLION_50KG",
        "name": "Royal Stallion Rice 50kg",
        "category": "rice",
        "unit": "bag",
        "weight": "50kg",
        "price_naira": 80000,
        "price_kobo": 8000000,
        "in_stock": True,
        "stock_quantity": 15,
    },
    {
        "sku": "OIL_DEVONS_KING_25L",
        "name": "Devon's King Vegetable Oil 25L",
        "category": "oil",
        "unit": "jerrycan",
        "weight": "25L",
        "price_naira": 58000,
        "price_kobo": 5800000,
        "in_stock": True,
        "stock_quantity": 20,
    },
    {
        "sku": "FLOUR_GOLDEN_PENNY_50KG",
        "name": "Golden Penny Flour 50kg",
        "category": "flour",
        "unit": "bag",
        "weight": "50kg",
        "price_naira": 62000,
        "price_kobo": 6200000,
        "in_stock": False,
        "stock_quantity": 0,
    },
]

ZONE_DELIVERY_FEES_KOBO = {
    "ikeja": 250000,       # ₦2,500
    "mainland": 250000,    # ₦2,500
    "surulere": 250000,    # ₦2,500
    "yaba": 250000,        # ₦2,500
    "lekki": 450000,       # ₦4,500
    "island": 450000,      # ₦4,500
    "vi": 450000,          # ₦4,500
    "ikoyi": 450000,       # ₦4,500
    "abuja": 500000,       # ₦5,000
    "ibadan": 400000,      # ₦4,000
}


def parse_catalog_manifest(manifest_str: Optional[str]) -> List[Dict[str, Any]]:
    """Safely parses structured catalog manifest, falling back to default manifest."""
    if not manifest_str:
        return [dict(item) for item in DEFAULT_COMMODITY_CATALOG]
    try:
        data = json.loads(manifest_str)
        if isinstance(data, list):
            return [dict(item) for item in data]
        if isinstance(data, dict) and "products" in data:
            return [dict(item) for item in data["products"]]
    except Exception:
        pass
    return [dict(item) for item in DEFAULT_COMMODITY_CATALOG]


class CheckoutOrderTool(LocalTool):
    """
    Unified Commercial Order Checkout Tool (ADR-0043).
    Enforces Parameter Convergence before generating virtual NUBAN holds.
    All incoming slot values are sanitized for NDPA 2023 PII protection.
    """

    def __init__(self):
        super().__init__(
            contract=LocalToolContract(
                tool_name="CheckoutOrderTool",
                intent="INSTANT_CHECKOUT_ORDER",
                required_params=["sku", "quantity", "fulfillment_type"],
                optional_params=["delivery_zone", "customer_notes"],
            )
        )

    async def evaluate(
        self,
        slots: Dict[str, Any],
        catalog_manifest: Optional[str] = None,
        stock_checker: Optional[Any] = None,
        **kwargs: Any,
    ) -> ToolEvaluationResult:
        # 1. Declarative PII Sanitization across all slot inputs via PiiSanitizedSlotMap
        sanitized_slots = _SLOT_MAP_VALIDATOR.validate_python(slots)

        catalog = parse_catalog_manifest(catalog_manifest)
        merchant_id = kwargs.get("merchant_id") or sanitized_slots.get("merchant_id")
        for c_item in catalog:
            if "offering_id" not in c_item and "sku" in c_item:
                c_item["offering_id"] = compute_offering_id(merchant_id, c_item["sku"])

        bound: Dict[str, Any] = dict(sanitized_slots)
        missing: List[str] = []

        # ---------------------------------------------------------------------
        # MULTI-ITEM BULK CART BRANCH (line_items > 1)
        # ---------------------------------------------------------------------
        raw_line_items = bound.get("line_items")
        if isinstance(raw_line_items, list):
            deduped_items: List[Dict[str, Any]] = []
            seen_keys = set()
            for it in raw_line_items:
                if not isinstance(it, dict):
                    continue
                key = ((it.get("sku") or "").upper(), (it.get("product") or "").lower())
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                deduped_items.append(it)
            if len(deduped_items) > 1:
                bound["line_items"] = deduped_items
                return await self._evaluate_multi_item_cart(
                    bound=bound,
                    line_items=deduped_items,
                    catalog=catalog,
                    merchant_id=merchant_id,
                    stock_checker=stock_checker,
                )
            else:
                bound.pop("line_items", None)

        # ---------------------------------------------------------------------
        # STEP 1: Resolve Offering ID / SKU & Disambiguate Products
        # ---------------------------------------------------------------------
        raw_sku = bound.get("sku") or bound.get("offering_id")
        product_query = (bound.get("product") or "").lower().strip()
        matched_sku_item: Optional[Dict[str, Any]] = None

        if raw_sku:
            # Check if attributes are already bound
            if bound.get("product_name") and bound.get("unit_price_kobo") and bound.get("sku"):
                matched_sku_item = {
                    "offering_id": bound.get("offering_id") or compute_offering_id(merchant_id, str(bound["sku"])),
                    "sku": str(bound["sku"]),
                    "name": bound["product_name"],
                    "price_kobo": bound["unit_price_kobo"],
                    "in_stock": bound.get("in_stock", True),
                }
                bound["offering_id"] = matched_sku_item["offering_id"]
            else:
                # Explicit SKU or offering_id provided (e.g. from button ID SET_SLOT:sku:...)
                raw_sku_str = str(raw_sku).strip()
                matched = [
                    item for item in catalog
                    if item["sku"].upper() == raw_sku_str.upper()
                    or str(item.get("offering_id", "")).lower() == raw_sku_str.lower()
                    or compute_offering_id(None, item["sku"]).lower() == raw_sku_str.lower()
                ]
                if matched:
                    matched_sku_item = matched[0]
                    bound["sku"] = matched_sku_item["sku"]
                    bound["offering_id"] = (
                        bound.get("offering_id")
                        or matched_sku_item.get("offering_id")
                        or compute_offering_id(merchant_id, matched_sku_item["sku"])
                    )
                    bound["product_name"] = matched_sku_item["name"]
                    bound["unit_price_kobo"] = matched_sku_item["price_kobo"]
                    bound["in_stock"] = matched_sku_item.get("in_stock", True)

        if not matched_sku_item and product_query:
            # Fuzzy match against catalog
            candidates = [
                item for item in catalog
                if product_query in item["category"].lower()
                or product_query in item["name"].lower()
                or any(term in item["name"].lower() for term in product_query.split())
            ]

            if len(candidates) == 1:
                matched_sku_item = candidates[0]
                bound["sku"] = matched_sku_item["sku"]
                bound["offering_id"] = matched_sku_item.get("offering_id") or compute_offering_id(merchant_id, matched_sku_item["sku"])
                bound["product_name"] = matched_sku_item["name"]
                bound["unit_price_kobo"] = matched_sku_item["price_kobo"]
            elif len(candidates) > 1:
                # AMBIGUITY DETECTED: Emit deterministic WhatsApp buttons (max 3)
                buttons = []
                for c in candidates[:3]:
                    price_fmt = f"₦{c['price_naira']:,}" if "price_naira" in c else f"₦{c['price_kobo']//100:,}"
                    title = f"{c['name']} ({price_fmt})"
                    if len(title) > 20:
                        # WhatsApp button titles have a 20-character limit
                        title = f"{c['name'].split()[0]} {c.get('weight', '')} ({price_fmt})"[:20]
                    buttons.append({
                        "id": f"SET_SLOT:sku:{c['sku']}",
                        "title": title,
                    })

                candidate_names = " or ".join([f"*{c['name']}* (₦{c.get('price_naira', c['price_kobo']//100):,})" for c in candidates[:3]])
                prompt_text = (
                    f"We have multiple options for *{product_query}* in stock:\n"
                    f"{candidate_names}.\n\n"
                    f"Which brand or size would you like to order?"
                )

                return ToolEvaluationResult(
                    status=ToolStatus.NEEDS_CLARIFICATION,
                    tool_name=self.contract.tool_name,
                    clarification=ToolClarificationPrompt(
                        prompt_text=prompt_text,
                        buttons=buttons,
                        missing_param="sku",
                        candidate_options=candidates,
                    ),
                    bound_slots=bound,
                    missing_slots=["sku"],
                )
            else:
                # No match found in catalog
                return ToolEvaluationResult(
                    status=ToolStatus.REJECTED,
                    tool_name=self.contract.tool_name,
                    clarification=ToolClarificationPrompt(
                        prompt_text=f"Sorry, we couldn't find *{product_query}* in our verified wholesale catalog today. Would you like to check our available price list?",
                        buttons=[{"id": "INTENT:SHOW_CATALOG", "title": "View Catalog"}],
                        missing_param="sku",
                    ),
                    bound_slots=bound,
                    missing_slots=["sku"],
                )

        if not matched_sku_item:
            missing.append("sku")
            return ToolEvaluationResult(
                status=ToolStatus.NEEDS_CLARIFICATION,
                tool_name=self.contract.tool_name,
                clarification=ToolClarificationPrompt(
                    prompt_text="Which product would you like to purchase today?",
                    missing_param="sku",
                ),
                bound_slots=bound,
                missing_slots=missing,
            )

        # ---------------------------------------------------------------------
        # STEP 2: Resolve Quantity
        # ---------------------------------------------------------------------
        qty = bound.get("quantity")
        parsed_qty: Optional[int] = None
        if qty is not None:
            if isinstance(qty, (int, float)):
                parsed_qty = int(qty)
            elif isinstance(qty, str):
                match = re.search(r"\b(\d+)\b", qty)
                if match:
                    parsed_qty = int(match.group(1))

        if not parsed_qty or parsed_qty <= 0:
            missing.append("quantity")
            return ToolEvaluationResult(
                status=ToolStatus.NEEDS_CLARIFICATION,
                tool_name=self.contract.tool_name,
                clarification=ToolClarificationPrompt(
                    prompt_text=f"How many units or bags of *{bound['product_name']}* do you want us to reserve?",
                    buttons=[
                        {"id": "SET_SLOT:quantity:1", "title": "1 bag"},
                        {"id": "SET_SLOT:quantity:2", "title": "2 bags"},
                        {"id": "SET_SLOT:quantity:5", "title": "5 bags"},
                    ],
                    missing_param="quantity",
                ),
                bound_slots=bound,
                missing_slots=missing,
            )

        bound["quantity"] = parsed_qty

        # ---------------------------------------------------------------------
        # STEP 3: Resolve Fulfillment Type (Delivery vs Pickup)
        # ---------------------------------------------------------------------
        fulfillment = bound.get("fulfillment_type")
        if fulfillment:
            f_upper = str(fulfillment).upper()
            if "PICKUP" in f_upper or "COLLECT" in f_upper or "WAREHOUSE" in f_upper:
                bound["fulfillment_type"] = "WAREHOUSE_PICKUP"
            else:
                bound["fulfillment_type"] = "EXPRESS_DELIVERY"
        else:
            # Check if location was already extracted
            if bound.get("location") or bound.get("delivery_zone"):
                bound["fulfillment_type"] = "EXPRESS_DELIVERY"
            else:
                missing.append("fulfillment_type")
                return ToolEvaluationResult(
                    status=ToolStatus.NEEDS_CLARIFICATION,
                    tool_name=self.contract.tool_name,
                    clarification=ToolClarificationPrompt(
                        prompt_text=f"For your order of *{parsed_qty}x {bound['product_name']}*, how would you like to receive it?",
                        buttons=[
                            {"id": "SET_SLOT:fulfillment_type:EXPRESS_DELIVERY", "title": "Express Delivery"},
                            {"id": "SET_SLOT:fulfillment_type:WAREHOUSE_PICKUP", "title": "Warehouse Pickup"},
                        ],
                        missing_param="fulfillment_type",
                    ),
                    bound_slots=bound,
                    missing_slots=missing,
                )

        # ---------------------------------------------------------------------
        # STEP 4: Full Parameter Invariant - Delivery Zone for Express Delivery
        # ---------------------------------------------------------------------
        delivery_fee_kobo = 0
        if bound["fulfillment_type"] == "EXPRESS_DELIVERY":
            raw_zone = (bound.get("delivery_zone") or bound.get("location") or "").lower().strip()
            resolved_zone: Optional[str] = None

            for zone_key, fee in ZONE_DELIVERY_FEES_KOBO.items():
                if zone_key in raw_zone:
                    resolved_zone = zone_key
                    delivery_fee_kobo = fee
                    break

            if not resolved_zone:
                missing.append("delivery_zone")
                return ToolEvaluationResult(
                    status=ToolStatus.NEEDS_CLARIFICATION,
                    tool_name=self.contract.tool_name,
                    clarification=ToolClarificationPrompt(
                        prompt_text=(
                            f"Almost done! To calculate your exact total and delivery fee for "
                            f"*{parsed_qty}x {bound['product_name']}*, where should we deliver to?"
                        ),
                        buttons=[
                            {"id": "SET_SLOT:delivery_zone:Ikeja", "title": "Ikeja / Mainland"},
                            {"id": "SET_SLOT:delivery_zone:Lekki", "title": "Lekki / Island"},
                            {"id": "SET_SLOT:delivery_zone:Abuja", "title": "Abuja FCT"},
                        ],
                        missing_param="delivery_zone",
                    ),
                    bound_slots=bound,
                    missing_slots=missing,
                )

            bound["delivery_zone"] = resolved_zone.capitalize()
            bound["delivery_fee_kobo"] = delivery_fee_kobo

        # ---------------------------------------------------------------------
        # STEP 5: Atomic Check-and-Hold (Inventory Verification)
        # ---------------------------------------------------------------------
        if stock_checker and callable(stock_checker):
            has_stock = await stock_checker(bound["sku"], parsed_qty)
            if not has_stock:
                return ToolEvaluationResult(
                    status=ToolStatus.OUT_OF_STOCK,
                    tool_name=self.contract.tool_name,
                    clarification=ToolClarificationPrompt(
                        prompt_text=f"Ouch! We just ran out of stock for *{bound['product_name']}* moments ago. Would you like to view alternative in-stock options?",
                        buttons=[{"id": "INTENT:SHOW_CATALOG", "title": "See Alternatives"}],
                        missing_param="sku",
                    ),
                    bound_slots=bound,
                    missing_slots=["sku"],
                )
        elif matched_sku_item and matched_sku_item.get("in_stock") is False:
            return ToolEvaluationResult(
                status=ToolStatus.OUT_OF_STOCK,
                tool_name=self.contract.tool_name,
                clarification=ToolClarificationPrompt(
                    prompt_text=f"Apologies, *{bound['product_name']}* is currently out of stock. Check back with us soon!",
                    buttons=[{"id": "INTENT:SHOW_CATALOG", "title": "See Alternatives"}],
                    missing_param="sku",
                ),
                bound_slots=bound,
                missing_slots=["sku"],
            )

        # ---------------------------------------------------------------------
        # STEP 6: Parameter Convergence & Immutable Kobo Total Calculation
        # ---------------------------------------------------------------------
        unit_price_kobo = bound["unit_price_kobo"]
        subtotal_kobo = unit_price_kobo * parsed_qty
        total_payable_kobo = subtotal_kobo + delivery_fee_kobo

        breakdown = {
            "offering_id": bound.get("offering_id"),
            "sku": bound["sku"],
            "product_name": bound["product_name"],
            "quantity": parsed_qty,
            "unit_price_kobo": unit_price_kobo,
            "subtotal_kobo": subtotal_kobo,
            "fulfillment_type": bound["fulfillment_type"],
            "delivery_zone": bound.get("delivery_zone", "Self-Pickup"),
            "delivery_fee_kobo": delivery_fee_kobo,
            "total_payable_kobo": total_payable_kobo,
        }

        return ToolEvaluationResult(
            status=ToolStatus.CONVERGED,
            tool_name=self.contract.tool_name,
            bound_slots=bound,
            missing_slots=[],
            calculated_total_kobo=total_payable_kobo,
            breakdown=breakdown,
            action="GENERATE_VIRTUAL_NUBAN_HOLD",
        )

    async def _evaluate_multi_item_cart(
        self,
        bound: Dict[str, Any],
        line_items: List[Dict[str, Any]],
        catalog: List[Dict[str, Any]],
        merchant_id: Optional[str],
        stock_checker: Optional[Any],
    ) -> ToolEvaluationResult:
        """Resolves multi-item cart (`line_items`), disambiguates any ambiguous SKU, and sums Kobo subtotals."""
        resolved_items: List[Dict[str, Any]] = []

        for idx, raw_item in enumerate(line_items):
            item = dict(raw_item)
            raw_sku = item.get("sku") or item.get("offering_id")
            prod_query = (item.get("product") or "").lower().strip()
            matched_cat: Optional[Dict[str, Any]] = None

            if raw_sku:
                raw_sku_str = str(raw_sku).strip()
                matches = [
                    c for c in catalog
                    if c["sku"].upper() == raw_sku_str.upper()
                    or str(c.get("offering_id", "")).lower() == raw_sku_str.lower()
                    or compute_offering_id(None, c["sku"]).lower() == raw_sku_str.lower()
                ]
                if matches:
                    matched_cat = matches[0]

            if not matched_cat and prod_query:
                candidates = [
                    c for c in catalog
                    if prod_query in c["category"].lower()
                    or prod_query in c["name"].lower()
                    or any(term in c["name"].lower() for term in prod_query.split())
                ]
                if len(candidates) == 1:
                    matched_cat = candidates[0]
                elif len(candidates) > 1:
                    buttons = []
                    for c in candidates[:3]:
                        price_fmt = f"₦{c['price_naira']:,}" if "price_naira" in c else f"₦{c['price_kobo']//100:,}"
                        title = f"{c['name']} ({price_fmt})"
                        if len(title) > 20:
                            title = f"{c['name'].split()[0]} {c.get('weight', '')} ({price_fmt})"[:20]
                        buttons.append({
                            "id": f"SET_SLOT:line_item_sku:{idx}:{c['sku']}",
                            "title": title,
                        })
                    candidate_names = " or ".join(
                        [f"*{c['name']}* (₦{c.get('price_naira', c['price_kobo']//100):,})" for c in candidates[:3]]
                    )
                    prompt_text = (
                        f"For item #{idx + 1} (*{prod_query}*), we have multiple options in stock:\n"
                        f"{candidate_names}.\n\n"
                        f"Which brand or size would you like to include in your cart?"
                    )
                    bound["line_items"] = line_items
                    return ToolEvaluationResult(
                        status=ToolStatus.NEEDS_CLARIFICATION,
                        tool_name=self.contract.tool_name,
                        clarification=ToolClarificationPrompt(
                            prompt_text=prompt_text,
                            buttons=buttons,
                            missing_param=f"line_item_sku:{idx}",
                            candidate_options=candidates,
                        ),
                        bound_slots=bound,
                        missing_slots=[f"line_item_sku:{idx}"],
                    )
                else:
                    return ToolEvaluationResult(
                        status=ToolStatus.REJECTED,
                        tool_name=self.contract.tool_name,
                        clarification=ToolClarificationPrompt(
                            prompt_text=f"Sorry, we couldn't find *{prod_query}* in our verified wholesale catalog today.",
                            buttons=[{"id": "INTENT:SHOW_CATALOG", "title": "View Catalog"}],
                            missing_param=f"line_item_sku:{idx}",
                        ),
                        bound_slots=bound,
                        missing_slots=[f"line_item_sku:{idx}"],
                    )

            if not matched_cat:
                return ToolEvaluationResult(
                    status=ToolStatus.NEEDS_CLARIFICATION,
                    tool_name=self.contract.tool_name,
                    clarification=ToolClarificationPrompt(
                        prompt_text=f"Which specific product would you like for item #{idx + 1}?",
                        missing_param=f"line_item_sku:{idx}",
                    ),
                    bound_slots=bound,
                    missing_slots=[f"line_item_sku:{idx}"],
                )

            qty_val = int(item.get("quantity") or 1)
            if stock_checker and callable(stock_checker):
                has_stock = await stock_checker(matched_cat["sku"], qty_val)
                if not has_stock:
                    return ToolEvaluationResult(
                        status=ToolStatus.OUT_OF_STOCK,
                        tool_name=self.contract.tool_name,
                        clarification=ToolClarificationPrompt(
                            prompt_text=f"Ouch! *{matched_cat['name']}* is currently out of stock.",
                            buttons=[{"id": "INTENT:SHOW_CATALOG", "title": "See Alternatives"}],
                            missing_param=f"line_item_sku:{idx}",
                        ),
                        bound_slots=bound,
                        missing_slots=[f"line_item_sku:{idx}"],
                    )
            elif matched_cat.get("in_stock") is False:
                return ToolEvaluationResult(
                    status=ToolStatus.OUT_OF_STOCK,
                    tool_name=self.contract.tool_name,
                    clarification=ToolClarificationPrompt(
                        prompt_text=f"Apologies, *{matched_cat['name']}* is currently out of stock.",
                        buttons=[{"id": "INTENT:SHOW_CATALOG", "title": "See Alternatives"}],
                        missing_param=f"line_item_sku:{idx}",
                    ),
                    bound_slots=bound,
                    missing_slots=[f"line_item_sku:{idx}"],
                )

            unit_kobo = int(matched_cat["price_kobo"])
            offering_id = matched_cat.get("offering_id") or compute_offering_id(merchant_id, matched_cat["sku"])
            resolved_items.append({
                "offering_id": offering_id,
                "sku": matched_cat["sku"],
                "product": matched_cat.get("category", item.get("product")),
                "product_name": matched_cat["name"],
                "quantity": qty_val,
                "unit_price_kobo": unit_kobo,
                "subtotal_kobo": unit_kobo * qty_val,
                "in_stock": True,
            })

        bound["line_items"] = resolved_items
        bound["offering_id"] = resolved_items[0]["offering_id"]
        bound["sku"] = resolved_items[0]["sku"]
        bound["product_name"] = " + ".join(f"{it['quantity']}x {it['product_name']}" for it in resolved_items)
        bound["quantity"] = sum(it["quantity"] for it in resolved_items)

        cart_summary = bound["product_name"]

        # Resolve Fulfillment Type
        fulfillment = bound.get("fulfillment_type")
        if fulfillment:
            f_upper = str(fulfillment).upper()
            if "PICKUP" in f_upper or "COLLECT" in f_upper or "WAREHOUSE" in f_upper:
                bound["fulfillment_type"] = "WAREHOUSE_PICKUP"
            else:
                bound["fulfillment_type"] = "EXPRESS_DELIVERY"
        else:
            if bound.get("location") or bound.get("delivery_zone"):
                bound["fulfillment_type"] = "EXPRESS_DELIVERY"
            else:
                return ToolEvaluationResult(
                    status=ToolStatus.NEEDS_CLARIFICATION,
                    tool_name=self.contract.tool_name,
                    clarification=ToolClarificationPrompt(
                        prompt_text=f"For your bulk order (*{cart_summary}*), how would you like to receive it?",
                        buttons=[
                            {"id": "SET_SLOT:fulfillment_type:EXPRESS_DELIVERY", "title": "Express Delivery"},
                            {"id": "SET_SLOT:fulfillment_type:WAREHOUSE_PICKUP", "title": "Warehouse Pickup"},
                        ],
                        missing_param="fulfillment_type",
                    ),
                    bound_slots=bound,
                    missing_slots=["fulfillment_type"],
                )

        delivery_fee_kobo = 0
        if bound["fulfillment_type"] == "EXPRESS_DELIVERY":
            raw_zone = (bound.get("delivery_zone") or bound.get("location") or "").lower().strip()
            resolved_zone: Optional[str] = None
            for zone_key, fee in ZONE_DELIVERY_FEES_KOBO.items():
                if zone_key in raw_zone:
                    resolved_zone = zone_key
                    delivery_fee_kobo = fee
                    break
            if not resolved_zone:
                return ToolEvaluationResult(
                    status=ToolStatus.NEEDS_CLARIFICATION,
                    tool_name=self.contract.tool_name,
                    clarification=ToolClarificationPrompt(
                        prompt_text=f"Almost done! Where should we deliver your bulk order (*{cart_summary}*)?",
                        buttons=[
                            {"id": "SET_SLOT:delivery_zone:Ikeja", "title": "Ikeja / Mainland"},
                            {"id": "SET_SLOT:delivery_zone:Lekki", "title": "Lekki / Island"},
                            {"id": "SET_SLOT:delivery_zone:Abuja", "title": "Abuja FCT"},
                        ],
                        missing_param="delivery_zone",
                    ),
                    bound_slots=bound,
                    missing_slots=["delivery_zone"],
                )
            bound["delivery_zone"] = resolved_zone.capitalize()
            bound["delivery_fee_kobo"] = delivery_fee_kobo

        subtotal_kobo = sum(it["subtotal_kobo"] for it in resolved_items)
        total_payable_kobo = subtotal_kobo + delivery_fee_kobo

        breakdown = {
            "line_items": resolved_items,
            "offering_id": bound["offering_id"],
            "sku": bound["sku"],
            "product_name": cart_summary,
            "quantity": bound["quantity"],
            "subtotal_kobo": subtotal_kobo,
            "fulfillment_type": bound["fulfillment_type"],
            "delivery_zone": bound.get("delivery_zone", "Self-Pickup"),
            "delivery_fee_kobo": delivery_fee_kobo,
            "total_payable_kobo": total_payable_kobo,
        }

        return ToolEvaluationResult(
            status=ToolStatus.CONVERGED,
            tool_name=self.contract.tool_name,
            bound_slots=bound,
            missing_slots=[],
            calculated_total_kobo=total_payable_kobo,
            breakdown=breakdown,
            action="GENERATE_VIRTUAL_NUBAN_HOLD",
        )


# -----------------------------------------------------------------------------
# LOCAL TOOL DISPATCHER REGISTRY
# -----------------------------------------------------------------------------
class LocalToolDispatcher:
    """Central registry and execution dispatcher for local in-process tools."""

    def __init__(self):
        self._tools: Dict[str, LocalTool] = {}
        # Auto-register default tools
        self.register_tool(CheckoutOrderTool())

    def register_tool(self, tool: LocalTool) -> None:
        """Registers a local tool under its intent and tool name."""
        self._tools[tool.contract.tool_name.lower()] = tool
        self._tools[tool.contract.intent.lower()] = tool

    def get_tool(self, identifier: str) -> Optional[LocalTool]:
        """Retrieves registered tool by intent or tool name."""
        return self._tools.get(identifier.lower())

    async def evaluate(
        self,
        intent: str,
        slots: Dict[str, Any],
        catalog_manifest: Optional[str] = None,
        stock_checker: Optional[Any] = None,
        **kwargs: Any,
    ) -> Optional[ToolEvaluationResult]:
        """Dispatches slots to the matching tool and evaluates parameter contracts."""
        tool = self.get_tool(intent)
        if not tool:
            return None
        return await tool.evaluate(
            slots=slots,
            catalog_manifest=catalog_manifest,
            stock_checker=stock_checker,
            **kwargs,
        )


_dispatcher_singleton: Optional[LocalToolDispatcher] = None


def get_local_tool_dispatcher() -> LocalToolDispatcher:
    """Returns singleton LocalToolDispatcher instance."""
    global _dispatcher_singleton
    if _dispatcher_singleton is None:
        _dispatcher_singleton = LocalToolDispatcher()
    return _dispatcher_singleton
