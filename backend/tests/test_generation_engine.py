"""Automated Tests for Shared Generation Kernel & Three-Tier Wallet Guard (ADR-0039, ADR-0040, ADR-0041)."""

import pytest
import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from app.core.generation import (
    InferenceEnginePort,
    ExecutionPolicy,
    TaskPriority,
    ClassificationResult,
    ContextSlice,
    AggregatedContext,
    ContextProvider,
    ProviderRegistry,
    ContextAggregator,
    ThreeTierWalletGuard,
    FallbackFactoryRegistry,
    CentralInferenceEngine,
    get_inference_engine,
)
from app.contexts.desk.schemas import SixFieldContextCard


@pytest.mark.asyncio
async def test_three_tier_wallet_guard_evaluation():
    """Validates Three-Tier Degradation on Soft Limits (ADR-0040)."""
    # 1. Normal Tier (> 2,000 tokens)
    can_exec, tier = await ThreeTierWalletGuard.evaluate_tier(3500, TaskPriority.INTERNAL_ADMIN)
    assert can_exec is True
    assert tier == "NORMAL_TIER"

    can_exec, tier = await ThreeTierWalletGuard.evaluate_tier(3500, TaskPriority.CUSTOMER_FACING)
    assert can_exec is True
    assert tier == "NORMAL_TIER"

    # 2. Conservation Soft Cap (1 - 2,000 tokens)
    # Direct customer-facing WhatsApp chats are allowed
    can_exec, tier = await ThreeTierWalletGuard.evaluate_tier(1500, TaskPriority.CUSTOMER_FACING)
    assert can_exec is True
    assert tier == "CONSERVATION_SOFT_CAP_ALLOWED"

    # Internal admin tasks (Desk 6-field card) are throttled to deterministic fallback!
    can_exec, tier = await ThreeTierWalletGuard.evaluate_tier(1500, TaskPriority.INTERNAL_ADMIN)
    assert can_exec is False
    assert tier == "CONSERVATION_SOFT_CAP_THROTTLED"

    # 3. Hard Cap (<= 0 tokens)
    # Within 1,000 leeway buffer for in-flight customer requests
    can_exec, tier = await ThreeTierWalletGuard.evaluate_tier(-200, TaskPriority.CUSTOMER_FACING)
    assert can_exec is True
    assert tier == "LEEWAY_BUFFER_ALLOWED"

    can_exec, tier = await ThreeTierWalletGuard.evaluate_tier(-200, TaskPriority.INTERNAL_ADMIN)
    assert can_exec is False

    # Fully exhausted beyond leeway
    can_exec, tier = await ThreeTierWalletGuard.evaluate_tier(-1500, TaskPriority.CUSTOMER_FACING)
    assert can_exec is False
    assert tier == "HARD_CAP_EXHAUSTED"


@pytest.mark.asyncio
async def test_context_aggregator_bounded_timeout_and_pii_masking():
    """Validates bounded 35ms timeout and NDPA 2023 Ephemeral PII tokenization (ADR-0041)."""
    aggregator = ContextAggregator(default_timeout_ms=35.0)

    # Provider with PII content (BVN and NUBAN)
    class TestPiiProvider(ContextProvider):
        @property
        def slice_name(self) -> str:
            return "test_pii_slice"

        async def resolve(self, merchant_id, customer_phone, options=None):
            return ContextSlice(
                slice_name=self.slice_name,
                content="Customer BVN is 22334455667 and account number is 0123456789 Moniepoint.",
                token_estimate=20,
            )

    # Slow provider that simulates latency exceeding 35ms
    class SlowTimeoutProvider(ContextProvider):
        @property
        def slice_name(self) -> str:
            return "slow_slice"

        async def resolve(self, merchant_id, customer_phone, options=None):
            await asyncio.sleep(0.1)  # 100ms
            return ContextSlice(slice_name=self.slice_name, content="Should not appear", token_estimate=10)

    ProviderRegistry.register(TestPiiProvider())
    ProviderRegistry.register(SlowTimeoutProvider())

    merchant_id = uuid4()
    context = await aggregator.aggregate(
        merchant_id=merchant_id,
        customer_phone="+2348031112233",
        requested_slices=["test_pii_slice", "slow_slice"],
        timeout_ms=35.0,
    )

    # Assert slow provider was dropped gracefully by timeout
    assert "slow_slice" not in context.slices

    # Assert fast provider was resolved
    assert "test_pii_slice" in context.slices
    pii_content = context.slices["test_pii_slice"].content

    # Assert raw BVN and NUBAN were masked under NDPA 2023
    assert "22334455667" not in pii_content
    assert "0123456789" not in pii_content
    assert "[REDACTED_BVN_5667]" in pii_content
    assert "[REDACTED_NUBAN_6789]" in pii_content

    # Test Ephemeral Re-Hydration
    model_output = f"I have noted your verified account [REDACTED_NUBAN_6789]."
    rehydrated = context.rehydrate_text(model_output)
    assert "0123456789" in rehydrated
    assert "[REDACTED_NUBAN_6789]" not in rehydrated


@pytest.mark.asyncio
async def test_central_inference_engine_cascading_stages():
    """Validates Stage 1 (FastPath), Stage 2 (Local ONNX), and Stage 3 (LLM) execution."""
    engine = get_inference_engine()

    # 1. Stage 1: Deterministic Trigram Fast-Path (Pidgin pricing query)
    res_stage1 = await engine.classify(
        text="slash price if i buy plenty wholesale",
        policy=ExecutionPolicy.CASCADING_FALLBACK,
        task_priority=TaskPriority.CUSTOMER_FACING,
    )
    assert res_stage1.routing_source in ["FAST_PATH", "CUSTOM_LOCAL_MODEL"]
    assert res_stage1.tokens_consumed == 0
    assert res_stage1.latency_ms < 100.0

    # 2. Stage 2: Local Custom Model / Commercial Slang
    res_stage2 = await engine.classify(
        text="delivery timeline dispatch rider waybill",
        policy=ExecutionPolicy.LOCAL_MODEL,
        task_priority=TaskPriority.CUSTOMER_FACING,
    )
    assert res_stage2.routing_source == "CUSTOM_LOCAL_MODEL"
    assert res_stage2.tokens_consumed == 0

    # 3. Stage 3: Deep Reasoning LLM Escalation (Open complex dialogue)
    res_stage3 = await engine.classify(
        text="Can we discuss a custom B2B enterprise SLA for 500 branch locations across West Africa?",
        policy=ExecutionPolicy.DEEP_REASONING,
        task_priority=TaskPriority.CUSTOMER_FACING,
        wallet_token_balance=5000,
    )
    assert res_stage3.routing_source == "GEMINI_LLM_ESCALATION"
    assert res_stage3.tokens_consumed > 0


@pytest.mark.asyncio
async def test_structured_generation_with_conservation_throttling():
    """Validates structured generation automatic degradation when tokens are throttled (ADR-0040)."""
    engine = get_inference_engine()

    prompt = "Customer Tunde Adeleke says: I want to order 220 cartons of flour today urgently. How far with delivery?"

    # When balance is in Conservation Soft Cap (1,500 tokens), INTERNAL_ADMIN is throttled to FallbackFactory!
    card = await engine.generate_structured(
        schema=SixFieldContextCard,
        prompt=prompt,
        policy=ExecutionPolicy.CASCADING_FALLBACK,
        task_priority=TaskPriority.INTERNAL_ADMIN,
        wallet_token_balance=1500,
    )

    assert isinstance(card, SixFieldContextCard)
    assert card.detected_budget_naira == "₦220,000"
    assert card.urgency_tier == "HOT"
    assert card.dialect == "Nigerian Pidgin"
