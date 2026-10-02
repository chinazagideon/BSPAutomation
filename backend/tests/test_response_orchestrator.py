"""Automated Tests for Response Orchestrator & WhatsApp Interactive Commerce (ADR-0044).

Covers:
- test_price_inquiry_multi_product_list: "how much is rice?" generates interactive_list envelope
- test_product_detail_tap_3_buttons: PRODUCT:sku renders 3-button card ([Order Now], [View Catalog], [Speak to Agent])
- test_catalog_miss_emits_event: Querying missing product emits CatalogMissDetectedEvent
- test_interactive_slot_binding_convergence: SET_SLOT:sku:... binds parameter in NegotiationFrame
"""

import pytest
from uuid import uuid4

from app.core.events import event_bus, CatalogMissDetectedEvent
from app.core.generation.response_classifier import ResponseStrategy
from app.core.generation.response_formatter import (
    EgressMessageType,
    EgressPayloadEnvelope,
)
from app.core.generation.response_orchestrator import ResponseOrchestrator
from app.core.generation.negotiation import NegotiationFrameManager


@pytest.mark.asyncio
async def test_price_inquiry_multi_product_list():
    """Validates that a price inquiry matching multiple items returns an interactive list envelope."""
    merchant_id = str(uuid4())
    customer_phone = "+2348011223344"
    nlu_result = {
        "intent": "PRICE_INQUIRY",
        "extracted_entities": {"product": "rice", "quantity": "1 bag"},
        "suggested_reply": "Here are our available rice options:",
    }

    envelope: EgressPayloadEnvelope = await ResponseOrchestrator.resolve(
        merchant_id=merchant_id,
        nlu_result=nlu_result,
        customer_phone=customer_phone,
        raw_message="how much is one bag of rice?",
    )

    assert envelope.strategy == ResponseStrategy.CATALOG_PRODUCT_LIST
    assert envelope.message_type == EgressMessageType.INTERACTIVE_LIST
    assert envelope.to_phone == customer_phone
    assert envelope.sections is not None
    assert len(envelope.sections) >= 1

    rows = envelope.sections[0]["rows"]
    row_ids = [r["id"] for r in rows]
    assert "PRODUCT:RICE_MAMA_GOLD_50KG" in row_ids
    assert "PRODUCT:RICE_ROYAL_STALLION_50KG" in row_ids


@pytest.mark.asyncio
async def test_product_detail_tap_3_buttons():
    """Validates tapping PRODUCT:{sku} renders a 3-button product detail card."""
    merchant_id = str(uuid4())
    customer_phone = "+2348011223344"
    interactive_id = "PRODUCT:RICE_MAMA_GOLD_50KG"

    envelope: EgressPayloadEnvelope = await ResponseOrchestrator.resolve_interactive_action(
        merchant_id=merchant_id,
        interactive_id=interactive_id,
        customer_phone=customer_phone,
    )

    assert envelope.strategy == ResponseStrategy.SINGLE_PRODUCT_QUOTE
    assert envelope.message_type == EgressMessageType.INTERACTIVE_BUTTONS
    assert "Mama Gold Rice 50kg" in envelope.body_text
    assert "78,000" in envelope.body_text

    assert envelope.buttons is not None
    assert len(envelope.buttons) == 3

    button_ids = [b["id"] for b in envelope.buttons]
    button_titles = [b["title"] for b in envelope.buttons]

    assert "SET_SLOT:sku:RICE_MAMA_GOLD_50KG" in button_ids
    assert "SHOW_CATALOG" in button_ids
    assert "AGENT_HANDOFF" in button_ids

    assert "Order Now" in button_titles
    assert "View Catalog" in button_titles
    assert "Speak to Agent" in button_titles


@pytest.mark.asyncio
async def test_catalog_miss_emits_event():
    """Validates querying an uncataloged item emits CatalogMissDetectedEvent and returns polite alert."""
    merchant_id = str(uuid4())
    customer_phone = "+2348099887766"
    unlisted_item = "solar inverter 5kva"

    emitted_events = []

    async def _on_miss(event: CatalogMissDetectedEvent):
        emitted_events.append(event)

    event_bus.subscribe("catalog.miss.detected", _on_miss)

    nlu_result = {
        "intent": "PRICE_INQUIRY",
        "extracted_entities": {"product": unlisted_item},
        "suggested_reply": "Checking our inventory...",
    }

    envelope: EgressPayloadEnvelope = await ResponseOrchestrator.resolve(
        merchant_id=merchant_id,
        nlu_result=nlu_result,
        customer_phone=customer_phone,
        raw_message=f"how much for {unlisted_item}?",
    )

    assert envelope.strategy == ResponseStrategy.CATALOG_MISS_ALERT
    assert unlisted_item in envelope.body_text

    # Assert domain event emission
    matching_events = [e for e in emitted_events if e.query_term == unlisted_item]
    assert len(matching_events) >= 1
    event = matching_events[0]
    assert event.customer_phone == customer_phone
    assert event.merchant_id == merchant_id


@pytest.mark.asyncio
async def test_interactive_slot_binding_convergence():
    """Validates tapping SET_SLOT:sku:{sku} updates Redis NegotiationFrame and triggers clarification."""
    merchant_id = str(uuid4())
    customer_phone = "+2348077665544"
    interactive_id = "SET_SLOT:sku:RICE_MAMA_GOLD_50KG"

    # Evict any existing frame first
    await NegotiationFrameManager.evict_frame(merchant_id, customer_phone)

    envelope: EgressPayloadEnvelope = await ResponseOrchestrator.resolve_interactive_action(
        merchant_id=merchant_id,
        interactive_id=interactive_id,
        customer_phone=customer_phone,
    )

    assert envelope.strategy == ResponseStrategy.SLOT_CLARIFICATION

    # Verify active negotiation frame in Redis
    frame = await NegotiationFrameManager.get_frame(merchant_id, customer_phone)
    assert frame is not None
    assert frame.bound_slots.get("sku") == "RICE_MAMA_GOLD_50KG"
    assert "quantity" in frame.missing_slots
