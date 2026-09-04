"""Stage 1: Deterministic Trigram & Regex Fast-Path Intent Router for Nigerian SME Dialogues."""

import re
import time
from typing import Optional, Dict, Any
from app.adapters.base import ClassificationOutput


def extract_commercial_entities(text: str) -> Dict[str, Any]:
    """Extracts Nigerian location, commercial quantities, and Naira budget entities."""
    lower = text.lower()
    entities: Dict[str, Any] = {}

    # 1. Location Entity Extraction
    if re.search(r"\b(ikeja|computer\s*village|allen|ogba|maryland)\b", lower):
        entities["location"] = "Ikeja / Mainland, Lagos"
    elif re.search(r"\b(lekki|vi|victoria\s*island|ikoyi|ajah|chevron)\b", lower):
        entities["location"] = "Lekki / Island, Lagos"
    elif re.search(r"\b(yaba|surulere|ebute\s*metta|unilag)\b", lower):
        entities["location"] = "Yaba / Central, Lagos"
    elif re.search(r"\b(abuja|garki|wuse|maitama|gwarinpa)\b", lower):
        entities["location"] = "Abuja FCT"
    elif re.search(r"\b(ibadan|bodija|dugbe|ring\s*road)\b", lower):
        entities["location"] = "Ibadan, Oyo"

    # 2. Quantity Entity Extraction
    qty_match = re.search(r"(\d+)\s*(cartons?|bags?|units?|pieces?|packs?|crates?|doz)", lower)
    if qty_match:
        entities["quantity"] = f"{qty_match.group(1)} {qty_match.group(2)}"

    # 3. Budget / Currency Extraction (Kobo)
    budget_match = re.search(r"(?:₦|ngn|naira|\b)?\s*(\d{1,3}(?:,\d{3})*|\d+)\s*(k|thousand|m|million)?\b", lower)
    if budget_match:
        val_str = budget_match.group(1).replace(",", "")
        multiplier_str = budget_match.group(2)
        try:
            num = float(val_str)
            if multiplier_str in ["k", "thousand"]:
                num *= 1000
            elif multiplier_str in ["m", "million"]:
                num *= 1000000
            if num >= 500:
                entities["budget_naira"] = num
                entities["budget_kobo"] = int(num * 100)
        except ValueError:
            pass

    return entities


def fast_path_classify(
    text: str,
    custom_dictionary: Optional[list] = None,
) -> Optional[ClassificationOutput]:
    """
    Stage 1 Classifier: Matches deterministic commercial phrases with sub-millisecond execution.
    Checks merchant custom dictionary first, then falls back to static Nigerian slang regexes.
    Returns ClassificationOutput if confidence >= threshold, or None.
    """
    start_time = time.perf_counter()
    lower = text.lower().strip()
    entities = extract_commercial_entities(text)
    dialect = "Nigerian Pidgin" if re.search(r"\b(don|dey|wetin|abeg|oya|fit|sef)\b", lower) else "Commercial Slang"

    # 0. Merchant-Specific Custom Fast-Path Dictionary
    if custom_dictionary:
        for rule in custom_dictionary:
            phrase = (rule.get("phrase_pattern") or "").lower().strip()
            if phrase and phrase in lower:
                latency = (time.perf_counter() - start_time) * 1000.0
                return ClassificationOutput(
                    intent=rule.get("intent", "CUSTOM_MERCHANT_INTENT"),
                    lead_tier=rule.get("lead_tier", "WARM"),
                    urgency_score=rule.get("urgency_score", 7),
                    confidence=0.98,
                    detected_dialect=dialect,
                    suggested_reply=rule.get("suggested_response_template", "Thank you! We received your custom request."),
                    action=rule.get("action", "EXECUTE_CUSTOM_FAST_PATH_WORKFLOW"),
                    extracted_entities=entities,
                    tokens_consumed=0,
                    latency_ms=max(1.0, latency),
                )

    # 1. Payment Transfer Confirmation (High-intent hot lead)
    if re.search(r"(?:i\s*don\s*pay|done\s*transfer|i\s*sent\s*the\s*money|alert\s*don\s*enter|see\s*debit\s*alert|receipt\s*dey|transfer\s*successful|paid|i\s*have\s*paid)", lower):
        latency = (time.perf_counter() - start_time) * 1000.0
        return ClassificationOutput(
            intent="CONFIRM_PAYMENT",
            lead_tier="HOT",
            urgency_score=10,
            confidence=0.98,
            detected_dialect=dialect,
            suggested_reply="Bless up! 🙌 Your payment confirmation has been received. Our automated anti-ghosting ledger is matching your transfer ref with Moniepoint. Confirmation incoming sharp sharp!",
            action="TRIGGER_LEDGER_RECONCILIATION",
            extracted_entities=entities,
            tokens_consumed=0,
            latency_ms=max(1.5, latency),
        )

    # 2. Instant Order / Checkout Intent
    if re.search(r"(?:i\s*wan\s*buy|i\s*wan\s*order|send\s*account\s*details|how\s*i\s*go\s*pay|pack\s*\d+|deliver\s*to|drop\s*am\s*for|i\s*need\s*\d+|give\s*me\s*\d+)", lower):
        latency = (time.perf_counter() - start_time) * 1000.0
        loc = entities.get("location", "")
        loc_str = f" for delivery to {loc}" if loc else ""
        return ClassificationOutput(
            intent="INSTANT_CHECKOUT_ORDER",
            lead_tier="HOT",
            urgency_score=9,
            confidence=0.95,
            detected_dialect=dialect,
            suggested_reply=f"Sharp! I have reserved your item order{loc_str}. We don lock your cart for 10 minutes anti-ghosting hold.\n\n🏦 *Payment Details (Dedicated Virtual NUBAN):*\nBank: *Moniepoint MFB*\nAccount Name: *Enterprise SME Store*\nAccount Number: *9031842901*\n\nOnce transfer clear, receipt go land here instantly!",
            action="GENERATE_VIRTUAL_NUBAN_HOLD",
            extracted_entities=entities,
            tokens_consumed=0,
            latency_ms=max(1.5, latency),
        )

    # 3. Reservation & Booking Slot Hold
    if re.search(r"(?:book\s*(?:appointment|session|slot)|reserve\s*space|lock\s*my\s*date|schedule\s*meeting|any\s*slot\s*for\s*tomorrow)", lower):
        latency = (time.perf_counter() - start_time) * 1000.0
        return ClassificationOutput(
            intent="RESERVE_APPOINTMENT",
            lead_tier="HOT",
            urgency_score=9,
            confidence=0.94,
            detected_dialect=dialect,
            suggested_reply="Got you covered! 🗓️ We have atomic slot locking with GiST anti-double-booking protection. A 10-minute provisional hold is now active. Please confirm your ₦5,000 commitment deposit to lock your calendar slot.",
            action="ATOMIC_SLOT_HOLD",
            extracted_entities=entities,
            tokens_consumed=0,
            latency_ms=max(1.5, latency),
        )

    # 4. Price & Catalog Inquiry
    if re.search(r"(?:how\s*much|wetin\s*be\s*the\s*price|price\s*dey|give\s*me\s*discount|abeg\s*reduce\s*small|last\s*price|dm\s*price|catalog)", lower):
        latency = (time.perf_counter() - start_time) * 1000.0
        return ClassificationOutput(
            intent="PRICE_INQUIRY",
            lead_tier="WARM",
            urgency_score=7,
            confidence=0.92,
            detected_dialect=dialect,
            suggested_reply="Hello! Here is our SME wholesale price catalog:\n📦 *Grade A Premium Unit*: ₦24,500 / carton\n📦 *Bulk Order (5+ cartons)*: ₦22,000 / carton + Free Ikeja/Lekki dispatch\n\nHow many cartons you wan make we pack for you today?",
            action="SHOW_PRODUCT_CATALOG",
            extracted_entities=entities,
            tokens_consumed=0,
            latency_ms=max(1.5, latency),
        )

    # 5. Live Agent Desk Escalation
    if re.search(r"(?:speak\s*to\s*human|talk\s*to\s*person|agent\s*abeg|customer\s*care|call\s*me|real\s*person)", lower):
        latency = (time.perf_counter() - start_time) * 1000.0
        return ClassificationOutput(
            intent="HUMAN_AGENT_HANDOFF",
            lead_tier="WARM",
            urgency_score=8,
            confidence=0.96,
            detected_dialect=dialect,
            suggested_reply="No wahala! I am transferring you directly to our live desk agent. Our system is injecting your full context so the agent won't ask you repeated questions. 👨‍💼",
            action="DISPATCH_AGENT_HANDOFF",
            extracted_entities=entities,
            tokens_consumed=0,
            latency_ms=max(1.5, latency),
        )

    # 6. Greeting Engagement
    if re.search(r"\b(?:how\s*far|wetin\s*dey|good\s*(?:morning|afternoon|evening)|hello|hi|hey|oya)\b", lower):
        latency = (time.perf_counter() - start_time) * 1000.0
        return ClassificationOutput(
            intent="GREETING_ENGAGEMENT",
            lead_tier="WARM",
            urgency_score=5,
            confidence=0.91,
            detected_dialect=dialect,
            suggested_reply="How far! Welcome to Enterprise WhatsApp Hub. 🙌 We provide automated checkouts, atomic reservations, and real-time bank transfer anti-ghosting delivery across Nigeria.\n\nHow we fit help your business today?",
            action="SHOW_MAIN_MENU",
            extracted_entities=entities,
            tokens_consumed=0,
            latency_ms=max(1.5, latency),
        )

    return None
