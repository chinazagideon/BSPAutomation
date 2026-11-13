"""Deterministic Response Orchestration Layer (ADR-0044).

Coordinates between Cascading NLU, KnowledgeService catalog search,
ResponseClassifier, ResponseFormatter, and the Egress Gateway.
Handles dual interactive ID scheme (PRODUCT:{sku} & SET_SLOT:{slot}:{value})
and emits CatalogMissDetectedEvent on missing inventory.
"""

from typing import Dict, Any, Optional, Union, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.contexts.knowledge.services import KnowledgeService
from app.contexts.knowledge.offering_schemas import CoreOfferingDTO
from app.core.events import event_bus, CatalogMissDetectedEvent
from app.core.generation.response_classifier import ResponseClassifier, ResponseStrategy
from app.core.generation.response_formatter import (
    ResponseFormatter,
    EgressPayloadEnvelope,
    EgressMessageType,
)
from app.core.generation.negotiation import NegotiationFrameManager, NegotiationFrame
from app.core.generation.tools import get_local_tool_dispatcher, ToolStatus

logger = structlog.get_logger(__name__)


class ResponseOrchestrator:
    """Central conversational commerce coordinator between NLU, Knowledge Catalog, and Egress."""

    @classmethod
    async def resolve(
        cls,
        merchant_id: Union[UUID, str],
        nlu_result: Any,
        customer_phone: str,
        raw_message: str = "",
        session: Optional[AsyncSession] = None,
        merchant_name: str = "Enterprise SME Store",
    ) -> EgressPayloadEnvelope:
        """Resolves conversational turn to channel-compliant EgressPayloadEnvelope."""
        # 1. Normalize NLU result attributes
        if isinstance(nlu_result, dict):
            intent = nlu_result.get("intent", "STANDARD_TEXT")
            entities = nlu_result.get("extracted_entities", {}) or {}
            suggested_reply = nlu_result.get("suggested_reply", "")
        else:
            intent = getattr(nlu_result, "intent", "STANDARD_TEXT")
            entities = getattr(nlu_result, "extracted_entities", {}) or {}
            suggested_reply = getattr(nlu_result, "suggested_reply", "")

        # 2. Extract potential commercial search terms
        norm_intent = (intent or "").strip().upper()
        is_catalog_intent = norm_intent in [
            "PRICE_INQUIRY",
            "SHOW_PRODUCT_CATALOG",
            "BROWSE_CATALOG",
            "STOCK_AVAILABILITY_INQUIRY",
        ]

        query_term = (
            entities.get("product")
            or entities.get("product_name")
            or entities.get("category")
            or ""
        )
        if not query_term and is_catalog_intent:
            # Fallback to scanning raw message for common commercial commodities ONLY if intent is catalog-related
            import re
            raw_lower = raw_message.lower()
            for token in ["rice", "sugar", "oil", "flour", "beans", "cement", "milk", "garri", "noodles"]:
                if re.search(rf"\b{token}\b", raw_lower):
                    query_term = token
                    break

        # 3. Perform catalog search if commercially relevant
        catalog_results: List[CoreOfferingDTO] = []
        if is_catalog_intent or (query_term and norm_intent in ["INSTANT_CHECKOUT_ORDER"]):
            catalog_results = await KnowledgeService.search_catalog_offerings(
                merchant_id=merchant_id,
                query=query_term,
                session=session,
            )

        catalog_count = len(catalog_results)

        # 4. Classify response strategy
        strategy = ResponseClassifier.classify_strategy(
            intent=intent,
            entities=entities,
            catalog_count=catalog_count,
            is_converged=False,
        )

        logger.info(
            "response_strategy_resolved",
            merchant_id=str(merchant_id),
            intent=intent,
            query_term=query_term,
            catalog_count=catalog_count,
            matching_skus=[item.sku for item in catalog_results[:5]],
            strategy=strategy.value,
        )

        # 5. Format egress envelope based on strategy
        if strategy == ResponseStrategy.CATALOG_MISS_ALERT:
            # Emit CatalogMissDetectedEvent to decoupled event bus
            miss_term = query_term or raw_message
            await event_bus.publish(
                CatalogMissDetectedEvent(
                    merchant_id=str(merchant_id),
                    customer_phone=customer_phone,
                    query_term=miss_term,
                    raw_message=raw_message,
                    detected_category=entities.get("category"),
                )
            )
            return ResponseFormatter.format_catalog_miss(
                to_phone=customer_phone,
                query_term=miss_term,
                merchant_name=merchant_name,
            )

        if strategy == ResponseStrategy.CATALOG_PRODUCT_LIST:
            title = f"{query_term.title()} Catalog" if query_term else "Product Catalog"
            return ResponseFormatter.format_interactive_list(
                to_phone=customer_phone,
                offerings=catalog_results,
                query_title=title,
            )

        if strategy == ResponseStrategy.SINGLE_PRODUCT_QUOTE:
            offering = catalog_results[0]
            return ResponseFormatter.format_product_detail_card(
                to_phone=customer_phone,
                offering=offering,
            )

        if strategy == ResponseStrategy.ORDER_STATUS_CARD:
            from app.core.generation.order_ledger import CustomerOrderLedger
            inquiry_res = await CustomerOrderLedger.lookup_order_for_inquiry(
                merchant_id=str(merchant_id),
                customer_phone=customer_phone,
                order_ref=entities.get("order_reference"),
                session=session,
            )
            return ResponseFormatter.format_order_status_card(
                to_phone=customer_phone,
                order=inquiry_res.order,
                multiple_orders=inquiry_res.orders if inquiry_res.cardinality == "MULTIPLE" else None,
                merchant_name=merchant_name,
            )

        if strategy == ResponseStrategy.UNRESOLVED_DISAMBIGUATION:
            from app.core.generation.negotiation import NegotiationFrameManager
            stack = await NegotiationFrameManager.load_stack(str(merchant_id), customer_phone)
            top = stack.peek()
            has_cart = bool(top and top.intent == "INSTANT_CHECKOUT_ORDER" and top.missing_slots)
            cart_summary = (
                f"{top.bound_slots.get('quantity', 1)}x {top.bound_slots.get('product_name') or top.bound_slots.get('product') or 'items'}"
                if has_cart
                else None
            )
            return ResponseFormatter.format_unresolved_disambiguation(
                to_phone=customer_phone,
                has_active_cart=has_cart,
                cart_summary=cart_summary,
                merchant_name=merchant_name,
            )

        if strategy == ResponseStrategy.FULL_CATALOG_BROWSE:
            if catalog_results:
                return ResponseFormatter.format_interactive_list(
                    to_phone=customer_phone,
                    offerings=catalog_results,
                    query_title="All Products",
                )
            return ResponseFormatter.format_standard_text(
                to_phone=customer_phone,
                text=suggested_reply or f"Welcome to {merchant_name}! How may we help you today?",
                strategy=ResponseStrategy.FULL_CATALOG_BROWSE,
            )

        if strategy == ResponseStrategy.AGENT_HANDOFF:
            return ResponseFormatter.format_standard_text(
                to_phone=customer_phone,
                text=suggested_reply or "A human agent will be with you shortly.",
                strategy=ResponseStrategy.AGENT_HANDOFF,
            )

        if strategy == ResponseStrategy.SLOT_CLARIFICATION:
            clarification_buttons = entities.get("clarification_buttons")
            if clarification_buttons and isinstance(clarification_buttons, list) and len(clarification_buttons) > 0:
                return ResponseFormatter.format_interactive_buttons(
                    to_phone=customer_phone,
                    body_text=suggested_reply or "Please select an option:",
                    buttons=clarification_buttons,
                    strategy=ResponseStrategy.SLOT_CLARIFICATION,
                )
            return ResponseFormatter.format_standard_text(
                to_phone=customer_phone,
                text=suggested_reply or "Please select your order preferences.",
                strategy=ResponseStrategy.SLOT_CLARIFICATION,
            )

        # Default fallback: Standard Text
        return ResponseFormatter.format_standard_text(
            to_phone=customer_phone,
            text=suggested_reply or f"Thank you for contacting {merchant_name}!",
            strategy=ResponseStrategy.STANDARD_TEXT,
        )

    @classmethod
    async def resolve_interactive_action(
        cls,
        merchant_id: Union[UUID, str],
        interactive_id: str,
        customer_phone: str,
        session: Optional[AsyncSession] = None,
        merchant_name: str = "Enterprise SME Store",
        catalog_manifest: Optional[str] = None,
    ) -> EgressPayloadEnvelope:
        """Routes interactive list and button taps via Discriminated Union + match/case in ConversationFSMService."""
        from app.core.generation.fsm import ConversationFSMService

        return await ConversationFSMService.dispatch_interactive_protocol(
            merchant_id=merchant_id,
            interactive_id=interactive_id,
            customer_phone=customer_phone,
            session=session,
            merchant_name=merchant_name,
            catalog_manifest=catalog_manifest,
        )
