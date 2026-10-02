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

        if norm_intent == "PRICE_INQUIRY":
            has_product_entity = bool(
                entities.get("product")
                or entities.get("category")
                or entities.get("product_name")
            )
            if catalog_count == 0 and has_product_entity:
                return ResponseStrategy.CATALOG_MISS_ALERT
            if catalog_count == 1:
                return ResponseStrategy.SINGLE_PRODUCT_QUOTE
            if catalog_count > 1:
                return ResponseStrategy.CATALOG_PRODUCT_LIST
            return ResponseStrategy.FULL_CATALOG_BROWSE

        if norm_intent in ["SHOW_PRODUCT_CATALOG", "BROWSE_CATALOG"]:
            has_product_entity = bool(
                entities.get("product")
                or entities.get("category")
                or entities.get("product_name")
            )
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

        return ResponseStrategy.STANDARD_TEXT
