"""Test Suite for Unresolved Intent Disambiguation, Order Tracking, and Suspended Cart Preservation (ADR-0048)."""

import pytest
from app.adapters.providers.spacy_nlu_engine import get_spacy_nlu_engine
from app.core.generation.response_classifier import ResponseClassifier, ResponseStrategy
from app.core.generation.response_formatter import (
    EgressMessageType,
    ResponseFormatter,
)
from app.core.generation.response_orchestrator import ResponseOrchestrator
from app.core.generation.order_ledger import CustomerOrderLedger
from app.core.generation.fsm import ConversationFSMService, FSMTransitionType
from app.core.generation.negotiation import NegotiationFrame, NegotiationFrameManager


MERCHANT_ID = "018f6c5a-8b1e-7230-a890-111111111111"
CUSTOMER_PHONE = "+2348031234567"


@pytest.mark.asyncio
async def test_order_status_inquiry_nlu_classification():
    """Verifies 'when is my order going to arrive?' classifies as ORDER_STATUS_INQUIRY with high confidence."""
    engine = get_spacy_nlu_engine()

    test_queries = [
        "when is my order going to arrive?",
        "where is my order?",
        "track my order",
        "order status",
        "when will my delivery arrive",
        "where my delivery dey",
        "wetin happen to my order",
    ]

    for q in test_queries:
        parsed = engine.predict_intent_and_slots(q)
        assert parsed.intent == "ORDER_STATUS_INQUIRY", f"Failed for query: {q}"
        assert parsed.confidence >= 0.90, f"Low confidence for query: {q}"
        assert parsed.lead_tier == "HOT"


@pytest.mark.asyncio
async def test_response_classifier_does_not_bias_to_catalog_on_order_status():
    """Verifies ResponseClassifier routes ORDER_STATUS_INQUIRY to ORDER_STATUS_CARD, never CATALOG_PRODUCT_LIST."""
    # Even if product entity was somehow present, order status intent MUST override
    strategy = ResponseClassifier.classify_strategy(
        intent="ORDER_STATUS_INQUIRY",
        entities={"product": "rice"},
        catalog_count=3,
    )
    assert strategy == ResponseStrategy.ORDER_STATUS_CARD

    # Unresolved intent routes to UNRESOLVED_DISAMBIGUATION, never catalog
    unresolved_strat = ResponseClassifier.classify_strategy(
        intent="UNRESOLVED_GENERAL_QUERY",
        entities={},
        catalog_count=5,
    )
    assert unresolved_strat == ResponseStrategy.UNRESOLVED_DISAMBIGUATION


@pytest.mark.asyncio
async def test_unresolved_query_returns_disambiguation_menu():
    """Verifies ambiguous queries without an active cart return 3-button Disambiguation Card."""
    await NegotiationFrameManager.evict_frame(MERCHANT_ID, CUSTOMER_PHONE)

    nlu_fake = {
        "intent": "UNRESOLVED_GENERAL_QUERY",
        "extracted_entities": {},
        "suggested_reply": "How can I help you?",
    }
    envelope = await ResponseOrchestrator.resolve(
        merchant_id=MERCHANT_ID,
        nlu_result=nlu_fake,
        customer_phone=CUSTOMER_PHONE,
        raw_message="tell me about everything",
    )

    assert envelope.strategy == ResponseStrategy.UNRESOLVED_DISAMBIGUATION
    assert envelope.message_type == EgressMessageType.INTERACTIVE_BUTTONS
    assert len(envelope.buttons) == 3
    assert envelope.buttons[0]["id"] == "NAV:BROWSE_CATALOG"
    assert envelope.buttons[1]["id"] == "NAV:TRACK_ORDER"
    assert envelope.buttons[2]["id"] == "NAV:AGENT_HANDOFF"


@pytest.mark.asyncio
async def test_unresolved_query_with_active_cart_offers_resume_order():
    """Verifies ambiguous queries with a suspended cart dynamically offer [Resume Order]."""
    stack = await NegotiationFrameManager.load_stack(MERCHANT_ID, CUSTOMER_PHONE)
    cart_frame = NegotiationFrame(
        merchant_id=MERCHANT_ID,
        active_tool="CheckoutOrderTool",
        intent="INSTANT_CHECKOUT_ORDER",
        node_type="TRANSACTIONAL",
        bound_slots={"sku": "RICE_MAMA_GOLD_50KG", "product_name": "Mama Gold Rice 50kg", "quantity": 2},
        missing_slots=["delivery_zone"],
    )
    stack.push(cart_frame)
    await NegotiationFrameManager.save_stack(MERCHANT_ID, CUSTOMER_PHONE, stack)

    nlu_fake = {
        "intent": "UNRESOLVED_GENERAL_QUERY",
        "extracted_entities": {},
        "suggested_reply": "I didn't quite catch that.",
    }
    envelope = await ResponseOrchestrator.resolve(
        merchant_id=MERCHANT_ID,
        nlu_result=nlu_fake,
        customer_phone=CUSTOMER_PHONE,
        raw_message="random out of context text",
    )

    assert envelope.strategy == ResponseStrategy.UNRESOLVED_DISAMBIGUATION
    assert envelope.buttons[0]["id"] == "NAV:RESUME_CART"
    assert envelope.buttons[0]["title"] == "Resume Order"
    assert "pending order" in envelope.body_text.lower()


@pytest.mark.asyncio
async def test_order_status_lookup_without_orders():
    """Verifies that an order inquiry when 0 orders exist prompts for reference without showing rice catalog."""
    await NegotiationFrameManager.evict_frame(MERCHANT_ID, "+2348000000099")

    nlu_fake = {
        "intent": "ORDER_STATUS_INQUIRY",
        "extracted_entities": {},
        "suggested_reply": "",
    }
    envelope = await ResponseOrchestrator.resolve(
        merchant_id=MERCHANT_ID,
        nlu_result=nlu_fake,
        customer_phone="+2348000000099",
        raw_message="when is my order going to arrive?",
    )

    assert envelope.strategy == ResponseStrategy.ORDER_STATUS_CARD
    assert "couldn't find any recent orders" in envelope.body_text
    assert "Rice Catalog" not in (envelope.header_text or "")
    assert envelope.buttons[1]["id"] == "NAV:AGENT_HANDOFF"


@pytest.mark.asyncio
async def test_order_status_lookup_with_existing_order():
    """Verifies that an order inquiry when an order exists returns live dispatch details."""
    phone = "+2348039988776"
    await CustomerOrderLedger.record_order(
        merchant_id=MERCHANT_ID,
        customer_phone=phone,
        bound_slots={
            "product_name": "Mama Gold Rice 50kg",
            "quantity": 1,
            "delivery_zone": "Ikeja / Mainland, Lagos",
        },
        total_kobo=7800000,
    )

    nlu_fake = {
        "intent": "ORDER_STATUS_INQUIRY",
        "extracted_entities": {},
        "suggested_reply": "",
    }
    envelope = await ResponseOrchestrator.resolve(
        merchant_id=MERCHANT_ID,
        nlu_result=nlu_fake,
        customer_phone=phone,
        raw_message="when is my order going to arrive?",
    )

    assert envelope.strategy == ResponseStrategy.ORDER_STATUS_CARD
    assert "Dispatched / In Transit" in envelope.body_text
    assert "Mama Gold Rice 50kg" in envelope.body_text
    assert "Ikeja" in envelope.body_text
    assert "Rice Catalog" not in (envelope.header_text or "")


@pytest.mark.asyncio
async def test_out_of_flow_inquiry_with_suspended_cart_returns_compound_response():
    """Verifies out-of-flow inquiry answers the question and resumes the pending cart compoundly."""
    phone = "+2348099881122"
    # 1. Place an earlier order so order tracking succeeds
    await CustomerOrderLedger.record_order(
        merchant_id=MERCHANT_ID,
        customer_phone=phone,
        bound_slots={"product_name": "Dangote Sugar 50kg", "quantity": 1, "delivery_zone": "Lekki"},
        total_kobo=8400000,
    )

    # 2. Start a new checkout cart on the stack
    stack = await NegotiationFrameManager.load_stack(MERCHANT_ID, phone)
    active_cart = NegotiationFrame(
        merchant_id=MERCHANT_ID,
        active_tool="CheckoutOrderTool",
        intent="INSTANT_CHECKOUT_ORDER",
        node_type="TRANSACTIONAL",
        bound_slots={"sku": "RICE_MAMA_GOLD_50KG", "product_name": "Mama Gold Rice 50kg", "quantity": 2},
        missing_slots=["delivery_zone"],
    )
    stack.push(active_cart)
    await NegotiationFrameManager.save_stack(MERCHANT_ID, phone, stack)

    # 3. Customer sends out-of-flow status query
    outcome = await ConversationFSMService.process_turn(
        merchant_id=MERCHANT_ID,
        customer_phone=phone,
        customer_name="Emeka",
        sanitized_text="when is my order going to arrive?",
    )

    # 4. Verify compound response
    assert outcome.intent == "ORDER_STATUS_INQUIRY"
    assert outcome.envelope.strategy == ResponseStrategy.ORDER_STATUS_CARD
    # Part 1: Order status answer
    assert "Dispatched / In Transit" in outcome.envelope.body_text
    assert "Dangote Sugar" in outcome.envelope.body_text
    # Part 2: Continuing reservation prompt
    assert "Continuing your reservation for" in outcome.envelope.body_text
    assert "Mama Gold Rice" in outcome.envelope.body_text

    # 5. Verify stack is preserved (NOT evicted)
    persisted_stack = await NegotiationFrameManager.load_stack(MERCHANT_ID, phone)
    top = persisted_stack.peek()
    assert top is not None
    assert top.intent == "INSTANT_CHECKOUT_ORDER"
    assert top.bound_slots["sku"] == "RICE_MAMA_GOLD_50KG"


@pytest.mark.asyncio
async def test_nav_interactive_protocol_dispatches():
    """Verifies NAV:* callbacks dispatch with 0 tokens and correct strategies."""
    # NAV:BROWSE_CATALOG
    env_cat = await ConversationFSMService.dispatch_interactive_protocol(
        merchant_id=MERCHANT_ID,
        interactive_id="NAV:BROWSE_CATALOG",
        customer_phone=CUSTOMER_PHONE,
    )
    assert env_cat.strategy == ResponseStrategy.CATALOG_PRODUCT_LIST

    # NAV:TRACK_ORDER
    env_track = await ConversationFSMService.dispatch_interactive_protocol(
        merchant_id=MERCHANT_ID,
        interactive_id="NAV:TRACK_ORDER",
        customer_phone=CUSTOMER_PHONE,
    )
    assert env_track.strategy == ResponseStrategy.ORDER_STATUS_CARD

    # NAV:AGENT_HANDOFF
    env_agent = await ConversationFSMService.dispatch_interactive_protocol(
        merchant_id=MERCHANT_ID,
        interactive_id="NAV:AGENT_HANDOFF",
        customer_phone=CUSTOMER_PHONE,
    )
    assert env_agent.strategy == ResponseStrategy.AGENT_HANDOFF
