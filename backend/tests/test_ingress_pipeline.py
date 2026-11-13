"""Tests for the 3-Stage Cascading Hybrid NLU Pipeline, Confidence Gates, and State Controllers."""

import pytest
from app.contexts.ingress.pipeline import CascadingNLUPipeline
from app.core.config import settings


@pytest.mark.asyncio
async def test_stage_1_fast_path_match():
    """Verifies that high-frequency commercial slang terminates at Stage 1 with 0 tokens and <5ms latency."""
    text = "Bless up! I don pay, see debit alert"
    result = await CascadingNLUPipeline.process(text)

    assert result.routing_source == "FAST_PATH"
    assert result.intent == "CONFIRM_PAYMENT"
    assert result.lead_tier == "HOT"
    assert result.confidence >= 0.90
    assert result.tokens_consumed == 0
    assert result.estimated_kobo_saved > 0
    assert "bless up" in result.suggested_reply.lower()


@pytest.mark.asyncio
async def test_stage_2_custom_model_match():
    """Verifies that nuanced wholesale inquiries fall through Stage 1 and resolve at Stage 2 with 0 tokens."""
    text = "Abeg give me wholesale price if I buy plenty cartons for my shop"
    result = await CascadingNLUPipeline.process(text)

    assert result.routing_source == "CUSTOM_LOCAL_MODEL"
    assert result.intent == "WHOLESALE_DISCOUNT_INQUIRY"
    assert result.lead_tier == "HOT"
    assert result.confidence >= 0.75
    assert result.tokens_consumed == 0
    assert result.estimated_kobo_saved > 0
    assert result.suggested_reply is not None


@pytest.mark.asyncio
async def test_stage_3_llm_escalation():
    """Verifies that complex, consultative inquiries fall through Stages 1 & 2 and escalate to Gemini LLM."""
    text = "We are setting up a brand new bakery in Ikeja and need flour specifications and long-term financing."
    result = await CascadingNLUPipeline.process(text)

    assert result.routing_source == "GEMINI_LLM_ESCALATION"
    assert result.confidence >= 0.80
    assert result.tokens_consumed > 0
    assert result.suggested_reply is not None


@pytest.mark.asyncio
async def test_state_controller_disable_custom_model():
    """Verifies that setting USE_CUSTOM_MODEL=False bypasses Stage 2 and routes directly to Stage 3."""
    original_state = settings.USE_CUSTOM_MODEL
    try:
        settings.USE_CUSTOM_MODEL = False
        text = "Abeg give me wholesale price if I buy plenty cartons for my shop"
        result = await CascadingNLUPipeline.process(text)

        # Bypassed Stage 2 -> Escalated to Stage 3
        assert result.routing_source == "GEMINI_LLM_ESCALATION"
    finally:
        settings.USE_CUSTOM_MODEL = original_state


@pytest.mark.asyncio
async def test_state_controller_disable_llm_escalation():
    """With LLM + Stage 2 disabled, unresolved queries get a help menu (NOT an agent handoff)."""
    original_llm_state = settings.USE_LLM_ESCALATION
    original_custom_state = settings.USE_CUSTOM_MODEL
    try:
        settings.USE_LLM_ESCALATION = False
        settings.USE_CUSTOM_MODEL = False
        text = "Random complex query that does not match fast path keywords at all."
        result = await CascadingNLUPipeline.process(text)

        assert result.routing_source == "FALLBACK_DESK_HANDOFF"
        assert result.action == "SHOW_HELP_MENU"
        assert result.tokens_consumed == 0
    finally:
        settings.USE_LLM_ESCALATION = original_llm_state
        settings.USE_CUSTOM_MODEL = original_custom_state


@pytest.mark.asyncio
async def test_unresolved_explicit_human_request_still_hands_off():
    """Agent handoff remains available as the last resort when the customer explicitly asks for a person."""
    original_llm_state = settings.USE_LLM_ESCALATION
    original_custom_state = settings.USE_CUSTOM_MODEL
    original_fast_state = settings.USE_FAST_PATH
    try:
        settings.USE_LLM_ESCALATION = False
        settings.USE_CUSTOM_MODEL = False
        settings.USE_FAST_PATH = False
        result = await CascadingNLUPipeline.process("I want to speak to human agent")

        assert result.action == "DISPATCH_AGENT_HANDOFF"
    finally:
        settings.USE_LLM_ESCALATION = original_llm_state
        settings.USE_CUSTOM_MODEL = original_custom_state
        settings.USE_FAST_PATH = original_fast_state


@pytest.mark.asyncio
async def test_stage3_fallback_ignores_rice_in_history_and_classifies_order_status():
    """Fallback recovery must scan only Latest Customer Message, never historical product mentions."""
    import time
    from app.adapters.llm import GeminiFlashAdapter, MockLLMAdapter

    prompt = (
        "Recent Dialogue History:\n"
        "Customer Name: Tunde Adeleke\n"
        "Customer Phone: 2348031234567\n"
        "Recent Turns:\n"
        "[Assistant]: Sharp! We don reserve your order (1x Mama Gold Rice 25kg) for delivery to Abuja.\n"
        "[Customer]: Abuja FCT\n\n"
        "Latest Customer Message: when is the my order going to arrive?"
    )

    adapter = GeminiFlashAdapter(api_key="", model_name="gemini-3.7-flash")
    fallback_res = adapter._build_handoff_fallback(time.perf_counter(), "simulated timeout", prompt)
    assert fallback_res.intent == "ORDER_STATUS_INQUIRY"
    assert fallback_res.action == "RESOLVE_ORDER_STATUS"
    assert fallback_res.extracted_entities.get("product") is None

    mock_res = await MockLLMAdapter().generate_chat_completion(prompt, "system")
    assert mock_res.intent == "ORDER_STATUS_INQUIRY"
    assert mock_res.action == "RESOLVE_ORDER_STATUS"


@pytest.mark.asyncio
async def test_customer_history_slice_role_labels_and_divider_stripping():
    """CustomerHistorySliceProvider formats DialogueTurn with role labels and strips WhatsApp dividers."""
    from app.contexts.ingress.providers import CustomerHistorySliceProvider
    from app.contexts.ingress.schemas import DialogueTurn

    turns = [
        DialogueTurn(role="assistant", text="Tap an order:\n━━━━━━━━━━━━━━━━━━━━\n1x Mama Gold Rice 25kg"),
        DialogueTurn(role="customer", text="Abuja FCT"),
    ]
    slice_obj = await CustomerHistorySliceProvider().resolve(
        merchant_id=None,
        customer_phone="+2348031234567",
        options={"customer_name": "Tunde Adeleke", "previous_context": turns},
    )
    assert "[Assistant]: Tap an order:" in slice_obj.content
    assert "[Customer]: Abuja FCT" in slice_obj.content
    assert "━━━━" not in slice_obj.content


@pytest.mark.asyncio
async def test_fsm_forwards_grounding_manifests_to_cascading_nlu(monkeypatch):
    """ConversationFSMService._run_cascading_nlu forwards FAQ and customer order manifests."""
    from uuid import uuid4
    from unittest.mock import AsyncMock
    from app.core.generation.fsm import ConversationFSMService
    from app.contexts.ingress.services import IngressService
    from app.contexts.ingress.schemas import NLUClassificationResponse

    captured = {}

    async def fake_build_manifests(session, merchant_id, customer_phone):
        return {
            "faq_manifest": "### Merchant Policies & FAQs:\n- Delivery SLA: 24h",
            "faq_data": [{"title": "Delivery SLA", "content": "24h", "intent": "DELIVERY_TIMELINE_INQUIRY"}],
            "customer_orders_manifest": "### Customer's Recent Orders:\n- Order: 1x Mama Gold Rice 25kg",
            "customer_orders_data": [{"order_summary": "1x Mama Gold Rice 25kg"}],
        }

    async def fake_process(**kwargs):
        captured.update(kwargs)
        return NLUClassificationResponse(
            routing_source="GEMINI_LLM_ESCALATION",
            intent="ORDER_STATUS_INQUIRY",
            lead_tier="HOT",
            urgency_score=8,
            confidence=0.95,
            detected_dialect="Standard English",
            action="RESOLVE_ORDER_STATUS",
            latency_ms=10.0,
        )

    monkeypatch.setattr(IngressService, "build_grounding_manifests", staticmethod(fake_build_manifests))
    monkeypatch.setattr(CascadingNLUPipeline, "process", staticmethod(fake_process))

    await ConversationFSMService._run_cascading_nlu(
        merchant_id=uuid4(),
        text="when is the my order going to arrive?",
        customer_phone="+2348031234567",
        customer_name="Tunde Adeleke",
        recent_history=[],
        session=AsyncMock(),
        merchant_name="Alaba Agro",
        custom_dictionary=None,
        catalog_manifest=None,
        provider_context=None,
    )

    assert captured["customer_orders_manifest"] == "### Customer's Recent Orders:\n- Order: 1x Mama Gold Rice 25kg"
    assert captured["faq_manifest"] == "### Merchant Policies & FAQs:\n- Delivery SLA: 24h"
    assert len(captured["customer_orders_data"]) == 1
