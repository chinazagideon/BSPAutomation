"""Deterministic Zero-Token Response Strategy Classifier (ADR-0044).

Maps classified intent, extracted entities, and catalog match count to a concrete ResponseStrategy.
"""

from enum import Enum
from typing import Dict, Any


class ResponseStrategy(str, Enum):
    CATALOG_PRODUCT_LIST = "CATALOG_PRODUCT_LIST"
    SINGLE_PRODUCT_QUOTE = "SINGLE_PRODUCT_QUOTE"
    FULL_CATALOG_BROWSE = "FULL_CATALOG_BROWSE"
    CATALOG_MISS_ALERT = "CATALOG_MISS_ALERT"
    CHECKOUT_CONVERGED = "CHECKOUT_CONVERGED"
    SLOT_CLARIFICATION = "SLOT_CLARIFICATION"
    OUT_OF_STOCK_ALERT = "OUT_OF_STOCK_ALERT"
    RESERVE_APPOINTMENT = "RESERVE_APPOINTMENT"
    AGENT_HANDOFF = "AGENT_HANDOFF"
    STANDARD_TEXT = "STANDARD_TEXT"
    UNRESOLVED_DISAMBIGUATION = "UNRESOLVED_DISAMBIGUATION"
    ORDER_STATUS_CARD = "ORDER_STATUS_CARD"


class ResponseClassifier:
    """Deterministic, 0-token rule engine mapping NLU results & catalog count to response strategies."""

    @staticmethod
    def classify_strategy(
        intent: str,
        entities: Dict[str, Any],
        catalog_count: int,
        is_converged: bool = False,
    ) -> ResponseStrategy:
        norm_intent = (intent or "").strip().upper()

        if norm_intent in ["ORDER_STATUS_INQUIRY", "RESOLVE_ORDER_STATUS"]:
            return ResponseStrategy.ORDER_STATUS_CARD

        has_product_entity = bool(
            entities.get("product")
            or entities.get("category")
            or entities.get("product_name")
        )

        is_explicit_catalog_intent = norm_intent in [
            "PRICE_INQUIRY",
            "SHOW_PRODUCT_CATALOG",
            "BROWSE_CATALOG",
            "STOCK_AVAILABILITY_INQUIRY",
        ]
        is_commercial_intent = is_explicit_catalog_intent or norm_intent == "INSTANT_CHECKOUT_ORDER"

        if is_explicit_catalog_intent or (has_product_entity and is_commercial_intent and catalog_count > 0):
            if catalog_count == 0 and has_product_entity:
                return ResponseStrategy.CATALOG_MISS_ALERT
            if catalog_count == 1:
                return ResponseStrategy.SINGLE_PRODUCT_QUOTE
            if catalog_count > 1:
                return ResponseStrategy.CATALOG_PRODUCT_LIST
            return ResponseStrategy.FULL_CATALOG_BROWSE

        if norm_intent == "INSTANT_CHECKOUT_ORDER":
            if is_converged:
                return ResponseStrategy.CHECKOUT_CONVERGED
            return ResponseStrategy.SLOT_CLARIFICATION

        if norm_intent in ["HUMAN_AGENT_HANDOFF", "DISPATCH_AGENT_HANDOFF"]:
            return ResponseStrategy.AGENT_HANDOFF

        if norm_intent == "RESERVE_APPOINTMENT":
            return ResponseStrategy.RESERVE_APPOINTMENT

        if norm_intent in ["UNRESOLVED_GENERAL_QUERY", "UNRESOLVED_DISAMBIGUATION", "GENERAL_INQUIRY", "SHOW_HELP_MENU"]:
            return ResponseStrategy.UNRESOLVED_DISAMBIGUATION

        return ResponseStrategy.STANDARD_TEXT
