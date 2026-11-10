"""Sandbox Simulator for the Stateless Open-Weight Model Layer (Function A & Function B).

Isolated inside app/sandbox/ per AGENTS.md. Provides 100% deterministic local simulation
of Function A (Grammar-Constrained Input Parsing) and Function B (Dynamic Prompt Hydration & Translation).
"""

import re
import time
from typing import Any, Dict, List, Optional

from app.adapters.base import (
    HydrationTranslationInput,
    HydrationTranslationOutput,
    ParsedTurnInput,
    StatelessOpenWeightPort,
)
from app.adapters.custom_classifier import LexicalDialectAnalyzer
from app.contexts.ingress.fast_path import extract_commercial_entities

AFFIRMATION_PATTERN = re.compile(
    r"^(?:yes|yeah|yep|yup|ok|okay|k|oya|sure|sharp|send\s*am|pls\s*do|please\s*do|correct|proceed|confirm|carry\s*go|abeg\s*send)\b",
    re.IGNORECASE,
)

NEGATION_PATTERN = re.compile(
    r"^(?:no|nah|nope|leave\s*am|never\s*mind|i\s*no\s*(?:wan|dey)\s*buy|i\s*no\s*want|forget\s*(?:am|it)|abort|cancel)\b",
    re.IGNORECASE,
)

MUTATION_TRIGGER_PATTERN = re.compile(
    r"\b(?:instead|change\s*(?:am|it)?\s*to|make\s*(?:am|it)|no\s*be\s*\w+\s*again|rather|swap\s*to|actually)\b",
    re.IGNORECASE,
)

SKU_CANDIDATE_MAP = {
    "dangote sugar": ("SUGAR_DANGOTE_50KG", "Dangote Sugar 50kg", "sugar"),
    "bua sugar": ("SUGAR_BUA_50KG", "BUA Sugar 50kg", "sugar"),
    "st louis": ("SUGAR_ST_LOUIS_500G", "St. Louis Sugar Cube (500g Pack)", "sugar"),
    "mama gold rice 25kg": ("RICE_MAMA_GOLD_25KG", "Mama Gold Rice 25kg", "rice"),
    "mama gold rice": ("RICE_MAMA_GOLD_50KG", "Mama Gold Rice 50kg", "rice"),
    "mama gold": ("RICE_MAMA_GOLD_50KG", "Mama Gold Rice 50kg", "rice"),
    "royal stallion": ("RICE_ROYAL_STALLION_50KG", "Royal Stallion Rice 50kg", "rice"),
    "devon": ("OIL_DEVONS_KING_25L", "Devon's King Vegetable Oil 25L", "oil"),
    "king oil": ("OIL_DEVONS_KING_25L", "Devon's King Vegetable Oil 25L", "oil"),
    "kings oil": ("OIL_DEVONS_KING_25L", "Devon's King Vegetable Oil 25L", "oil"),
    "golden penny": ("FLOUR_GOLDEN_PENNY_50KG", "Golden Penny Flour 50kg", "flour"),
}


class SandboxOpenWeightSimulator(StatelessOpenWeightPort):
    """Deterministic local simulator for Open-Weight Function A (Input Parser) and Function B (Translator)."""

    async def parse_input(
        self,
        text: str,
        expected_slot_hint: Optional[str] = None,
        custom_dictionary: Optional[List[Dict[str, Any]]] = None,
    ) -> ParsedTurnInput:
        start_time = time.perf_counter()
        cleaned_text = (text or "").strip()
        lower = cleaned_text.lower()
        dialect = LexicalDialectAnalyzer.detect_dialect(cleaned_text)
        entities = extract_commercial_entities(cleaned_text)

        # Normalize location -> delivery_zone for checkout compatibility
        if "location" in entities and "delivery_zone" not in entities:
            entities["delivery_zone"] = entities["location"]

        # Specific brand/SKU detection
        for brand_phrase, (sku, prod_name, category) in SKU_CANDIDATE_MAP.items():
            if brand_phrase in lower:
                entities["sku"] = sku
                entities["product_name"] = prod_name
                entities["product"] = category
                break

        # Detect explicit slot mutations ("instead", "make it 5 bags of Mama Gold Rice", "change am to")
        slot_mutations: Dict[str, Any] = {}
        if MUTATION_TRIGGER_PATTERN.search(lower):
            for k in ("sku", "product_name", "product", "quantity", "location", "delivery_zone", "fulfillment_type"):
                if k in entities:
                    slot_mutations[k] = entities[k]

        # 1. Disambiguate polysemous "drop am" (Delivery vs Cancellation)
        has_drop_am_delivery = bool(re.search(r"\bdrop\s*am\s*(?:for|to|at|in)\b", lower))
        if has_drop_am_delivery:
            entities["fulfillment_type"] = "EXPRESS_DELIVERY"

        is_cancel = bool(
            re.search(
                r"\b(cancel(?:\s+am|\s+order|\s+it)?|never\s*mind|no\s*buy\s*again|i\s*no\s*(?:wan|dey)\s*buy|forget\s*(?:am|it)|abort)\b",
                lower,
            )
        )
        if not is_cancel and re.search(r"\bdrop\s*am\b", lower) and not has_drop_am_delivery:
            is_cancel = True

        is_affirm = bool(AFFIRMATION_PATTERN.search(lower)) and not is_cancel
        is_negate = bool(NEGATION_PATTERN.search(lower))

        if is_cancel:
            latency = (time.perf_counter() - start_time) * 1000.0
            return ParsedTurnInput(
                intent="CANCEL_ORDER",
                canonical_query="Cancel active order",
                slots=entities,
                slot_mutations={},
                is_cancellation=True,
                is_affirmation=False,
                is_negation=True,
                detected_dialect=dialect,
                confidence=0.98,
                lead_tier="COLD",
                urgency_score=5,
                tokens_consumed=0,
                latency_ms=round(max(1.2, latency), 2),
            )

        # 2. Custom Merchant Fast-Path Dictionary
        if custom_dictionary:
            for rule in custom_dictionary:
                phrase = (rule.get("phrase_pattern") or "").lower().strip()
                if phrase and phrase in lower:
                    latency = (time.perf_counter() - start_time) * 1000.0
                    return ParsedTurnInput(
                        intent=rule.get("intent", "GENERAL_INQUIRY"),
                        canonical_query=cleaned_text,
                        slots=entities,
                        slot_mutations=slot_mutations,
                        detected_dialect=dialect,
                        confidence=0.98,
                        lead_tier=rule.get("lead_tier", "WARM"),
                        urgency_score=rule.get("urgency_score", 7),
                        tokens_consumed=0,
                        latency_ms=round(max(1.2, latency), 2),
                    )

        # 3. Out-of-Context / Sub-Flow Inquiry Detection (checked before slot-hint fallback!)
        # 3A. Delivery Timeline / ETA Inquiry ("how long delivery dey take", "when rider go move", "when e go land")
        if re.search(
            r"(?:when\s*e\s*go\s*land|how\s*long.*(?:deliver|take|reach)|delivery\s*timeline|dispatch\s*rider|interstate\s*waybill|how\s*many\s*(?:days|hours)|when\s*rider\s*go)",
            lower,
        ):
            latency = (time.perf_counter() - start_time) * 1000.0
            return ParsedTurnInput(
                intent="DELIVERY_TIMELINE_INQUIRY",
                canonical_query=f"Delivery timeline inquiry for {entities.get('location', 'customer area')}",
                slots=entities,
                slot_mutations={},
                detected_dialect=dialect,
                confidence=0.94,
                lead_tier="WARM",
                urgency_score=7,
                tokens_consumed=0,
                latency_ms=round(max(1.5, latency), 2),
            )

        # 3B. Trust, Proof & Shop Location Inquiry ("where your shop dey", "hope say no be scam", "you legit")
        if re.search(
            r"(?:hope\s*say\s*no\s*be\s*scam|you\s*legit|where\s*(?:your|una)\s*shop\s*dey|where\s*is\s*your\s*shop|proof\s*dey|see\s*past\s*work|reviews)",
            lower,
        ):
            latency = (time.perf_counter() - start_time) * 1000.0
            return ParsedTurnInput(
                intent="TRUST_VERIFICATION_PROOF",
                canonical_query="Verify merchant legitimacy and physical shop location",
                slots=entities,
                slot_mutations={},
                detected_dialect=dialect,
                confidence=0.95,
                lead_tier="WARM",
                urgency_score=7,
                tokens_consumed=0,
                latency_ms=round(max(1.5, latency), 2),
            )

        # 3C. Wholesale & Bulk Discount Negotiation
        if re.search(
            r"(?:slash\s*price|discount\s*dey|reduce\s*small|wholesale\s*price|if\s*i\s*buy\s*plenty|last\s*price)",
            lower,
        ):
            latency = (time.perf_counter() - start_time) * 1000.0
            return ParsedTurnInput(
                intent="WHOLESALE_DISCOUNT_INQUIRY",
                canonical_query="Wholesale bulk discount inquiry",
                slots=entities,
                slot_mutations={},
                detected_dialect=dialect,
                confidence=0.93,
                lead_tier="HOT",
                urgency_score=8,
                tokens_consumed=0,
                latency_ms=round(max(1.5, latency), 2),
            )

        # 3D. Live Agent Handoff
        if re.search(
            r"(?:speak\s*to\s*human|talk\s*to\s*person|agent\s*abeg|customer\s*care|call\s*me|real\s*person|human\s*agent)",
            lower,
        ):
            latency = (time.perf_counter() - start_time) * 1000.0
            return ParsedTurnInput(
                intent="HUMAN_AGENT_HANDOFF",
                canonical_query="Request human support agent handoff",
                slots=entities,
                slot_mutations={},
                detected_dialect=dialect,
                confidence=0.97,
                lead_tier="HOT",
                urgency_score=9,
                tokens_consumed=0,
                latency_ms=round(max(1.5, latency), 2),
            )

        # 3E. Payment Confirmation
        if re.search(
            r"\b(?:i\s*don\s*pay|done\s*transfer|i\s*sent\s*the\s*money|alert\s*don\s*enter|see\s*debit\s*alert|receipt\s*dey|transfer\s*successful|paid|i\s*have\s*paid)\b",
            lower,
        ):
            latency = (time.perf_counter() - start_time) * 1000.0
            return ParsedTurnInput(
                intent="CONFIRM_PAYMENT",
                canonical_query="Customer confirms bank transfer payment",
                slots=entities,
                slot_mutations={},
                detected_dialect=dialect,
                confidence=0.98,
                lead_tier="HOT",
                urgency_score=10,
                tokens_consumed=0,
                latency_ms=round(max(1.5, latency), 2),
            )

        # 3F. Appointment / Reservation Slot Hold
        if re.search(
            r"(?:book\s*(?:appointment|session|slot)|reserve\s*space|lock\s*my\s*date|schedule\s*meeting|any\s*slot\s*for\s*tomorrow)",
            lower,
        ):
            latency = (time.perf_counter() - start_time) * 1000.0
            return ParsedTurnInput(
                intent="RESERVE_APPOINTMENT",
                canonical_query="Book appointment reservation slot",
                slots=entities,
                slot_mutations={},
                detected_dialect=dialect,
                confidence=0.95,
                lead_tier="HOT",
                urgency_score=9,
                tokens_consumed=0,
                latency_ms=round(max(1.5, latency), 2),
            )

        # 3G. Price & Stock Availability Inquiry (when not explicitly mutating or placing an order)
        is_explicit_buy = bool(
            re.search(
                r"(?:i\s*wan\s*buy|i\s*wan\s*order|send\s*account\s*details|how\s*i\s*go\s*pay|pack\s*\d+|deliver\s*to|drop\s*am\s*(?:for|to|at)|i\s*need\s*\d+|give\s*me\s*\d+|i\s*want\s*\d+|buy\s*\d+)",
                lower,
            )
            or slot_mutations
        )
        is_price_or_stock_question = bool(
            re.search(
                r"(?:how\s*much|wetin\s*be\s*the\s*price|price\s*dey|dm\s*price|catalog|do\s*you\s*have|you\s*get|is\s*there|any\s*stock|in\s*stock|available|dey\s*(?:store|shop|ground)|una\s*get)\b",
                lower,
            )
        )
        if is_price_or_stock_question and not is_explicit_buy:
            if not entities.get("product"):
                for commodity in [
                    "rice", "sugar", "oil", "flour", "beans", "cement", "milk", "garri", "noodles", "salt",
                    "inverter", "laptop", "macbook", "starlink", "battery", "barber", "haircut", "massage", "facial",
                ]:
                    if commodity in lower:
                        entities["product"] = commodity
                        break
            latency = (time.perf_counter() - start_time) * 1000.0
            return ParsedTurnInput(
                intent="PRICE_INQUIRY",
                canonical_query=f"Price and stock inquiry for {entities.get('product', 'catalog')}",
                slots=entities,
                slot_mutations={},
                detected_dialect=dialect,
                confidence=0.95,
                lead_tier="HOT",
                urgency_score=8,
                tokens_consumed=0,
                latency_ms=round(max(1.5, latency), 2),
            )

        # 4. Checkout / Order Intent or Slot Continuation (guided by expected_slot_hint)
        if is_explicit_buy or (
            expected_slot_hint
            and any(k in entities for k in ("sku", "product", "quantity", "location", "delivery_zone", "fulfillment_type"))
        ):
            latency = (time.perf_counter() - start_time) * 1000.0
            return ParsedTurnInput(
                intent="INSTANT_CHECKOUT_ORDER",
                canonical_query=cleaned_text,
                slots=entities,
                slot_mutations=slot_mutations,
                is_affirmation=is_affirm,
                is_negation=is_negate,
                detected_dialect=dialect,
                confidence=0.96,
                lead_tier="HOT",
                urgency_score=9,
                tokens_consumed=0,
                latency_ms=round(max(1.5, latency), 2),
            )

        # 5. Greeting Engagement
        if re.search(r"\b(?:how\s*far|wetin\s*dey|good\s*(?:morning|afternoon|evening)|hello|hi|hey|oya)\b", lower):
            latency = (time.perf_counter() - start_time) * 1000.0
            return ParsedTurnInput(
                intent="GREETING_ENGAGEMENT",
                canonical_query="Customer greeting",
                slots=entities,
                is_affirmation=is_affirm,
                is_negation=is_negate,
                detected_dialect=dialect,
                confidence=0.92,
                lead_tier="WARM",
                urgency_score=5,
                tokens_consumed=0,
                latency_ms=round(max(1.2, latency), 2),
            )

        # 6. General / Open Consultation Fallback
        latency = (time.perf_counter() - start_time) * 1000.0
        return ParsedTurnInput(
            intent="GENERAL_INQUIRY",
            canonical_query=cleaned_text,
            slots=entities,
            slot_mutations=slot_mutations,
            is_affirmation=is_affirm,
            is_negation=is_negate,
            detected_dialect=dialect,
            confidence=0.70,
            lead_tier="WARM",
            urgency_score=6,
            tokens_consumed=0,
            latency_ms=round(max(1.5, latency), 2),
        )

    async def translate_output(
        self,
        hydration: HydrationTranslationInput,
    ) -> HydrationTranslationOutput:
        start_time = time.perf_counter()
        base_text = (hydration.fallback_body_text or "").strip()
        resumed = hydration.resumed_frame

        if not resumed:
            latency = (time.perf_counter() - start_time) * 1000.0
            return HydrationTranslationOutput(
                translated_text=base_text,
                fallback_body_text=base_text,
                tokens_consumed=0,
                latency_ms=round(max(1.0, latency), 2),
            )

        bound = resumed.get("bound_slots") or {}
        missing = resumed.get("missing_slots") or []
        resume_prompt = resumed.get("clarification_prompt") or ""
        product_label = bound.get("product_name") or bound.get("product") or "your item"
        qty_label = bound.get("quantity")

        is_pidgin = hydration.target_dialect == "Nigerian Pidgin"
        order_desc = f"{qty_label}x {product_label}" if qty_label else f"{product_label}"

        if not resume_prompt:
            next_slot = missing[0] if missing else "details"
            if next_slot == "delivery_zone":
                resume_prompt = (
                    f"Which area make we deliver your *{order_desc}* to?"
                    if is_pidgin
                    else f"Where should we deliver your *{order_desc}*?"
                )
            elif next_slot == "fulfillment_type":
                resume_prompt = (
                    f"For your *{order_desc}*, you wan Express Delivery or Warehouse Pickup?"
                    if is_pidgin
                    else f"For your *{order_desc}*, would you prefer Express Delivery or Warehouse Pickup?"
                )
            elif next_slot == "quantity":
                resume_prompt = (
                    f"How many bags/units of *{product_label}* you wan reserve?"
                    if is_pidgin
                    else f"How many units of *{product_label}* would you like to reserve?"
                )
            else:
                resume_prompt = (
                    f"Which brand/size of *{product_label}* you wan pick?"
                    if is_pidgin
                    else f"Which option for *{product_label}* would you like to select?"
                )

        bridge_header = (
            f"🔄 *Back to your active order ({order_desc}):*"
            if not is_pidgin
            else f"🔄 *Make we continue your order ({order_desc}):*"
        )
        combined = f"{base_text}\n\n{bridge_header}\n{resume_prompt}"
        latency = (time.perf_counter() - start_time) * 1000.0

        return HydrationTranslationOutput(
            translated_text=combined,
            fallback_body_text=combined,
            tokens_consumed=0,
            latency_ms=round(max(2.0, latency), 2),
        )
