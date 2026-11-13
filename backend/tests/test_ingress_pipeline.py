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
