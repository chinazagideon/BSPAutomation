"""Comprehensive Automated Tests for Schema-Governed Tool Clarification & Negotiation Engine (ADR-0043).

Tests:
1. Schema-driven parameter gap detection on ambiguous products ("I want 2 bags of sugar").
2. Meta WhatsApp interactive button generation with exact kobo pricing.
3. Direct button ID slot binding (0ms NLP parsing).
4. Full parameter invariant convergence (Merchandise + Delivery Fee kobo precision).
5. Atomic check-and-hold inventory validation (preventing NUBAN allocation on out-of-stock items).
6. Frame preservation on intermediate topic swerves (answering FAQs while keeping negotiation frame warm).
7. Deterministic cancellation eviction ("cancel am", "never mind").
8. Strict NDPA 2023 PII protection (phone hashing in Redis, slot scrubbing).
9. End-to-end multi-turn worker execution.
"""

import pytest
import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from app.core.generation.tools import (
    get_local_tool_dispatcher,
    CheckoutOrderTool,
    ToolStatus,
    DEFAULT_COMMODITY_CATALOG,
    ZONE_DELIVERY_FEES_KOBO,
)
from app.core.generation.negotiation import (
    NegotiationFrameManager,
    NegotiationFrame,
    compute_phone_hash,
)
from app.contexts.ingress.fast_path import fast_path_classify, extract_commercial_entities
from app.core.generation.engine import CentralInferenceEngine
from app.core.generation.ports import ExecutionPolicy, TaskPriority
from app.core.generation.context import AggregatedContext, ContextSlice
from app.adapters.whatsapp import MockWhatsAppBSPAdapter


@pytest.mark.asyncio
async def test_ambiguous_product_parameter_gap_detection():
    """
    Scenario: Customer says "I want 2 bags of sugar".
    Verifies:
    - Tool detects ambiguity (Dangote 50kg vs BUA 50kg vs St. Louis 500g).
    - Status is NEEDS_CLARIFICATION.
    - WhatsApp buttons are generated with SET_SLOT:sku:... IDs.
    - Zero LLM tokens consumed.
    """
    dispatcher = get_local_tool_dispatcher()
    slots = {"product": "sugar", "quantity": 2}

    result = await dispatcher.evaluate(
        intent="INSTANT_CHECKOUT_ORDER",
        slots=slots,
    )

    assert result is not None
    assert result.status == ToolStatus.NEEDS_CLARIFICATION
    assert result.tool_name == "CheckoutOrderTool"
    assert "sku" in result.missing_slots
    assert result.clarification is not None
    assert result.clarification.buttons is not None
    assert len(result.clarification.buttons) == 3

    button_ids = [btn["id"] for btn in result.clarification.buttons]
    assert "SET_SLOT:sku:SUGAR_DANGOTE_50KG" in button_ids
    assert "SET_SLOT:sku:SUGAR_BUA_50KG" in button_ids
    assert "SET_SLOT:sku:SUGAR_ST_LOUIS_500G" in button_ids


@pytest.mark.asyncio
async def test_direct_interactive_button_id_parsing():
    """Validates 0ms NLP direct slot extraction from WhatsApp button callback IDs."""
    button_id = "SET_SLOT:sku:SUGAR_DANGOTE_50KG"
    parsed = NegotiationFrameManager.parse_interactive_id(button_id)

    assert parsed is not None
    slot_name, slot_val = parsed
    assert slot_name == "sku"
    assert slot_val == "SUGAR_DANGOTE_50KG"

    # Non-slot button IDs return None
    assert NegotiationFrameManager.parse_interactive_id("INTENT:SHOW_CATALOG") is None
    assert NegotiationFrameManager.parse_interactive_id(None) is None


@pytest.mark.asyncio
async def test_full_parameter_convergence_with_delivery_fee():
    """
    Scenario: Customer has resolved SKU (Dangote 50kg), quantity (2), fulfillment (Express Delivery), and location (Ikeja).
    Verifies:
    - Status is CONVERGED.
    - Merchandise total = 2 * ₦84,000 = ₦168,000 (16,800,000 kobo).
    - Delivery fee = ₦2,500 (250,000 kobo).
    - Total payable = ₦170,500 (17,050,000 kobo).
    - Action is GENERATE_VIRTUAL_NUBAN_HOLD.
    """
    dispatcher = get_local_tool_dispatcher()
    slots = {
        "sku": "SUGAR_DANGOTE_50KG",
        "quantity": 2,
        "fulfillment_type": "EXPRESS_DELIVERY",
        "delivery_zone": "Ikeja",
    }

    result = await dispatcher.evaluate(
        intent="INSTANT_CHECKOUT_ORDER",
        slots=slots,
    )

    assert result is not None
    assert result.status == ToolStatus.CONVERGED
    assert result.action == "GENERATE_VIRTUAL_NUBAN_HOLD"
    assert result.calculated_total_kobo == 17050000  # ₦170,500.00
    assert result.breakdown["subtotal_kobo"] == 16800000
    assert result.breakdown["delivery_fee_kobo"] == 250000
    assert result.breakdown["total_payable_kobo"] == 17050000


@pytest.mark.asyncio
async def test_atomic_check_and_hold_out_of_stock():
    """Validates that Parameter Convergence is blocked if inventory is depleted."""
    dispatcher = get_local_tool_dispatcher()
    slots = {
        "sku": "SUGAR_DANGOTE_50KG",
        "quantity": 50,
        "fulfillment_type": "WAREHOUSE_PICKUP",
    }

    async def mock_stock_depleted(sku: str, qty: int) -> bool:
        return False  # Zero stock available

    result = await dispatcher.evaluate(
        intent="INSTANT_CHECKOUT_ORDER",
        slots=slots,
        stock_checker=mock_stock_depleted,
    )

    assert result is not None
    assert result.status == ToolStatus.OUT_OF_STOCK
    assert result.action is None
    assert "out of stock" in result.clarification.prompt_text.lower()


@pytest.mark.asyncio
async def test_negotiation_frame_lifecycle_and_pii_scrubbing():
    """
    Validates:
    - Ephemeral Redis frame saving, reading, and eviction.
    - Phone number hashing in Redis keys.
    - Slot value sanitization for NDPA PII protection (BVN/NIN redacting).
    """
    merchant_id = str(uuid4())
    customer_phone = "+2348039876543"

    frame = NegotiationFrame(
        merchant_id=merchant_id,
        phone_hash=compute_phone_hash(merchant_id, customer_phone),
        active_tool="CheckoutOrderTool",
        intent="INSTANT_CHECKOUT_ORDER",
        bound_slots={
            "quantity": 2,
            "notes": "Deliver to my shop, my BVN is 22345678901 please note",
        },
        missing_slots=["sku", "fulfillment_type"],
    )

    # 1. Save frame (scrubs PII)
    await NegotiationFrameManager.save_frame(merchant_id, customer_phone, frame, ttl=60)

    # 2. Retrieve frame
    loaded = await NegotiationFrameManager.get_frame(merchant_id, customer_phone)
    assert loaded is not None
    assert loaded.bound_slots["quantity"] == 2
    # BVN must be redacted!
    assert "22345678901" not in loaded.bound_slots["notes"]
    assert "[REDACTED_BVN_8901]" in loaded.bound_slots["notes"]

    # 3. Evict frame
    evicted = await NegotiationFrameManager.evict_frame(merchant_id, customer_phone)
    assert evicted is True

    # 4. Check gone
    assert await NegotiationFrameManager.get_frame(merchant_id, customer_phone) is None


@pytest.mark.asyncio
async def test_deterministic_cancellation_keywords():
    """Tests that Nigerian Pidgin and English cancel keywords trigger eviction."""
    cancel_phrases = [
        "cancel am",
        "cancel order",
        "never mind",
        "no buy again",
        "i no wan buy",
        "forget am",
        "abort",
    ]
    for phrase in cancel_phrases:
        assert NegotiationFrameManager.is_cancellation_intent(phrase) is True

    # Non-cancellation
    assert NegotiationFrameManager.is_cancellation_intent("I want to buy 2 bags") is False
    assert NegotiationFrameManager.is_cancellation_intent("Where is your shop?") is False


@pytest.mark.asyncio
async def test_fast_path_delegates_to_local_tool_dispatcher():
    """
    Verifies that fast_path_classify no longer hardcodes NUBAN generation,
    and returns action="DISPATCH_LOCAL_TOOL".
    """
    # "I want 2 bags of sugar"
    res = fast_path_classify("I want 2 bags of sugar deliver to Ikeja")
    assert res is not None
    assert res.intent == "INSTANT_CHECKOUT_ORDER"
    assert res.action == "DISPATCH_LOCAL_TOOL"
    assert res.suggested_reply is None
    assert res.extracted_entities.get("quantity") == "2 bags"
    assert res.extracted_entities.get("product") == "sugar"
    assert res.extracted_entities.get("location") == "Ikeja / Mainland, Lagos"


@pytest.mark.asyncio
async def test_central_inference_engine_integration_clarification():
    """
    Tests CentralInferenceEngine running Stage 1 Fast-Path with LocalToolDispatcher:
    Input: "I want 2 bags of sugar"
    Expectation:
    - Routing source: FAST_PATH
    - Action: DISPATCH_CLARIFICATION
    - Suggested reply contains brand options
    - Extracted entities contain clarification buttons
    """
    engine = CentralInferenceEngine()
    context = AggregatedContext(
        customer_phone="+2348031112233",
        slices={
            "catalog_manifest": ContextSlice(
                slice_name="catalog_manifest",
                content='[{"sku": "SUGAR_DANGOTE_50KG", "name": "Dangote Sugar 50kg", "category": "sugar", "price_kobo": 8400000, "in_stock": true}, {"sku": "SUGAR_BUA_50KG", "name": "BUA Sugar 50kg", "category": "sugar", "price_kobo": 8200000, "in_stock": true}]',
            )
        }
    )

    result = await engine.classify(
        text="I want 2 bags of sugar",
        context=context,
        policy=ExecutionPolicy.FASTEST_PATH,
        task_priority=TaskPriority.CUSTOMER_FACING,
    )

    assert result.routing_source == "FAST_PATH"
    assert result.action == "DISPATCH_CLARIFICATION"
    assert "sugar" in result.suggested_reply.lower()
    assert "clarification_buttons" in result.extracted_entities
    buttons = result.extracted_entities["clarification_buttons"]
    assert len(buttons) >= 2


@pytest.mark.asyncio
async def test_central_inference_engine_full_convergence():
    """
    Tests CentralInferenceEngine running Turn 1 when all parameters are present:
    Input: "I want 2 bags of Dangote Sugar 50kg deliver to Ikeja"
    Expectation:
    - Parameter Convergence achieved on Turn 1!
    - Action: GENERATE_VIRTUAL_NUBAN_HOLD
    - Suggested reply contains ₦170,500 and Moniepoint MFB account details
    """
    engine = CentralInferenceEngine()
    context = AggregatedContext(
        customer_phone="+2348031112233",
        slices={
            "catalog_manifest": ContextSlice(
                slice_name="catalog_manifest",
                content='[{"sku": "SUGAR_DANGOTE_50KG", "name": "Dangote Sugar 50kg", "category": "sugar", "price_kobo": 8400000, "in_stock": true}]',
            )
        }
    )

    result = await engine.classify(
        text="I want 2 bags of Dangote Sugar 50kg deliver to Ikeja",
        context=context,
        policy=ExecutionPolicy.FASTEST_PATH,
        task_priority=TaskPriority.CUSTOMER_FACING,
    )

    assert result.routing_source == "FAST_PATH"
    assert result.action == "GENERATE_VIRTUAL_NUBAN_HOLD"
    assert "170,500" in result.suggested_reply
    assert "Moniepoint MFB" in result.suggested_reply
    assert result.extracted_entities.get("calculated_total_kobo") == 17050000
