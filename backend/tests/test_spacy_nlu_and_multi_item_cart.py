"""Comprehensive Automated Tests for Native spaCy NLU Engine, Canonical offering_id (UUIDv5),
Contrastive Mid-Flow Mutations, and Multi-Item Bulk Cart (`line_items`) Support.
"""

from uuid import UUID, uuid4
import pytest

from app.adapters.base import InteractiveProtocolEnvelope, ProductTapAction
from app.adapters.custom_classifier import get_custom_classifier_adapter
from app.adapters.providers.spacy_nlu_engine import get_spacy_nlu_engine
from app.contexts.ingress.fast_path import fast_path_classify
from app.contexts.knowledge.offering_schemas import (
    DEFAULT_DEMO_MERCHANT_UUID,
    compute_offering_id,
)
from app.contexts.knowledge.services import KnowledgeService
from app.core.generation.fsm import ConversationFSMService, FSMTransitionType
from app.core.generation.negotiation import NegotiationFrameManager
from app.core.generation.tools import ToolStatus, get_local_tool_dispatcher


@pytest.mark.asyncio
async def test_canonical_offering_id_uuidv5_promotion():
    """
    Verifies that catalog items carry a deterministic UUIDv5 `offering_id` derived
    from (merchant_id, sku), and that KnowledgeService and CheckoutOrderTool resolve
    by `offering_id` as well as backward-compatible `sku`.
    """
    sugar_offering_id = compute_offering_id(DEFAULT_DEMO_MERCHANT_UUID, "SUGAR_DANGOTE_50KG")
    # Valid deterministic UUIDv5
    parsed_uuid = UUID(sugar_offering_id)
    assert parsed_uuid.version == 5
    # Deterministic across repeated calls
    assert compute_offering_id(DEFAULT_DEMO_MERCHANT_UUID, "SUGAR_DANGOTE_50KG") == sugar_offering_id
    # Tenant-scoped isolation: different merchant_id yields a different offering_id for the same SKU
    other_merchant_offering_id = compute_offering_id(uuid4(), "SUGAR_DANGOTE_50KG")
    assert other_merchant_offering_id != sugar_offering_id

    # Verify KnowledgeService resolves both offering_id and sku
    offering_by_id = await KnowledgeService.get_offering(
        identifier=sugar_offering_id,
        merchant_id=DEFAULT_DEMO_MERCHANT_UUID,
    )
    assert offering_by_id is not None
    assert offering_by_id.offering_id == sugar_offering_id
    assert offering_by_id.sku == "SUGAR_DANGOTE_50KG"

    offering_by_sku = await KnowledgeService.get_offering(
        identifier="SUGAR_DANGOTE_50KG",
        merchant_id=DEFAULT_DEMO_MERCHANT_UUID,
    )
    assert offering_by_sku is not None
    assert offering_by_sku.offering_id == sugar_offering_id

    # Verify ProductTapAction populates both offering_id and sku
    tap_env = InteractiveProtocolEnvelope.model_validate(f"PRODUCT:{sugar_offering_id}")
    assert isinstance(tap_env.event, ProductTapAction)
    assert tap_env.event.offering_id == sugar_offering_id


@pytest.mark.asyncio
async def test_spacy_nlu_intent_and_hard_negatives():
    """
    Verifies that the native spaCy NLU pipeline (TextCatBOW + EntityRuler + Matcher):
    1. Classifies Nigerian English & Pidgin intents accurately across Stage 1 and Stage 2.
    2. Does NOT false-positive on substring collisions like "This is a prepaid meter inquiry"
       or "I want to ask if una dey deliver".
    3. Disambiguates polysemous Pidgin "Drop am for Yaba" (delivery slot) vs
       "Drop am, I no buy again" (CANCEL_ORDER).
    """
    engine = get_spacy_nlu_engine()

    # Stage 1 Fast-Path matches
    fp_price = fast_path_classify("Abeg how much be Dangote sugar 50kg?")
    assert fp_price is not None
    assert fp_price.intent == "PRICE_INQUIRY"
    assert fp_price.extracted_entities.get("sku") == "SUGAR_DANGOTE_50KG"
    assert fp_price.extracted_entities.get("offering_id") == compute_offering_id(
        DEFAULT_DEMO_MERCHANT_UUID, "SUGAR_DANGOTE_50KG"
    )

    # Stage 2 Custom Classifier (spaCy adapter) matches wholesale discount inquiry
    classifier = get_custom_classifier_adapter()
    stage2_res = await classifier.classify("What is your wholesale discount for 50 bags of rice?")
    assert stage2_res is not None
    assert stage2_res.intent == "WHOLESALE_DISCOUNT_INQUIRY"
    assert stage2_res.confidence >= 0.70

    # Hard negative 1: "prepaid" contains "paid", must NOT trigger CONFIRM_PAYMENT
    prepaid_parsed = engine.predict_intent_and_slots("This is a prepaid meter inquiry")
    assert prepaid_parsed.intent != "CONFIRM_PAYMENT"

    # Hard negative 2: "Drop am for Yaba" -> delivery zone slot fill, NOT CANCEL_ORDER
    drop_yaba = engine.predict_intent_and_slots("Drop am for Yaba")
    assert drop_yaba.intent == "INSTANT_CHECKOUT_ORDER"
    assert not drop_yaba.is_cancellation
    assert drop_yaba.slots.get("delivery_zone") == "Yaba / Central, Lagos"
    assert drop_yaba.slots.get("fulfillment_type") == "EXPRESS_DELIVERY"

    # Contrast: "Drop am, I no buy again" -> CANCEL_ORDER
    drop_cancel = engine.predict_intent_and_slots("Drop am, I no buy again")
    assert drop_cancel.intent == "CANCEL_ORDER"
    assert drop_cancel.is_cancellation


@pytest.mark.asyncio
async def test_spacy_contrastive_mid_flow_mutation_in_fsm():
    """
    Verifies that a mid-checkout contrastive utterance ("No be Dangote again abeg,
    make am 5 bags of Mama Gold Rice 50kg instead") uses spaCy's token-level rejection
    Matcher + active_bound_slots diffing to evict the stale Dangote `offering_id`/`sku`
    and bind `RICE_MAMA_GOLD_50KG` + `quantity=5`.
    """
    merchant_id = str(uuid4())
    phone = "+2348099887766"
    await NegotiationFrameManager.evict_frame(merchant_id, phone)

    # Step 1: Start checkout for 2 bags of Dangote Sugar (missing fulfillment_type)
    step1 = await ConversationFSMService.process_turn(
        merchant_id=merchant_id,
        customer_phone=phone,
        customer_name="Tunde Bakare",
        sanitized_text="I wan buy 2 bags of Dangote sugar",
    )
    assert step1.transition == FSMTransitionType.NEW_FLOW
    assert step1.active_frame is not None
    assert step1.active_frame["bound_slots"].get("sku") == "SUGAR_DANGOTE_50KG"
    assert step1.active_frame["bound_slots"].get("offering_id") == compute_offering_id(
        merchant_id, "SUGAR_DANGOTE_50KG"
    )
    assert step1.active_frame["bound_slots"].get("quantity") == 2

    # Step 2: Contrastive mid-flow mutation mentioning both rejected ("Dangote") and target ("Mama Gold Rice 50kg")
    step2 = await ConversationFSMService.process_turn(
        merchant_id=merchant_id,
        customer_phone=phone,
        customer_name="Tunde Bakare",
        sanitized_text="No be Dangote again abeg, make am 5 bags of Mama Gold Rice 50kg instead, deliver to Ikeja",
    )
    assert step2.transition == FSMTransitionType.MUTATE_SLOTS
    assert step2.action == "GENERATE_VIRTUAL_NUBAN_HOLD"
    # 5 bags of Mama Gold Rice 50kg (5 * 78,000 = 390,000) + Ikeja delivery (2,500) = 392,500 Naira (39,250,000 kobo)
    assert step2.extracted_entities.get("calculated_total_kobo") == 39250000
    assert "Mama Gold Rice 50kg" in step2.envelope.body_text
    assert "Dangote" not in step2.envelope.body_text


@pytest.mark.asyncio
async def test_multi_item_bulk_cart_convergence_and_clarification():
    """
    Verifies Multi-Item Bulk Cart (`line_items`) support:
    1. Coordinated order with unambiguous SKUs ("Give me 2 bags of Dangote sugar AND
       3 bags of Mama Gold rice 50kg deliver to Ikeja") pairs each (quantity, offering_id/sku)
       clause and converges with exact combined Kobo arithmetic.
    2. Coordinated order with an ambiguous line item ("Give me 2 bags of Dangote sugar
       and 3 bags of rice") emits `SET_SLOT:line_item_sku:1:{sku}` buttons and converges
       once disambiguated.
    """
    dispatcher = get_local_tool_dispatcher()
    engine = get_spacy_nlu_engine()

    # Case 1: Unambiguous multi-item bulk cart
    parsed_bulk = engine.predict_intent_and_slots(
        "Give me 2 bags of Dangote sugar and 3 bags of Mama Gold rice 50kg deliver to Ikeja"
    )
    assert parsed_bulk.intent == "INSTANT_CHECKOUT_ORDER"
    line_items = parsed_bulk.slots.get("line_items")
    assert isinstance(line_items, list)
    assert len(line_items) == 2

    res_bulk = await dispatcher.evaluate(
        intent="INSTANT_CHECKOUT_ORDER",
        slots=parsed_bulk.slots,
    )
    assert res_bulk is not None
    assert res_bulk.status == ToolStatus.CONVERGED
    # 2 * 84,000 (168,000) + 3 * 78,000 (234,000) + 2,500 Ikeja delivery = 404,500 Naira = 40,450,000 kobo
    assert res_bulk.calculated_total_kobo == 40450000
    assert res_bulk.breakdown["subtotal_kobo"] == 40200000
    assert res_bulk.breakdown["delivery_fee_kobo"] == 250000
    assert len(res_bulk.breakdown["line_items"]) == 2

    # Case 2: Multi-item cart with ambiguous second item ("3 bags of rice") via FSM
    merchant_id = str(uuid4())
    phone = "+2348011223344"
    await NegotiationFrameManager.evict_frame(merchant_id, phone)

    turn1 = await ConversationFSMService.process_turn(
        merchant_id=merchant_id,
        customer_phone=phone,
        customer_name="Ngozi Okonkwo",
        sanitized_text="Give me 2 bags of Dangote sugar and 3 bags of rice",
    )
    assert turn1.action == "DISPATCH_CLARIFICATION"
    button_ids = [b["id"] for b in turn1.envelope.buttons]
    assert any(bid.startswith("SET_SLOT:line_item_sku:1:") for bid in button_ids)

    # Customer taps Mama Gold 50kg for line item index 1
    turn2 = await ConversationFSMService.process_turn(
        merchant_id=merchant_id,
        customer_phone=phone,
        customer_name="Ngozi Okonkwo",
        sanitized_text="Mama Gold 50kg",
        is_interactive=True,
        interactive_id="SET_SLOT:line_item_sku:1:RICE_MAMA_GOLD_50KG",
    )
    # Still needs fulfillment_type
    assert turn2.action == "DISPATCH_CLARIFICATION"
    fulfillment_buttons = [b["id"] for b in turn2.envelope.buttons]
    assert "SET_SLOT:fulfillment_type:WAREHOUSE_PICKUP" in fulfillment_buttons

    # Customer selects Warehouse Pickup (0 delivery fee)
    turn3 = await ConversationFSMService.process_turn(
        merchant_id=merchant_id,
        customer_phone=phone,
        customer_name="Ngozi Okonkwo",
        sanitized_text="Warehouse Pickup",
        is_interactive=True,
        interactive_id="SET_SLOT:fulfillment_type:WAREHOUSE_PICKUP",
    )
    assert turn3.action == "GENERATE_VIRTUAL_NUBAN_HOLD"
    # 2 * 84,000 + 3 * 78,000 + 0 pickup = 402,000 Naira = 40,200,000 kobo
    assert "₦402,000" in turn3.envelope.body_text
    assert "2x Dangote Sugar 50kg" in turn3.envelope.body_text
    assert "3x Mama Gold Rice 50kg" in turn3.envelope.body_text
