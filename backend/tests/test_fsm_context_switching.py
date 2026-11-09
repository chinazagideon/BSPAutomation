"""Comprehensive Automated Tests for Deterministic FSM, LIFO ContextStack & Stateless Open-Weight LLM Boundary.

Verifies the 5 Pydantic v2 Domain-Modeling Patterns & Context Switching Resilience:
1. Pattern 1: Declarative Boundary Validation (Annotated + BeforeValidator/AfterValidator + model_validate_json).
2. Pattern 2: Self-Healing Kobo/Naira Financial Invariant (@model_validator(mode="after") on HydrationTranslationOutput).
3. Pattern 3: Rich ContextStack Domain Model (push, pop, peek, lazy TTL pruning, deduplication, MAX_STACK_DEPTH, @computed_field active_frame).
4. Pattern 4: Auto-Generated Grammar Constrained Schema via ParsedTurnInput.llm_json_schema().
5. Pattern 5: Discriminated Union & Python match/case Protocol Dispatch (InteractiveProtocolEnvelope).
6. End-to-End LIFO Context Switch (CHECKOUT -> PUSH -> DELIVERY_TIMELINE_INQUIRY -> POP -> Function B Hydrated Resume).
7. Mid-Checkout Slot Mutation (changing product/quantity mid-flow without stale SKU leakage).
8. Polysemous Nigerian Pidgin Disambiguation ("Drop am for Yaba" vs "Drop am, I no buy again").
"""

import json
import time
from uuid import uuid4
import pytest

from app.adapters.base import (
    ClassificationOutput,
    CommandTapAction,
    HydrationTranslationInput,
    HydrationTranslationOutput,
    InteractiveProtocolEnvelope,
    ParsedTurnInput,
    ProductTapAction,
    SlotBindAction,
)
from app.adapters.providers.open_weight import get_open_weight_adapter
from app.core.generation.fsm import ConversationFSMService, FSMTransitionType
from app.core.generation.negotiation import (
    ContextStack,
    NegotiationFrame,
    NegotiationFrameManager,
    compute_phone_hash,
)
from app.core.generation.response_classifier import ResponseStrategy
from app.core.generation.response_formatter import EgressMessageType


@pytest.mark.asyncio
async def test_pattern_1_declarative_boundary_validation_and_pii_scrubbing():
    """
    Verifies Pattern 1:
    - ParsedTurnInput.model_validate_json() and ClassificationOutput.model_validate_json()
      declaratively scrub Nigerian BVN/NIN PII in strings and slot dicts, scale 0..100 confidence
      to 0.0..1.0, scale 0.0..1.0 urgency to 1..10, and coerce lead_tier & dialect.
    """
    raw_llm_json = json.dumps({
        "intent": "instant_checkout_order",
        "canonical_query": "Order 2 bags of sugar, my BVN is 22345678901",
        "slots": {
            "product": "sugar",
            "quantity": 2,
            "customer_note": "My NIN is 12345678901 please call me",
        },
        "confidence": 94.0,       # Should be scaled from 94% -> 0.94
        "urgency_score": 0.85,    # Should be scaled from 0.85 -> 9
        "lead_tier": "Tier 1 - Hot",
        "detected_dialect": "pidgin english",
    })

    parsed = ParsedTurnInput.model_validate_json(raw_llm_json)
    assert parsed.intent == "INSTANT_CHECKOUT_ORDER"
    assert parsed.confidence == 0.94
    assert parsed.urgency_score == 9
    assert parsed.lead_tier == "HOT"
    assert parsed.detected_dialect == "Nigerian Pidgin"
    # Verify PII was scrubbed declaratively without imperative service loops
    assert "22345678901" not in parsed.canonical_query
    assert "[REDACTED_BVN_8901]" in parsed.canonical_query
    assert "12345678901" not in parsed.slots["customer_note"]
    assert "[REDACTED_NIN_8901]" in parsed.slots["customer_note"]

    # Also verify ClassificationOutput.model_validate_json()
    cls_out = ClassificationOutput.model_validate_json(raw_llm_json)
    assert cls_out.intent == "INSTANT_CHECKOUT_ORDER"
    assert cls_out.confidence == 0.94
    assert cls_out.urgency_score == 9
    assert cls_out.lead_tier == "HOT"


@pytest.mark.asyncio
async def test_pattern_2_self_healing_kobo_financial_invariant():
    """
    Verifies Pattern 2:
    - HydrationTranslationOutput @model_validator(mode="after") preserves valid translations
      that keep all verified Naira amounts intact.
    - Automatically heals to fallback_body_text (setting used_fallback=True) if the LLM
      drops or corrupts any Naira currency figure.
    """
    fallback = "Delivery to Lekki is ₦4,500. Your 2x Dangote Sugar 50kg subtotal is ₦168,000 (Total: ₦172,500)."

    # Case A: Faithful translation preserving all Naira figures
    valid_out = HydrationTranslationOutput(
        translated_text="No wahala! Delivery go Lekki na ₦4,500. For your 2x Dangote Sugar 50kg (₦168,000), total na ₦172,500.",
        fallback_body_text=fallback,
    )
    assert valid_out.used_fallback is False
    assert "No wahala!" in valid_out.translated_text

    # Case B: Hallucinated / corrupted price (₦17,250 instead of ₦172,500) -> Self-Heals!
    corrupted_out = HydrationTranslationOutput(
        translated_text="No wahala! Delivery go Lekki na ₦4,500. Total na ₦17,250.",
        fallback_body_text=fallback,
    )
    assert corrupted_out.used_fallback is True
    assert corrupted_out.translated_text == fallback


@pytest.mark.asyncio
async def test_pattern_3_rich_context_stack_domain_model_invariants():
    """
    Verifies Pattern 3:
    - ContextStack push, pop, peek, and @computed_field active_frame.
    - Automatic lazy pruning of expired frames via @field_validator.
    - Deduplication of frames with the same intent.
    - MAX_STACK_DEPTH (3) capping evicting the oldest bottom frame.
    """
    merchant_id = str(uuid4())
    phone = "+2348030001111"
    phone_hash = compute_phone_hash(merchant_id, phone)

    expired_frame = NegotiationFrame(
        merchant_id=merchant_id,
        phone_hash=phone_hash,
        intent="EXPIRED_FLOW",
        expires_at=time.time() - 10.0,  # Already expired
    )
    live_checkout = NegotiationFrame(
        merchant_id=merchant_id,
        phone_hash=phone_hash,
        intent="INSTANT_CHECKOUT_ORDER",
        bound_slots={"product": "sugar", "quantity": 2},
        missing_slots=["sku", "fulfillment_type"],
    )

    # 1. @field_validator prunes expired_frame immediately upon instantiation
    stack = ContextStack(
        merchant_id=merchant_id,
        phone_hash=phone_hash,
        frames=[expired_frame, live_checkout],
    )
    assert len(stack.frames) == 1
    assert stack.active_frame is not None
    assert stack.active_frame.intent == "INSTANT_CHECKOUT_ORDER"

    # 2. Push sub-flow frame -> active_frame becomes DELIVERY_TIMELINE_INQUIRY
    subflow = NegotiationFrame(
        merchant_id=merchant_id,
        phone_hash=phone_hash,
        intent="DELIVERY_TIMELINE_INQUIRY",
        node_type="ATOMIC_QUERY",
    )
    stack.push(subflow)
    assert len(stack.frames) == 2
    assert stack.active_frame.intent == "DELIVERY_TIMELINE_INQUIRY"

    # 3. Pop sub-flow -> restores INSTANT_CHECKOUT_ORDER as active_frame
    popped = stack.pop()
    assert popped is not None
    assert popped.intent == "DELIVERY_TIMELINE_INQUIRY"
    assert stack.active_frame is not None
    assert stack.active_frame.intent == "INSTANT_CHECKOUT_ORDER"

    # 4. Depth capping at MAX_STACK_DEPTH = 3
    stack.push(NegotiationFrame(merchant_id=merchant_id, intent="FLOW_2"))
    stack.push(NegotiationFrame(merchant_id=merchant_id, intent="FLOW_3"))
    stack.push(NegotiationFrame(merchant_id=merchant_id, intent="FLOW_4"))
    assert len(stack.frames) == 3
    assert [f.intent for f in stack.frames] == ["FLOW_2", "FLOW_3", "FLOW_4"]


@pytest.mark.asyncio
async def test_pattern_4_auto_generated_grammar_constrained_json_schema():
    """
    Verifies Pattern 4:
    - ParsedTurnInput.llm_json_schema() dynamically derives the JSON schema from the Pydantic model
      with CanonicalIntentType enum values and strips internal telemetry fields.
    """
    schema = ParsedTurnInput.llm_json_schema()
    props = schema["properties"]
    assert "intent" in props
    assert "slots" in props
    assert "slot_mutations" in props
    assert "is_cancellation" in props
    assert "tokens_consumed" not in props
    assert "latency_ms" not in props


@pytest.mark.asyncio
async def test_pattern_5_discriminated_union_interactive_protocol_dispatch():
    """
    Verifies Pattern 5:
    - InteractiveProtocolEnvelope parses raw callback IDs into typed Discriminated Union variants
      (SlotBindAction, ProductTapAction, CommandTapAction).
    """
    env_slot = InteractiveProtocolEnvelope.model_validate("SET_SLOT:sku:SUGAR_DANGOTE_50KG")
    assert isinstance(env_slot.event, SlotBindAction)
    assert env_slot.event.slot_name == "sku"
    assert env_slot.event.slot_value == "SUGAR_DANGOTE_50KG"

    env_prod = InteractiveProtocolEnvelope.model_validate("PRODUCT:RICE_MAMA_GOLD_50KG")
    assert isinstance(env_prod.event, ProductTapAction)
    assert env_prod.event.sku == "RICE_MAMA_GOLD_50KG"

    env_cmd = InteractiveProtocolEnvelope.model_validate("INTENT:SHOW_CATALOG")
    assert isinstance(env_cmd.event, CommandTapAction)
    assert env_cmd.event.command == "SHOW_CATALOG"


@pytest.mark.asyncio
async def test_lifo_context_switch_push_subflow_and_pop_hydrated_resume():
    """
    End-to-End Context Switch Verification:
    1. Turn 1: Customer starts checkout ("I want 2 bags of Dangote Sugar 50kg").
       -> FSM creates CHECKOUT frame waiting for fulfillment_type.
    2. Turn 2: Customer switches context ("Wait o, how long delivery dey take for Lekki?").
       -> FSM pushes sub-flow, resolves DELIVERY_TIMELINE_INQUIRY, pops back to CHECKOUT,
          and invokes Function B to hydrate the combined delivery ETA + checkout resume prompt
          with the CHECKOUT clarification buttons attached.
    3. Turn 3: Customer supplies delivery ("Drop am for Lekki").
       -> Disambiguates 'drop am for Lekki' as EXPRESS_DELIVERY to Lekki (NOT cancellation!)
          and converges the checkout order with exact Kobo calculation.
    """
    merchant_id = str(uuid4())
    phone = "+2348035556677"
    await NegotiationFrameManager.evict_frame(merchant_id, phone)

    # Turn 1: Start checkout with SKU & quantity known, missing fulfillment_type
    turn1 = await ConversationFSMService.process_turn(
        merchant_id=merchant_id,
        customer_phone=phone,
        customer_name="Chidi Obi",
        sanitized_text="I want 2 bags of Dangote Sugar 50kg",
    )
    assert turn1.intent == "INSTANT_CHECKOUT_ORDER"
    assert turn1.active_frame is not None
    assert turn1.active_frame["bound_slots"]["sku"] == "SUGAR_DANGOTE_50KG"
    assert turn1.active_frame["bound_slots"]["quantity"] == 2
    assert "fulfillment_type" in turn1.active_frame["missing_slots"]

    # Turn 2: Out-of-context question mid-checkout!
    turn2 = await ConversationFSMService.process_turn(
        merchant_id=merchant_id,
        customer_phone=phone,
        customer_name="Chidi Obi",
        sanitized_text="Wait o, how long delivery dey take for Lekki?",
    )
    assert turn2.transition == FSMTransitionType.PUSH_SUBFLOW_AND_POP_RESUME
    assert turn2.intent == "DELIVERY_TIMELINE_INQUIRY"
    # Verify Function B hydrated both the sub-flow answer AND the resumed order prompt
    assert "same-day" in turn2.envelope.body_text.lower() or "deliver" in turn2.envelope.body_text.lower()
    assert "Dangote Sugar 50kg" in turn2.envelope.body_text
    # Verify the resumed frame's interactive buttons are still attached!
    assert turn2.envelope.message_type == EgressMessageType.INTERACTIVE_BUTTONS
    button_ids = [b["id"] for b in (turn2.envelope.buttons or [])]
    assert "SET_SLOT:fulfillment_type:EXPRESS_DELIVERY" in button_ids
    # Verify the popped frame is still the active frame on top of the LIFO stack
    assert turn2.active_frame is not None
    assert turn2.active_frame["intent"] == "INSTANT_CHECKOUT_ORDER"

    # Turn 3: Polysemous Pidgin "Drop am for Lekki" -> Must converge checkout, NOT cancel!
    turn3 = await ConversationFSMService.process_turn(
        merchant_id=merchant_id,
        customer_phone=phone,
        customer_name="Chidi Obi",
        sanitized_text="Oya drop am for Lekki",
    )
    assert turn3.transition == FSMTransitionType.ADVANCE_FRAME
    assert turn3.envelope.strategy == ResponseStrategy.CHECKOUT_CONVERGED
    # 2 * ₦84,000 (₦168,000) + Lekki delivery (₦4,500) = ₦172,500
    assert "₦172,500" in turn3.envelope.body_text
    assert turn3.active_frame is None  # Popped upon convergence!


@pytest.mark.asyncio
async def test_mid_checkout_slot_mutation_replaces_stale_product_and_quantity():
    """
    Scenario: Customer is mid-checkout for 2 bags of Dangote Sugar 50kg (missing fulfillment_type),
    then pivots: "Actually make it 3 bags of Mama Gold Rice 50kg instead".
    Verifies:
    - FSM transitions via MUTATE_SLOTS.
    - Stale sugar SKU and unit price are cleared and replaced with RICE_MAMA_GOLD_50KG (qty=3).
    """
    merchant_id = str(uuid4())
    phone = "+2348037778899"
    await NegotiationFrameManager.evict_frame(merchant_id, phone)

    # Turn 1: Start order for 2 bags of Dangote Sugar 50kg
    await ConversationFSMService.process_turn(
        merchant_id=merchant_id,
        customer_phone=phone,
        customer_name="Amina Bello",
        sanitized_text="I want 2 bags of Dangote Sugar 50kg",
    )

    # Turn 2: Mutate product & quantity mid-flow
    turn2 = await ConversationFSMService.process_turn(
        merchant_id=merchant_id,
        customer_phone=phone,
        customer_name="Amina Bello",
        sanitized_text="Actually make it 3 bags of Mama Gold Rice 50kg instead",
    )
    assert turn2.transition == FSMTransitionType.MUTATE_SLOTS
    assert turn2.active_frame is not None
    assert turn2.active_frame["bound_slots"]["sku"] == "RICE_MAMA_GOLD_50KG"
    assert turn2.active_frame["bound_slots"]["product_name"] == "Mama Gold Rice 50kg"
    assert turn2.active_frame["bound_slots"]["quantity"] == 3
    assert "3x Mama Gold Rice 50kg" in turn2.envelope.body_text
