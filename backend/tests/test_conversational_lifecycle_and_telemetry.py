"""Automated Verification Suite for Grade-1 Footprint NLU Fixes and Structured Telemetry.

Covers:
1. test_stock_inquiry_fast_path_rice: "Do you have rice in store?" matches Stage 1 FastPath (0 tokens, ~2ms)
2. test_response_classifier_catalog_promotion: GENERAL_INQUIRY with matching catalog items promotes to CATALOG_PRODUCT_LIST
3. test_pending_offer_affirmation_resolution: "Yes" / "Oya" resolves pending offer via NegotiationFrame without LLM
4. test_pending_offer_negation_resolution: "No" / "Leave am" evicts pending offer politely
5. test_gemini_circuit_breaker_contextual_recovery: Transient 503 triggers contextual catalog fallback for known products
6. test_fast_path_regex_hardening: "prepaid" or "unpaid" does NOT trigger CONFIRM_PAYMENT
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.contexts.ingress.fast_path import fast_path_classify, extract_commercial_entities
from app.core.generation.response_classifier import ResponseClassifier, ResponseStrategy
from app.core.generation.response_formatter import EgressMessageType, EgressPayloadEnvelope
from app.core.generation.response_orchestrator import ResponseOrchestrator
from app.core.generation.negotiation import NegotiationFrameManager, NegotiationFrame
from app.adapters.llm import GeminiFlashAdapter


@pytest.mark.asyncio
async def test_stock_inquiry_fast_path_rice():
    """Validates that 'Do you have rice in store?' hits Stage 1 FastPath deterministically."""
    text = "Do you have rice in store?"
    res = fast_path_classify(text)

    assert res is not None
    assert res.intent == "PRICE_INQUIRY"
    assert res.action == "SHOW_PRODUCT_CATALOG"
    assert res.confidence >= 0.95
    assert res.tokens_consumed == 0
    assert res.extracted_entities.get("product") == "rice"


@pytest.mark.asyncio
async def test_pidgin_stock_inquiry_fast_path():
    """Validates that Nigerian Pidgin 'you get sugar?' hits Stage 1 FastPath."""
    text = "you get sugar?"
    res = fast_path_classify(text)

    assert res is not None
    assert res.intent == "PRICE_INQUIRY"
    assert res.extracted_entities.get("product") == "sugar"
    assert res.tokens_consumed == 0


@pytest.mark.asyncio
async def test_response_classifier_catalog_promotion():
    """Validates that an exploratory/general inquiry with catalog matches promotes to interactive list."""
    merchant_id = str(uuid4())
    customer_phone = "+2348011223344"

    # Even if intent came back as GENERAL_INQUIRY from an LLM fallback
    nlu_result = {
        "intent": "GENERAL_INQUIRY",
        "extracted_entities": {"product": "rice"},
        "suggested_reply": "Yes, we have rice in stock!",
    }

    strategy = ResponseClassifier.classify_strategy(
        intent="GENERAL_INQUIRY",
        entities={"product": "rice"},
        catalog_count=3,
    )
    assert strategy == ResponseStrategy.CATALOG_PRODUCT_LIST

    envelope: EgressPayloadEnvelope = await ResponseOrchestrator.resolve(
        merchant_id=merchant_id,
        nlu_result=nlu_result,
        customer_phone=customer_phone,
        raw_message="do you have rice?",
    )

    assert envelope.strategy == ResponseStrategy.CATALOG_PRODUCT_LIST
    assert envelope.message_type == EgressMessageType.INTERACTIVE_LIST
    assert envelope.sections is not None
    assert len(envelope.sections[0]["rows"]) >= 2


@pytest.mark.asyncio
async def test_pending_offer_affirmation_resolution():
    """Validates deterministic affirmation ('Yes', 'Oya', 'Sure') matching."""
    assert NegotiationFrameManager.is_affirmation_intent("Yes") is True
    assert NegotiationFrameManager.is_affirmation_intent("yes please") is True
    assert NegotiationFrameManager.is_affirmation_intent("oya") is True
    assert NegotiationFrameManager.is_affirmation_intent("sure") is True
    assert NegotiationFrameManager.is_affirmation_intent("sharp sharp") is True
    assert NegotiationFrameManager.is_affirmation_intent("send am") is True

    # Negative affirmations
    assert NegotiationFrameManager.is_affirmation_intent("no") is False
    assert NegotiationFrameManager.is_affirmation_intent("how much") is False


@pytest.mark.asyncio
async def test_pending_offer_negation_resolution():
    """Validates deterministic negation ('No', 'Leave am', 'Never mind') matching."""
    assert NegotiationFrameManager.is_negation_intent("No") is True
    assert NegotiationFrameManager.is_negation_intent("leave am") is True
    assert NegotiationFrameManager.is_negation_intent("never mind") is True
    assert NegotiationFrameManager.is_negation_intent("i no want") is True
    assert NegotiationFrameManager.is_negation_intent("cancel") is True

    # Negative rejections
    assert NegotiationFrameManager.is_negation_intent("yes") is False
    assert NegotiationFrameManager.is_negation_intent("ok") is False


@pytest.mark.asyncio
async def test_fast_path_regex_hardening():
    """Validates that 'unpaid' or 'prepaid' does NOT trigger CONFIRM_PAYMENT."""
    text_prepaid = "This is a prepaid meter inquiry"
    res_prepaid = fast_path_classify(text_prepaid)
    assert res_prepaid is None or res_prepaid.intent != "CONFIRM_PAYMENT"

    text_paid = "I have paid into your account"
    res_paid = fast_path_classify(text_paid)
    assert res_paid is not None
    assert res_paid.intent == "CONFIRM_PAYMENT"


@pytest.mark.asyncio
async def test_gemini_circuit_breaker_contextual_recovery():
    """Validates that Gemini transient failure degrades contextually to catalog rather than abrupt handoff."""
    adapter = GeminiFlashAdapter(api_key="mock_key")
    # Simulate a 503 error on client call
    adapter._client = MagicMock()
    adapter._client.aio.models.generate_content = AsyncMock(
        side_effect=Exception("503 UNAVAILABLE. Model experiencing high demand")
    )

    fallback = await adapter.generate_chat_completion(
        prompt="Customer Message: Do you have rice available?",
        system_instruction="Analyze customer intent",
    )

    assert fallback is not None
    # Contextual recovery extracts "rice" and routes to SHOW_PRODUCT_CATALOG
    assert fallback.intent == "PRICE_INQUIRY"
    assert fallback.action == "SHOW_PRODUCT_CATALOG"
    assert fallback.extracted_entities.get("product") == "rice"
    assert fallback.extracted_entities.get("error_fallback") is True
    assert fallback.tokens_consumed == 0


@pytest.mark.asyncio
async def test_order_now_button_tap_promotes_intent_and_triggers_quantity_clarification():
    """Validates that tapping 'Order Now' (SET_SLOT:sku:...) promotes frame intent from PRICE_INQUIRY to INSTANT_CHECKOUT_ORDER."""
    merchant_id = str(uuid4())
    customer_phone = "+2348031234567"

    # Frame created earlier in conversation with PRICE_INQUIRY
    initial_frame = NegotiationFrame(
        merchant_id=merchant_id,
        phone_hash="",
        active_tool="ProductCatalog",
        intent="PRICE_INQUIRY",
        bound_slots={},
        missing_slots=[],
    )
    await NegotiationFrameManager.save_frame(merchant_id, customer_phone, initial_frame)

    # Customer taps "Order Now" on Mama Gold Rice 25kg
    interactive_id = "SET_SLOT:sku:RICE_MAMA_GOLD_25KG"
    envelope = await ResponseOrchestrator.resolve_interactive_action(
        merchant_id=merchant_id,
        interactive_id=interactive_id,
        customer_phone=customer_phone,
    )

    assert envelope is not None
    assert envelope.strategy == ResponseStrategy.SLOT_CLARIFICATION
    assert envelope.message_type == EgressMessageType.INTERACTIVE_BUTTONS
    assert "Mama Gold Rice 25kg" in envelope.body_text
    assert envelope.buttons is not None
    assert len(envelope.buttons) == 3
    assert envelope.buttons[0]["id"] == "SET_SLOT:quantity:1"
    assert envelope.buttons[1]["id"] == "SET_SLOT:quantity:2"
    assert envelope.buttons[2]["id"] == "SET_SLOT:quantity:5"

    # Verify frame in Redis is updated with INSTANT_CHECKOUT_ORDER
    updated_frame = await NegotiationFrameManager.get_frame(merchant_id, customer_phone)
    assert updated_frame is not None
    assert updated_frame.intent == "INSTANT_CHECKOUT_ORDER"
    assert updated_frame.active_tool == "CheckoutOrderTool"
    assert updated_frame.bound_slots.get("sku") == "RICE_MAMA_GOLD_25KG"
    assert "quantity" in updated_frame.missing_slots


@pytest.mark.asyncio
async def test_interactive_multi_turn_checkout_convergence():
    """Validates entire multi-turn deterministic checkout convergence via interactive buttons (0 tokens)."""
    merchant_id = str(uuid4())
    customer_phone = "+2348099887766"

    # Turn 1: Tap Order Now on 25kg rice
    env1 = await ResponseOrchestrator.resolve_interactive_action(
        merchant_id=merchant_id,
        interactive_id="SET_SLOT:sku:RICE_MAMA_GOLD_25KG",
        customer_phone=customer_phone,
    )
    assert env1.strategy == ResponseStrategy.SLOT_CLARIFICATION

    # Turn 2: Tap 2 Bags
    env2 = await ResponseOrchestrator.resolve_interactive_action(
        merchant_id=merchant_id,
        interactive_id="SET_SLOT:quantity:2",
        customer_phone=customer_phone,
    )
    assert env2.strategy == ResponseStrategy.SLOT_CLARIFICATION
    assert env2.buttons[0]["id"] == "SET_SLOT:fulfillment_type:EXPRESS_DELIVERY"
    assert env2.buttons[1]["id"] == "SET_SLOT:fulfillment_type:WAREHOUSE_PICKUP"

    # Turn 3: Tap Warehouse Self-Pickup
    env3 = await ResponseOrchestrator.resolve_interactive_action(
        merchant_id=merchant_id,
        interactive_id="SET_SLOT:fulfillment_type:WAREHOUSE_PICKUP",
        customer_phone=customer_phone,
    )
    assert env3.strategy == ResponseStrategy.CHECKOUT_CONVERGED
    # 2 bags @ ₦41,000 = ₦82,000
    assert "₦82,000" in env3.body_text
    assert "warehouse self-pickup" in env3.body_text
    assert "Moniepoint MFB" in env3.body_text

    # Verify frame is evicted upon convergence
    frame_after = await NegotiationFrameManager.get_frame(merchant_id, customer_phone)
    assert frame_after is None


@pytest.mark.asyncio
async def test_show_catalog_and_agent_handoff_interactive_actions():
    """Validates that SHOW_CATALOG and AGENT_HANDOFF buttons update intent and return proper structures."""
    merchant_id = str(uuid4())
    customer_phone = "+2348077665544"

    # Test SHOW_CATALOG
    env_cat = await ResponseOrchestrator.resolve_interactive_action(
        merchant_id=merchant_id,
        interactive_id="SHOW_CATALOG",
        customer_phone=customer_phone,
    )
    assert env_cat.strategy == ResponseStrategy.CATALOG_PRODUCT_LIST
    assert env_cat.message_type == EgressMessageType.INTERACTIVE_LIST

    frame_cat = await NegotiationFrameManager.get_frame(merchant_id, customer_phone)
    assert frame_cat is not None
    assert frame_cat.intent == "SHOW_PRODUCT_CATALOG"

    # Test AGENT_HANDOFF
    env_agent = await ResponseOrchestrator.resolve_interactive_action(
        merchant_id=merchant_id,
        interactive_id="AGENT_HANDOFF",
        customer_phone=customer_phone,
    )
    assert env_agent.strategy == ResponseStrategy.AGENT_HANDOFF
    assert "human agent will be with you shortly" in env_agent.body_text

    frame_agent = await NegotiationFrameManager.get_frame(merchant_id, customer_phone)
    assert frame_agent is not None
    assert frame_agent.intent == "DISPATCH_AGENT_HANDOFF"


@pytest.mark.asyncio
async def test_out_of_stock_item_detail_card_suppresses_order_now():
    """Validates that out-of-stock items do not offer Order Now and instead offer View Catalog / Speak to Agent."""
    from app.core.generation.response_formatter import ResponseFormatter
    from app.contexts.knowledge.offering_schemas import CoreOfferingDTO, OfferingType

    oos_item = CoreOfferingDTO(
        sku="FLOUR_GOLDEN_PENNY_50KG",
        title="Golden Penny Flour 50kg",
        description="All-purpose premium baking flour for bakeries, 50kg bag. (Currently sold out).",
        category="flour",
        price_kobo=6200000,
        price_naira=62000.0,
        currency="NGN",
        is_available=False,
        offering_type=OfferingType.PHYSICAL_PRODUCT,
    )

    card = ResponseFormatter.format_product_detail_card(
        to_phone="+2348011223344",
        offering=oos_item,
    )

    assert card.strategy == ResponseStrategy.OUT_OF_STOCK_ALERT
    assert "Out of Stock" in card.body_text
    # Order Now button must NOT be present
    button_titles = [b["title"] for b in card.buttons]
    button_ids = [b["id"] for b in card.buttons]
    assert "Order Now" not in button_titles
    assert not any(bid.startswith("SET_SLOT:sku:") for bid in button_ids)
    assert "SHOW_CATALOG" in button_ids
    assert "AGENT_HANDOFF" in button_ids


@pytest.mark.asyncio
async def test_out_of_stock_order_now_slot_binding_triggers_out_of_stock_alert():
    """Validates that tapping Order Now for an out-of-stock SKU deterministically responds with OUT_OF_STOCK_ALERT."""
    merchant_id = "018f6c5a-8b1e-7230-a890-111111111111"
    customer_phone = "+2348130406877"

    env = await ResponseOrchestrator.resolve_interactive_action(
        merchant_id=merchant_id,
        interactive_id="SET_SLOT:sku:FLOUR_GOLDEN_PENNY_50KG",
        customer_phone=customer_phone,
    )

    assert env.strategy == ResponseStrategy.OUT_OF_STOCK_ALERT
    assert "out of stock" in env.body_text.lower()
    button_ids = [b["id"] for b in env.buttons]
    assert "SHOW_CATALOG" in button_ids
    assert "AGENT_HANDOFF" in button_ids

    # Frame should be evicted so customer isn't trapped in checkout
    frame = await NegotiationFrameManager.get_frame(merchant_id, customer_phone)
    assert frame is None

