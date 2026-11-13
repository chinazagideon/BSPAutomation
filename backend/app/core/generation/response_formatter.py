"""WhatsApp Response Formatter & Egress Envelopes (ADR-0044).

Functional translation from ResponseStrategy to channel-compliant Meta WhatsApp UI structures:
- Interactive List (up to 10 clickable items with PRODUCT:{sku} callbacks)
- 3-Button Product Detail Card with live Naira pricing ([Order Now], [View Catalog], [Speak to Agent])
- Contextual Text / Catalog Miss Alerts
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from app.contexts.knowledge.offering_schemas import CoreOfferingDTO
from app.core.generation.response_classifier import ResponseStrategy


class EgressMessageType(str, Enum):
    TEXT = "text"
    INTERACTIVE_BUTTONS = "interactive_buttons"
    INTERACTIVE_LIST = "interactive_list"


class EgressPayloadEnvelope(BaseModel):
    """Channel-compliant payload envelope dispatched to WhatsApp BSP egress gateway."""
    message_type: EgressMessageType
    to_phone: str
    body_text: str
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    button_title: Optional[str] = None
    buttons: Optional[List[Dict[str, str]]] = None
    sections: Optional[List[Dict[str, Any]]] = None
    strategy: ResponseStrategy
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ResponseFormatter:
    """Functional envelope formatter producing Meta WhatsApp UI structures."""

    @staticmethod
    def format_interactive_list(
        to_phone: str,
        offerings: List[CoreOfferingDTO],
        query_title: str = "Catalog",
    ) -> EgressPayloadEnvelope:
        """Formats WhatsApp Interactive List (max 10 rows) with PRODUCT:{sku} action IDs."""
        rows = []
        for item in offerings[:10]:
            price_str = f"₦{item.price_naira:,.0f}"
            desc = f"{price_str} • {item.category.title()}"
            if not item.is_available:
                desc += " (Out of Stock)"
            rows.append({
                "id": f"PRODUCT:{item.sku}",
                "title": item.title[:24],
                "description": desc[:72],
            })

        sections = [{"title": "Available Products", "rows": rows}]
        count_str = f"{len(offerings)} option{'s' if len(offerings) != 1 else ''}"
        header = f"{query_title} ({count_str})"[:60]
        body = "Select an item below to view live pricing and place your order:"

        return EgressPayloadEnvelope(
            message_type=EgressMessageType.INTERACTIVE_LIST,
            to_phone=to_phone,
            header_text=header,
            body_text=body,
            button_title="View Options"[:20],
            sections=sections,
            strategy=ResponseStrategy.CATALOG_PRODUCT_LIST,
            metadata={"product_count": len(offerings)},
        )

    @staticmethod
    def format_product_detail_card(
        to_phone: str,
        offering: CoreOfferingDTO,
    ) -> EgressPayloadEnvelope:
        """Formats 3-button product detail card with live Naira price and dual action IDs."""
        stock_status = "In Stock" if offering.is_available else "Out of Stock"
        if offering.is_available:
            call_to_action = "Tap *Order Now* to proceed with checkout."
            buttons = [
                {"id": f"SET_SLOT:sku:{offering.sku}", "title": "Order Now"},
                {"id": "SHOW_CATALOG", "title": "View Catalog"},
                {"id": "AGENT_HANDOFF", "title": "Speak to Agent"},
            ]
            strategy = ResponseStrategy.SINGLE_PRODUCT_QUOTE
        else:
            call_to_action = "⚠️ This item is currently *Out of Stock*. You fit browse our available catalog or speak with our team below."
            buttons = [
                {"id": "SHOW_CATALOG", "title": "View Catalog"},
                {"id": "AGENT_HANDOFF", "title": "Speak to Agent"},
            ]
            strategy = ResponseStrategy.OUT_OF_STOCK_ALERT

        body = (
            f"📦 *{offering.title}*\n"
            f"Price: *₦{offering.price_naira:,.2f}*\n"
            f"Category: {offering.category.title()} | Availability: {stock_status}\n\n"
            f"{offering.description}\n\n"
            f"{call_to_action}"
        )

        return EgressPayloadEnvelope(
            message_type=EgressMessageType.INTERACTIVE_BUTTONS,
            to_phone=to_phone,
            body_text=body,
            buttons=buttons,
            strategy=strategy,
            metadata={"sku": offering.sku, "price_kobo": offering.price_kobo, "is_available": offering.is_available},
        )

    @staticmethod
    def format_catalog_miss(
        to_phone: str,
        query_term: str,
        merchant_name: str = "our store",
    ) -> EgressPayloadEnvelope:
        """Formats polite catalog miss notification with buttons to browse or speak with support."""
        body = (
            f"Sorry, we could not find *{query_term}* in the catalog for {merchant_name}.\n\n"
            f"You fit browse our available items or speak directly with our team below."
        )

        buttons = [
            {"id": "SHOW_CATALOG", "title": "View Catalog"},
            {"id": "AGENT_HANDOFF", "title": "Speak to Agent"},
        ]

        return EgressPayloadEnvelope(
            message_type=EgressMessageType.INTERACTIVE_BUTTONS,
            to_phone=to_phone,
            body_text=body,
            buttons=buttons,
            strategy=ResponseStrategy.CATALOG_MISS_ALERT,
            metadata={"missing_query": query_term},
        )

    @staticmethod
    def format_standard_text(
        to_phone: str,
        text: str,
        strategy: ResponseStrategy = ResponseStrategy.STANDARD_TEXT,
    ) -> EgressPayloadEnvelope:
        """Formats standard plain text message."""
        return EgressPayloadEnvelope(
            message_type=EgressMessageType.TEXT,
            to_phone=to_phone,
            body_text=text,
            strategy=strategy,
        )

    @staticmethod
    def format_interactive_buttons(
        to_phone: str,
        body_text: str,
        buttons: List[Dict[str, str]],
        strategy: ResponseStrategy = ResponseStrategy.SLOT_CLARIFICATION,
    ) -> EgressPayloadEnvelope:
        """Formats interactive buttons message (e.g. slot clarification)."""
        return EgressPayloadEnvelope(
            message_type=EgressMessageType.INTERACTIVE_BUTTONS,
            to_phone=to_phone,
            body_text=body_text,
            buttons=buttons[:3],
            strategy=strategy,
        )

    @staticmethod
    def format_unresolved_disambiguation(
        to_phone: str,
        has_active_cart: bool = False,
        cart_summary: Optional[str] = None,
        merchant_name: str = "Enterprise SME Store",
    ) -> EgressPayloadEnvelope:
        """Formats 3-button neutral disambiguation menu (ADR-0048)."""
        if has_active_cart:
            cart_text = f"We notice you have a pending order for *{cart_summary or 'items'}*.\n\n"
            body = (
                f"{cart_text}How would you like to proceed with {merchant_name}?"
            )
            buttons = [
                {"id": "NAV:RESUME_CART", "title": "Resume Order"},
                {"id": "NAV:TRACK_ORDER", "title": "Track Order"},
                {"id": "NAV:AGENT_HANDOFF", "title": "Speak to Agent"},
            ]
        else:
            body = f"Welcome to {merchant_name}! How can we best help you today?"
            buttons = [
                {"id": "NAV:BROWSE_CATALOG", "title": "Browse Catalog"},
                {"id": "NAV:TRACK_ORDER", "title": "Track Order"},
                {"id": "NAV:AGENT_HANDOFF", "title": "Speak to Agent"},
            ]

        return EgressPayloadEnvelope(
            message_type=EgressMessageType.INTERACTIVE_BUTTONS,
            to_phone=to_phone,
            body_text=body,
            buttons=buttons,
            strategy=ResponseStrategy.UNRESOLVED_DISAMBIGUATION,
            metadata={"has_active_cart": has_active_cart},
        )

    @staticmethod
    def format_order_status_card(
        to_phone: str,
        order: Optional[Any] = None,
        multiple_orders: Optional[List[Any]] = None,
        merchant_name: str = "Enterprise SME Store",
    ) -> EgressPayloadEnvelope:
        """Formats post-purchase order tracking update (ADR-0048)."""
        if multiple_orders and len(multiple_orders) > 1:
            rows = []
            for ord_item in multiple_orders[:10]:
                created_str = (
                    datetime.fromtimestamp(ord_item.created_at).strftime("%d %b")
                    if getattr(ord_item, "created_at", None)
                    else "Recent"
                )
                zone = getattr(ord_item, "delivery_zone", None) or "Direct"
                ord_id = str(getattr(ord_item, "id", "") or "")
                rows.append({
                    "id": f"ORDER_SELECT:{ord_id}",
                    "title": f"Order #{ord_id[:8]}",
                    "description": f"{ord_item.order_summary[:40]} • {created_str} • {zone}"[:72],
                })
            sections = [{"title": "Recent Orders", "rows": rows}]
            return EgressPayloadEnvelope(
                message_type=EgressMessageType.INTERACTIVE_LIST,
                to_phone=to_phone,
                header_text=f"Select an Order ({len(multiple_orders)} found)"[:60],
                body_text="Tap an order below to check its live dispatch and arrival status:",
                button_title="View Orders"[:20],
                sections=sections,
                strategy=ResponseStrategy.ORDER_STATUS_CARD,
                metadata={"order_count": len(multiple_orders)},
            )

        if not order:
            body = (
                f"We couldn't find any recent orders associated with your WhatsApp number for {merchant_name}.\n\n"
                f"If you placed your order under another phone number, please reply with your *Order Reference ID* (e.g. #1042) or connect with a support agent below."
            )
            buttons = [
                {"id": "NAV:BROWSE_CATALOG", "title": "Browse Catalog"},
                {"id": "NAV:AGENT_HANDOFF", "title": "Speak to Agent"},
            ]
            return EgressPayloadEnvelope(
                message_type=EgressMessageType.INTERACTIVE_BUTTONS,
                to_phone=to_phone,
                body_text=body,
                buttons=buttons,
                strategy=ResponseStrategy.ORDER_STATUS_CARD,
                metadata={"found": False},
            )

        ord_id = str(getattr(order, "id", "") or "")
        short_id = f" (#{ord_id[:8]})" if ord_id else ""
        zone_info = f"Destination: *{order.delivery_zone}*\n" if getattr(order, "delivery_zone", None) else ""
        total_naira = f"₦{order.total_kobo // 100:,}" if getattr(order, "total_kobo", 0) else "Confirmed"
        created_dt = (
            datetime.fromtimestamp(order.created_at).strftime("%d %b %Y, %I:%M %p")
            if getattr(order, "created_at", None)
            else "Today"
        )

        body = (
            f"📦 *Order Status Update{short_id}*\n"
            f"Status: *Dispatched / In Transit* 🚚\n"
            f"Item: *{order.order_summary}*\n"
            f"{zone_info}"
            f"Amount: *{total_naira}*\n"
            f"Ordered: {created_dt}\n\n"
            f"Your order is on the way! Our dispatch rider will contact your WhatsApp line upon arrival."
        )
        buttons = [
            {"id": "NAV:BROWSE_CATALOG", "title": "Browse Catalog"},
            {"id": "NAV:AGENT_HANDOFF", "title": "Speak to Agent"},
        ]
        return EgressPayloadEnvelope(
            message_type=EgressMessageType.INTERACTIVE_BUTTONS,
            to_phone=to_phone,
            body_text=body,
            buttons=buttons,
            strategy=ResponseStrategy.ORDER_STATUS_CARD,
            metadata={"order_id": ord_id, "found": True},
        )

    @staticmethod
    def format_compound_response(
        to_phone: str,
        answer_text: str,
        resumption_prompt: str,
        buttons: Optional[List[Dict[str, str]]] = None,
        strategy: ResponseStrategy = ResponseStrategy.SLOT_CLARIFICATION,
    ) -> EgressPayloadEnvelope:
        """Formats compound response: Part 1 (Answer) + Part 2 (Cart resumption prompt) (ADR-0048)."""
        body = (
            f"{answer_text.strip()}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{resumption_prompt.strip()}"
        )
        if buttons:
            return EgressPayloadEnvelope(
                message_type=EgressMessageType.INTERACTIVE_BUTTONS,
                to_phone=to_phone,
                body_text=body,
                buttons=buttons[:3],
                strategy=strategy,
            )
        return EgressPayloadEnvelope(
            message_type=EgressMessageType.TEXT,
            to_phone=to_phone,
            body_text=body,
            strategy=strategy,
        )
