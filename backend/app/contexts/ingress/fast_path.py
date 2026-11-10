"""Stage 1: Native spaCy & Deterministic Fast-Path Intent Router for Nigerian SME Dialogues."""

import time
from typing import Any, Dict, Optional
import structlog

from app.adapters.base import ClassificationOutput
from app.adapters.providers.spacy_nlu_engine import (
    STAGE_1_FAST_PATH_INTENTS,
    get_spacy_nlu_engine,
)

logger = structlog.get_logger(__name__)

# Stage 1 deterministic action and reply templates mapped by canonical intent
_STAGE_1_INTENT_METADATA: Dict[str, Dict[str, Any]] = {
    "CONFIRM_PAYMENT": {
        "rule_source": "confirm_payment",
        "lead_tier": "HOT",
        "urgency_score": 10,
        "confidence": 0.98,
        "action": "TRIGGER_LEDGER_RECONCILIATION",
        "suggested_reply": (
            "Bless up! 🙌 Your payment confirmation has been received. "
            "Our automated anti-ghosting ledger is matching your transfer ref with Moniepoint. "
            "Confirmation incoming sharp sharp!"
        ),
    },
    "CANCEL_ORDER": {
        "rule_source": "cancel_order",
        "lead_tier": "COLD",
        "urgency_score": 5,
        "confidence": 0.98,
        "action": "CANCEL_NEGOTIATION_FRAME",
        "suggested_reply": (
            "No wahala! We don clear your pending order. "
            "Let us know anytime you're ready to order again."
        ),
    },
    "PRICE_INQUIRY": {
        "rule_source": "price_or_stock_inquiry",
        "lead_tier": "HOT",
        "urgency_score": 8,
        "confidence": 0.96,
        "action": "SHOW_PRODUCT_CATALOG",
        "suggested_reply": None,
    },
    "INSTANT_CHECKOUT_ORDER": {
        "rule_source": "instant_checkout_order",
        "lead_tier": "HOT",
        "urgency_score": 9,
        "confidence": 0.95,
        "action": "DISPATCH_LOCAL_TOOL",
        "suggested_reply": None,
    },
    "RESERVE_APPOINTMENT": {
        "rule_source": "reserve_appointment",
        "lead_tier": "HOT",
        "urgency_score": 9,
        "confidence": 0.94,
        "action": "ATOMIC_SLOT_HOLD",
        "suggested_reply": (
            "Got you covered! 🗓️ We have atomic slot locking with GiST anti-double-booking protection. "
            "A 10-minute provisional hold is now active. Please confirm your ₦5,000 commitment deposit to lock your calendar slot."
        ),
    },
    "HUMAN_AGENT_HANDOFF": {
        "rule_source": "human_agent_handoff",
        "lead_tier": "WARM",
        "urgency_score": 8,
        "confidence": 0.96,
        "action": "DISPATCH_AGENT_HANDOFF",
        "suggested_reply": (
            "No wahala! I am transferring you directly to our live desk agent. "
            "Our system is injecting your full context so the agent won't ask you repeated questions. 👨‍💼"
        ),
    },
    "GREETING_ENGAGEMENT": {
        "rule_source": "greeting_engagement",
        "lead_tier": "WARM",
        "urgency_score": 5,
        "confidence": 0.91,
        "action": "SHOW_MAIN_MENU",
        "suggested_reply": (
            "How far! Welcome to Enterprise WhatsApp Hub. 🙌 We provide automated checkouts, "
            "atomic reservations, and real-time bank transfer anti-ghosting delivery across Nigeria.\n\n"
            "How we fit help your business today?"
        ),
    },
}


def extract_commercial_entities(
    text: str,
    merchant_id: Optional[str] = None,
    active_bound_slots: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extracts Nigerian location, commercial quantities, Naira budgets, canonical offering_id/SKU, and multi-item line_items via SpacyNLUEngine."""
    engine = get_spacy_nlu_engine()
    entities, _, _ = engine.extract_entities(
        text,
        merchant_id=merchant_id,
        active_bound_slots=active_bound_slots,
    )
    return entities


def fast_path_classify(
    text: str,
    custom_dictionary: Optional[list] = None,
    merchant_id: Optional[str] = None,
) -> Optional[ClassificationOutput]:
    """
    Stage 1 Classifier: Executes merchant custom dictionary priority matching followed by
    natively trained spaCy intent & entity extraction (~1-2ms CPU).
    Returns ClassificationOutput if intent is a Stage 1 intent with confidence >= 0.90, else None.
    """
    start_time = time.perf_counter()
    lower = (text or "").lower().strip()
    engine = get_spacy_nlu_engine()
    dialect = engine.detect_dialect(text)

    # 0. Merchant-Specific Custom Fast-Path Dictionary
    if custom_dictionary:
        entities = extract_commercial_entities(text, merchant_id=merchant_id)
        for rule in custom_dictionary:
            phrase = (rule.get("phrase_pattern") or "").lower().strip()
            if phrase and phrase in lower:
                latency = (time.perf_counter() - start_time) * 1000.0
                out = ClassificationOutput(
                    intent=rule.get("intent", "CUSTOM_MERCHANT_INTENT"),
                    lead_tier=rule.get("lead_tier", "WARM"),
                    urgency_score=rule.get("urgency_score", 7),
                    confidence=0.98,
                    detected_dialect=dialect,
                    suggested_reply=rule.get(
                        "suggested_response_template",
                        "Thank you! We received your custom request.",
                    ),
                    action=rule.get("action", "EXECUTE_CUSTOM_FAST_PATH_WORKFLOW"),
                    extracted_entities=entities,
                    tokens_consumed=0,
                    latency_ms=max(1.0, latency),
                )
                logger.info(
                    "stage_1_fast_path_matched",
                    rule_source="custom_dictionary",
                    intent=out.intent,
                    confidence=out.confidence,
                    latency_ms=out.latency_ms,
                    entities=out.extracted_entities,
                )
                return out

    parsed = engine.predict_intent_and_slots(
        text=text,
        merchant_id=merchant_id,
    )

    if parsed.intent in STAGE_1_FAST_PATH_INTENTS and parsed.confidence >= 0.90:
        meta = _STAGE_1_INTENT_METADATA[parsed.intent]
        latency = (time.perf_counter() - start_time) * 1000.0
        out = ClassificationOutput(
            intent=parsed.intent,
            lead_tier=meta["lead_tier"],
            urgency_score=meta["urgency_score"],
            confidence=max(meta["confidence"], parsed.confidence),
            detected_dialect=parsed.detected_dialect,
            suggested_reply=meta["suggested_reply"],
            action=meta["action"],
            extracted_entities=parsed.slots,
            tokens_consumed=0,
            latency_ms=max(1.0, round(latency, 2)),
        )
        logger.info(
            "stage_1_fast_path_matched",
            rule_source=meta["rule_source"],
            intent=out.intent,
            confidence=out.confidence,
            latency_ms=out.latency_ms,
            entities=out.extracted_entities,
        )
        return out

    latency = (time.perf_counter() - start_time) * 1000.0
    logger.info(
        "stage_1_fast_path_missed",
        latency_ms=round(latency, 2),
        extracted_entities=parsed.slots,
    )
    return None
