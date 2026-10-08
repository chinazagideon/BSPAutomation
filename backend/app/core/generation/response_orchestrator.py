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
        query_term = (
            entities.get("product")
            or entities.get("product_name")
            or entities.get("category")
            or ""
        )
        if not query_term:
            # Fallback to scanning raw message for common commercial commodities
            raw_lower = raw_message.lower()
            for token in ["rice", "sugar", "oil", "flour", "beans", "cement", "milk", "garri", "noodles", "carton", "bag"]:
                if token in raw_lower:
                    query_term = token
                    break

        # 3. Perform catalog search if commercially relevant
        catalog_results: List[CoreOfferingDTO] = []
        if intent in ["PRICE_INQUIRY", "SHOW_PRODUCT_CATALOG", "BROWSE_CATALOG", "STOCK_AVAILABILITY_INQUIRY"] or query_term:
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
        """Routes interactive list and button taps via Dual Interactive ID Scheme."""
        interactive_id = (interactive_id or "").strip()

        # Resolve dynamic merchant name if default was supplied
        if merchant_name == "Enterprise SME Store":
            try:
                from app.contexts.ingress.services import IngressService
                provider_ctx = IngressService.get_cached_provider_context(str(merchant_id))
                if provider_ctx and isinstance(provider_ctx, dict) and provider_ctx.get("verified_business_name"):
                    merchant_name = provider_ctx["verified_business_name"]
            except Exception:
                pass

        # 1. Exploratory Catalog Tap: PRODUCT:{sku}
        if interactive_id.startswith("PRODUCT:"):
            sku = interactive_id.split(":", 1)[1].strip()
            active_frame = await NegotiationFrameManager.get_frame(str(merchant_id), customer_phone)
            if not active_frame:
                active_frame = NegotiationFrame(
                    merchant_id=str(merchant_id),
                    phone_hash="",
                    active_tool="ProductCatalog",
                    intent="PRICE_INQUIRY",
                    bound_slots={"sku": sku},
                    missing_slots=[],
                )
            else:
                active_frame.intent = "PRICE_INQUIRY"
                active_frame.bound_slots["sku"] = sku
            await NegotiationFrameManager.save_frame(str(merchant_id), customer_phone, active_frame)

            offering = await KnowledgeService.get_offering_by_sku(
                merchant_id=merchant_id,
                sku=sku,
                session=session,
            )
            if offering:
                return ResponseFormatter.format_product_detail_card(
                    to_phone=customer_phone,
                    offering=offering,
                )
            return ResponseFormatter.format_catalog_miss(
                to_phone=customer_phone,
                query_term=sku,
                merchant_name=merchant_name,
            )

        # 2. Transactional Slot Binding: SET_SLOT:{slot_name}:{slot_value}
        if interactive_id.startswith("SET_SLOT:"):
            parsed = NegotiationFrameManager.parse_interactive_id(interactive_id)
            if parsed:
                slot_name, slot_val = parsed
                active_frame = await NegotiationFrameManager.get_frame(str(merchant_id), customer_phone)
                if not active_frame:
                    active_frame = NegotiationFrame(
                        merchant_id=str(merchant_id),
                        phone_hash="",
                        active_tool="CheckoutOrderTool",
                        intent="INSTANT_CHECKOUT_ORDER",
                        bound_slots={},
                        missing_slots=[],
                    )
                else:
                    # Explicit Intent Transition: Interaction type is transactional checkout
                    active_frame.intent = "INSTANT_CHECKOUT_ORDER"
                    active_frame.active_tool = "CheckoutOrderTool"
                    if slot_name == "sku" and active_frame.bound_slots.get("sku") != slot_val:
                        # Clear old slots when ordering a new SKU
                        active_frame.bound_slots = {}

                active_frame.bound_slots[slot_name] = slot_val

                # If setting SKU slot, verify stock and pre-bind attributes from KnowledgeService or catalog manifest
                if slot_name == "sku":
                    offering = await KnowledgeService.get_offering_by_sku(
                        merchant_id=merchant_id,
                        sku=slot_val,
                        session=session,
                    )
                    if offering:
                        stock_qty = (
                            offering.metadata.get("stock_quantity")
                            if isinstance(getattr(offering, "metadata", None), dict)
                            else None
                        )
                        if not offering.is_available or (stock_qty is not None and stock_qty <= 0):
                            await NegotiationFrameManager.evict_frame(str(merchant_id), customer_phone)
                            prompt = (
                                f"Apologies, *{offering.title}* is currently out of stock.\n\n"
                                f"Would you like to browse our available items or speak directly with our team?"
                            )
                            buttons = [
                                {"id": "SHOW_CATALOG", "title": "View Catalog"},
                                {"id": "AGENT_HANDOFF", "title": "Speak to Agent"},
                            ]
                            return ResponseFormatter.format_interactive_buttons(
                                to_phone=customer_phone,
                                body_text=prompt,
                                buttons=buttons,
                                strategy=ResponseStrategy.OUT_OF_STOCK_ALERT,
                            )
                        active_frame.bound_slots["sku"] = offering.sku
                        active_frame.bound_slots["product_name"] = offering.title
                        active_frame.bound_slots["unit_price_kobo"] = offering.price_kobo
                        active_frame.bound_slots["in_stock"] = True
                    else:
                        from app.core.generation.tools import DEFAULT_COMMODITY_CATALOG
                        catalog_to_check = catalog_manifest if catalog_manifest else DEFAULT_COMMODITY_CATALOG
                        matched = [item for item in catalog_to_check if item.get("sku", "").upper() == str(slot_val).upper()]
                        if matched:
                            matched_item = matched[0]
                            if matched_item.get("in_stock") is False:
                                await NegotiationFrameManager.evict_frame(str(merchant_id), customer_phone)
                                item_name = matched_item.get("name") or slot_val.replace("_", " ").title()
                                prompt = (
                                    f"Apologies, *{item_name}* is currently out of stock.\n\n"
                                    f"Would you like to browse our available items or speak directly with our team?"
                                )
                                buttons = [
                                    {"id": "SHOW_CATALOG", "title": "View Catalog"},
                                    {"id": "AGENT_HANDOFF", "title": "Speak to Agent"},
                                ]
                                return ResponseFormatter.format_interactive_buttons(
                                    to_phone=customer_phone,
                                    body_text=prompt,
                                    buttons=buttons,
                                    strategy=ResponseStrategy.OUT_OF_STOCK_ALERT,
                                )
                            active_frame.bound_slots["sku"] = matched_item["sku"]
                            active_frame.bound_slots["product_name"] = matched_item["name"]
                            active_frame.bound_slots["unit_price_kobo"] = matched_item["price_kobo"]
                            active_frame.bound_slots["in_stock"] = True
                        else:
                            active_frame.bound_slots["sku"] = slot_val

                if not catalog_manifest:
                    try:
                        from app.contexts.ingress.services import IngressService
                        catalog_manifest = IngressService.get_cached_catalog_manifest(str(merchant_id))
                    except Exception:
                        pass

                tool_res = await get_local_tool_dispatcher().evaluate(
                    intent="INSTANT_CHECKOUT_ORDER",
                    slots=active_frame.bound_slots,
                    catalog_manifest=catalog_manifest,
                )

                if tool_res:
                    if tool_res.status == ToolStatus.NEEDS_CLARIFICATION:
                        active_frame.missing_slots = tool_res.missing_slots
                        if tool_res.bound_slots:
                            active_frame.bound_slots.update(tool_res.bound_slots)
                        await NegotiationFrameManager.save_frame(str(merchant_id), customer_phone, active_frame)
                        prompt = tool_res.clarification.prompt_text if tool_res.clarification else "Please choose an option."
                        buttons = tool_res.clarification.buttons if tool_res.clarification else None
                        if buttons and isinstance(buttons, list) and len(buttons) > 0:
                            return ResponseFormatter.format_interactive_buttons(
                                to_phone=customer_phone,
                                body_text=prompt,
                                buttons=buttons,
                                strategy=ResponseStrategy.SLOT_CLARIFICATION,
                            )
                        return ResponseFormatter.format_standard_text(
                            to_phone=customer_phone,
                            text=prompt,
                            strategy=ResponseStrategy.SLOT_CLARIFICATION,
                        )

                    elif tool_res.status == ToolStatus.CONVERGED:
                        await NegotiationFrameManager.evict_frame(str(merchant_id), customer_phone)
                        total_kobo = tool_res.calculated_total_kobo or 0
                        total_naira = f"₦{total_kobo // 100:,}"
                        loc_str = (
                            f" for delivery to {tool_res.bound_slots.get('delivery_zone', 'your address')}"
                            if tool_res.bound_slots.get("fulfillment_type") == "EXPRESS_DELIVERY"
                            else " for warehouse self-pickup"
                        )
                        reply = (
                            f"Sharp! We don reserve your order ({tool_res.bound_slots.get('quantity', 1)}x {tool_res.bound_slots.get('product_name', 'item')}){loc_str}.\n"
                            f"Total Amount: *{total_naira}* (10-minute anti-ghosting hold).\n\n"
                            f"🏦 *Payment Details (Dedicated Virtual NUBAN):*\n"
                            f"Bank: *Moniepoint MFB*\n"
                            f"Account Name: *{merchant_name}*\n"
                            f"Account Number: *9031842901*\n\n"
                            f"Once transfer clear, receipt go land here sharp sharp!"
                        )
                        return ResponseFormatter.format_standard_text(
                            to_phone=customer_phone,
                            text=reply,
                            strategy=ResponseStrategy.CHECKOUT_CONVERGED,
                        )

                    elif tool_res.status == ToolStatus.OUT_OF_STOCK:
                        await NegotiationFrameManager.evict_frame(str(merchant_id), customer_phone)
                        prompt = tool_res.clarification.prompt_text if tool_res.clarification else "Sorry, out of stock."
                        buttons = tool_res.clarification.buttons if tool_res.clarification else None
                        if buttons and isinstance(buttons, list) and len(buttons) > 0:
                            return ResponseFormatter.format_interactive_buttons(
                                to_phone=customer_phone,
                                body_text=prompt,
                                buttons=buttons,
                                strategy=ResponseStrategy.OUT_OF_STOCK_ALERT,
                            )
                        return ResponseFormatter.format_standard_text(
                            to_phone=customer_phone,
                            text=prompt,
                            strategy=ResponseStrategy.OUT_OF_STOCK_ALERT,
                        )

        # 3. Action: SHOW_CATALOG / BROWSE_CATALOG / INTENT:SHOW_CATALOG
        if interactive_id in ["SHOW_CATALOG", "BROWSE_CATALOG", "INTENT:SHOW_CATALOG"]:
            active_frame = await NegotiationFrameManager.get_frame(str(merchant_id), customer_phone)
            if not active_frame:
                active_frame = NegotiationFrame(
                    merchant_id=str(merchant_id),
                    phone_hash="",
                    active_tool="ProductCatalog",
                    intent="SHOW_PRODUCT_CATALOG",
                    bound_slots={},
                    missing_slots=[],
                )
            else:
                active_frame.intent = "SHOW_PRODUCT_CATALOG"
            await NegotiationFrameManager.save_frame(str(merchant_id), customer_phone, active_frame)

            offerings = await KnowledgeService.search_catalog_offerings(
                merchant_id=merchant_id,
                query="",
                session=session,
            )
            return ResponseFormatter.format_interactive_list(
                to_phone=customer_phone,
                offerings=offerings,
                query_title="Catalog",
            )

        # 4. Action: AGENT_HANDOFF / SPEAK_TO_AGENT / INTENT:AGENT_HANDOFF
        if interactive_id in ["AGENT_HANDOFF", "SPEAK_TO_AGENT", "INTENT:AGENT_HANDOFF"]:
            active_frame = await NegotiationFrameManager.get_frame(str(merchant_id), customer_phone)
            if not active_frame:
                active_frame = NegotiationFrame(
                    merchant_id=str(merchant_id),
                    phone_hash="",
                    active_tool="DeskService",
                    intent="DISPATCH_AGENT_HANDOFF",
                    bound_slots={},
                    missing_slots=[],
                )
            else:
                active_frame.intent = "DISPATCH_AGENT_HANDOFF"
            await NegotiationFrameManager.save_frame(str(merchant_id), customer_phone, active_frame)

            return ResponseFormatter.format_standard_text(
                to_phone=customer_phone,
                text="A human agent will be with you shortly. Please hold on.",
                strategy=ResponseStrategy.AGENT_HANDOFF,
            )

        # Remove redundant fallback greeting: return helpful catalog options instead
        return ResponseFormatter.format_interactive_buttons(
            to_phone=customer_phone,
            body_text=f"We couldn't find that item in current stock for {merchant_name}. Please choose an option below:",
            buttons=[
                {"id": "SHOW_CATALOG", "title": "View Catalog"},
                {"id": "AGENT_HANDOFF", "title": "Speak to Agent"},
            ],
            strategy=ResponseStrategy.OUT_OF_STOCK_ALERT,
        )
